# -*- coding: utf-8 -*-
"""
视频播放引擎 —— 基于 ffmpeg 管道自解码。

本机 Qt5 的 Windows 多媒体后端（WMF / DirectShow）无法初始化
（连最简单的 baseline H.264 mp4 都会 InvalidMedia），所以绕开 QtMultimedia：

    视频：ffmpeg  -> rawvideo(rgb24) 管道 -> QImage  -> 自绘 QWidget
    音频：ffmpeg  -> s16le PCM       管道 -> QIODevice -> QAudioOutput

音画同步以「音频时钟」为主：QAudioOutput.processedUSecs() 反映硬件真实消耗，
视频帧按该时间选取并丢弃落后帧，长时间播放也不会漂移。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time

from PyQt5.QtCore import (
    QByteArray, QElapsedTimer, QIODevice, QObject, QPointF, Qt, QThread, QTimer, pyqtSignal,
)
from PyQt5.QtGui import QColor, QFont, QImage, QPainter
from PyQt5.QtMultimedia import QAudio, QAudioFormat, QAudioOutput
from PyQt5.QtWidgets import QWidget


# ------------------------------------------------------------------ ffmpeg 定位
def find_ffmpeg() -> tuple[str, str]:
    """返回 (ffmpeg, ffprobe)。按优先级探测，都找不到返回 ("", "")."""
    cands: list[str] = []

    env = os.environ.get("ENGLISH_LAB_FFMPEG", "").strip()
    if env:
        cands.append(env)

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cands.append(os.path.join(here, "bin", "ffmpeg.exe"))

    w = shutil.which("ffmpeg")
    if w:
        cands.append(w)

    try:  # imageio-ffmpeg 自带一份，最省心
        import imageio_ffmpeg  # type: ignore
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe:
            cands.append(exe)
    except Exception:
        pass

    for root in (
        r"C:\ProgramData\chocolatey\bin",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\WinGet\Packages"),
        r"C:\ffmpeg\bin",
    ):
        if root:
            cands.append(os.path.join(root, "ffmpeg.exe"))

    for c in cands:
        if not c:
            continue
        if os.path.isdir(c):
            c = os.path.join(c, "ffmpeg.exe")
        if os.path.exists(c):
            probe = _sibling_probe(c)
            if probe:
                return c, probe
    return "", ""


def _sibling_probe(ffmpeg_exe: str) -> str:
    d = os.path.dirname(ffmpeg_exe)
    base = os.path.splitext(os.path.basename(ffmpeg_exe))[0]
    for name in (base.replace("ffmpeg", "ffprobe"), "ffprobe"):
        p = os.path.join(d, name + ".exe")
        if os.path.exists(p):
            return p
    return shutil.which("ffprobe") or ""


class Probe:
    """视频元信息。"""

    def __init__(self):
        self.duration_ms = 0
        self.width = 0
        self.height = 0
        self.fps = 25.0
        self.has_audio = False
        self.sample_rate = 44100
        self.channels = 2
        self.ok = False


def probe_video(ffprobe: str, path: str) -> Probe:
    p = Probe()
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-show_entries", "stream=codec_type,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json", path,
    ]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=15, creationflags=flags)
        data = json.loads(out.stdout.decode("utf-8", "ignore") or "{}")
    except Exception:
        return p

    try:
        p.duration_ms = int(float(data.get("format", {}).get("duration", 0)) * 1000)
    except Exception:
        pass

    for st in data.get("streams", []):
        if st.get("codec_type") == "video" and not p.width:
            p.width = int(st.get("width") or 0)
            p.height = int(st.get("height") or 0)
            p.fps = _parse_rate(st.get("r_frame_rate"))
        elif st.get("codec_type") == "audio":
            p.has_audio = True
            try:
                p.sample_rate = int(st.get("sample_rate") or 44100)
            except Exception:
                pass
            try:
                p.channels = int(st.get("channels") or 2)
            except Exception:
                pass

    # 兜底：r_frame_rate 有时给出 0/0
    if not 5.0 <= p.fps <= 120.0:
        p.fps = 25.0
    p.ok = bool(p.width and p.height and p.duration_ms)
    return p


def _parse_rate(r: str | None) -> float:
    try:
        a, _, b = str(r).partition("/")
        num = float(a)
        den = float(b) if b else 1.0
        return num / den if den else 25.0
    except Exception:
        return 25.0


# ------------------------------------------------------------------ 读帧线程
class FrameThread(QThread):
    """画面投递线程。

    节拍不再用自己的墙钟，而是跟随「主时钟」（有音频时=音频硬件时钟，
    无音频时=墙钟），每帧都做漂移校正：
      · 帧的显示时刻 = idx × 帧间隔 + av_offset；
      · 主时钟没到点就等，落后超过两帧就整帧跳过——长时间播放零漂移。
    """

    frameReady = pyqtSignal(QImage)
    finished_once = pyqtSignal()

    def __init__(self, ffmpeg: str, path: str, start_sec: float, out_w: int,
                 out_h: int, fps: float, rate: float,
                 clock_fn=None, av_offset_ms: float = 0.0, parent=None):
        super().__init__(parent)
        self.ffmpeg = ffmpeg
        self.path = path
        self.start_sec = start_sec
        self.out_w = out_w
        self.out_h = out_h
        self.fps = fps
        self.rate = rate
        self.clock_fn = clock_fn          # () -> float 主时钟(媒体毫秒)，None=墙钟
        self.av_offset_ms = float(av_offset_ms)
        self._stop_flag = False
        self.proc: subprocess.Popen | None = None

    def stop_now(self):
        self._stop_flag = True
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
        except Exception:
            pass

    def run(self):
        cmd = [self.ffmpeg, "-v", "error", "-nostdin"]
        if self.start_sec > 0.05:
            cmd += ["-ss", "%.3f" % self.start_sec]
        cmd += ["-i", self.path]
        vf = "scale=%d:%d" % (self.out_w, self.out_h)
        if abs(self.rate - 1.0) > 0.01:
            vf += ",setpts=PTS/%.3f" % self.rate
        cmd += ["-vf", vf, "-an", "-sn", "-dn",
                "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]

        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        frame_size = self.out_w * self.out_h * 3
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                bufsize=frame_size * 4, creationflags=flags,
            )
        except Exception:
            self.finished_once.emit()
            return

        interval = 1000.0 / max(1.0, self.fps * max(0.1, self.rate))
        offset = self.av_offset_ms
        clock = QElapsedTimer()
        clock.start()

        def master_ms() -> float:
            """主时钟当前值。给不了就退回本线程自己的墙钟。"""
            if self.clock_fn is None:
                return float(clock.elapsed())
            try:
                return float(self.clock_fn())
            except Exception:
                return float(clock.elapsed())

        def sleep_ms(ms: int):
            """可被 stop 打断的等待。"""
            end = time.time() + ms / 1000.0
            while not self._stop_flag:
                left = end - time.time()
                if left <= 0:
                    return
                self.msleep(min(5, int(left * 1000)))

        try:
            clock.start()
            idx = 0
            while not self._stop_flag:
                due = idx * interval + offset
                wait = due - master_ms()
                # 没到点就等（主时钟 5ms 级更新 + 线程内插值，收敛很快）
                while wait > 1 and not self._stop_flag:
                    sleep_ms(int(min(wait, 40)))
                    wait = due - master_ms()
                if self._stop_flag:
                    break
                if wait < -2 * interval:
                    # 落后太多：丢到当前应显示的那一帧，防累积延迟
                    idx = max(0, int((master_ms() - offset) / interval))
                    continue
                buf = self.proc.stdout.read(frame_size)
                if not buf or len(buf) < frame_size:
                    break
                img = QImage(bytes(buf), self.out_w, self.out_h,
                             self.out_w * 3, QImage.Format_RGB888).copy()
                if self._stop_flag:
                    break
                self.frameReady.emit(img)
                idx += 1
        except Exception:
            pass
        finally:
            try:
                if self.proc and self.proc.poll() is None:
                    self.proc.kill()
            except Exception:
                pass
        self.finished_once.emit()


class AudioThread(QThread):
    """
    只负责把 ffmpeg 的 PCM 读进内存缓冲。

    QAudioOutput 属于主线程，bytesFree() / sink.write() 必须在主线程调用；
    在子线程里碰它会导致主线程长时间卡顿。所以这里只攒数据，
    真正喂给声卡的动作由 FFPlayer 的主线程定时器完成。
    """

    LIMIT = 1 << 20          # 缓冲上限，防止 seek 后冒出旧声音

    def __init__(self, ffmpeg: str, path: str, start_sec: float,
                 rate: float, parent=None):
        super().__init__(parent)
        self.ffmpeg = ffmpeg
        self.path = path
        self.start_sec = start_sec
        self.rate = rate
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._stop_flag = False
        self.proc: subprocess.Popen | None = None

    # ------------------------------------------------------------ 对外
    def take(self, n: int) -> bytes:
        with self._lock:
            if not self._buf:
                return b""
            out = bytes(self._buf[:n])
            del self._buf[:n]
            return out

    def buffered(self) -> int:
        with self._lock:
            return len(self._buf)

    def stop_now(self):
        self._stop_flag = True
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
        except Exception:
            pass

    # ------------------------------------------------------------ 线程体
    def run(self):
        cmd = [self.ffmpeg, "-v", "error", "-nostdin"]
        if self.start_sec > 0.05:
            cmd += ["-ss", "%.3f" % self.start_sec]
        af = "atempo=%.3f" % self.rate if abs(self.rate - 1.0) > 0.01 else "anull"
        cmd += ["-i", self.path, "-vn", "-sn", "-dn",
                "-af", af, "-f", "s16le", "-ac", "2", "-ar", "44100", "-"]

        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                bufsize=1 << 18, creationflags=flags,
            )
        except Exception:
            return

        try:
            while not self._stop_flag:
                if self.buffered() > self.LIMIT:
                    self.msleep(5)
                    continue
                chunk = self.proc.stdout.read(16384)
                if not chunk:
                    break
                if self._stop_flag:
                    break
                with self._lock:
                    self._buf.extend(chunk)
        except Exception:
            pass
        finally:
            try:
                if self.proc and self.proc.poll() is None:
                    self.proc.kill()
            except Exception:
                pass


# ------------------------------------------------------------------ 播放引擎
class FFPlayer(QObject):
    """对外接口尽量贴近 QMediaPlayer，方便替换。"""

    frameReady = pyqtSignal(QImage)
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    playingChanged = pyqtSignal(bool)
    ended = pyqtSignal()
    errorOccurred = pyqtSignal(str)

    MAX_W = 960          # 默认解码输出宽度上限（影院模式会调大）
    CINEMA_W = 1600      # 影院模式解码宽度

    def __init__(self, ffmpeg: str = "", ffprobe: str = "", parent=None):
        super().__init__(parent)
        self.ffmpeg, self.ffprobe = (ffmpeg, ffprobe) if ffmpeg else find_ffmpeg()
        self.info = Probe()
        self.path = ""
        self.rate = 1.0
        self._playing = False
        self._base_ms = 0          # 本次播放在原片中的起点
        self._clock = QElapsedTimer()
        self._audio_out: QAudioOutput | None = None
        self._audio_sink: QIODevice | None = None
        self._audio_base_us = -1
        self._vthread: FrameThread | None = None
        self._athread: AudioThread | None = None
        self._last_img: QImage | None = None
        self._tick = QTimer(self)
        self._tick.setInterval(60)
        self._tick.timeout.connect(self._emit_pos)
        self._apump = QTimer(self)
        self._apump.setInterval(5)
        self._apump.timeout.connect(self._feed_audio)
        self._out_w = self._out_h = 0
        self._max_w = self.MAX_W
        # 主时钟共享状态 (媒体毫秒, 性能时钟戳, 是否在播)：
        # 帧线程只读这个三元组 + 自己插值，绝不跨线程调 Qt 音频接口。
        self.av_offset_ms = 0.0    # 正值=画面延后；配音画不同步可微调
        self._master = (0.0, time.perf_counter(), False)

    # ------------------------------------------------------------ 属性
    def available(self) -> bool:
        return bool(self.ffmpeg and self.ffprobe and os.path.exists(self.ffmpeg))

    def set_ffmpeg(self, exe: str):
        self.ffmpeg = exe
        self.ffprobe = _sibling_probe(exe)

    def set_output_width(self, w: int):
        """调整解码宽度（标准 960 / 影院 1600）。播放中会原地无缝重启解码。"""
        w = max(320, min(1920, int(w)))
        if w == self._max_w:
            return
        self._max_w = w
        if self.path and self.info.ok:
            self._out_w, self._out_h = self._out_size()
            if self._playing:
                pos = self.position()
                self._kill()
                self._spawn(pos)

    def _out_size(self):
        w, h = self.info.width, self.info.height
        if not w or not h:
            return 960, 540
        if w <= self._max_w:
            return w - w % 2, h - h % 2
        nh = int(h * self._max_w / w)
        nh -= nh % 2
        return self._max_w, nh

    # ------------------------------------------------------------ 打开
    def open(self, path: str) -> bool:
        self.stop()
        self.path = path
        if not self.available():
            self.errorOccurred.emit("没有找到 ffmpeg，无法播放视频")
            return False
        if not path or not os.path.exists(path):
            self.errorOccurred.emit("视频文件不存在")
            return False
        self.info = probe_video(self.ffprobe, path)
        if not self.info.ok:
            self.errorOccurred.emit("无法读取视频信息，可能是ffmpeg不支持的格式")
            return False
        self._out_w, self._out_h = self._out_size()
        self._base_ms = 0
        self.durationChanged.emit(self.info.duration_ms)
        self.positionChanged.emit(0)
        return True

    # ------------------------------------------------------------ 控制
    def play(self):
        if not self.path or self._playing:
            return
        if not self.available():
            self.errorOccurred.emit("没有找到 ffmpeg，无法播放视频")
            return
        self._spawn(self._base_ms)
        self._playing = True
        self._set_master(self._base_ms)
        self.playingChanged.emit(True)
        self._tick.start()

    def pause(self):
        if not self._playing:
            return
        self._base_ms = self.position()
        self._playing = False
        self._kill()
        self._set_master(self._base_ms)
        self.playingChanged.emit(False)
        self._tick.stop()
        self.positionChanged.emit(self._base_ms)

    def toggle(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    def stop(self):
        self._kill()
        self._playing = False
        self._set_master(self._base_ms)
        self.playingChanged.emit(False)
        self._tick.stop()

    def seek(self, ms: int):
        ms = max(0, ms)
        if self.info.duration_ms:
            ms = min(ms, self.info.duration_ms)
        was = self._playing
        self._kill()
        self._base_ms = ms
        self._set_master(ms)
        self.positionChanged.emit(ms)
        if was:
            self._spawn(ms)
            self._set_master(ms)
            self._tick.start()
        else:
            # 暂停状态下也要显示那一帧
            self._spawn(ms)
            QTimer.singleShot(500, lambda: self._playing or self._kill_for_frame())

    def set_rate(self, r: float):
        self.rate = r
        if self._playing:
            pos = self.position()
            self._kill()
            self._spawn(pos)
            self._set_master(pos)
            self._tick.start()

    def position(self) -> int:
        """全引擎唯一的时钟读口：播放中=主时钟（音频优先，帧线程同源）。"""
        if not self._playing:
            return self._base_ms
        return int(self._master_clock())

    def duration(self) -> int:
        return self.info.duration_ms

    def is_playing(self) -> bool:
        return self._playing

    # ------------------------------------------------------------ 内部
    def _master_clock(self) -> float:
        """给帧线程/UI 共读的主时钟：共享状态 + 线程内插值（不跨线程调 Qt）。

        - 播放中：以最近一次音频消耗值为锚，按墙钟外推（音频断供时画面
          继续走，恢复后自动等音频追平，同步不破）；
        - 暂停：冻结在锚点。
        """
        m0, s0, playing = self._master
        if not playing:
            return m0
        return m0 + (time.perf_counter() - s0) * 1000.0 * max(0.1, self.rate)

    def _set_master(self, ms: float):
        self._master = (float(ms), time.perf_counter(), self._playing)

    def _kill_for_frame(self):
        # 暂停态 seek：拿到关键帧后立刻收工
        if self._vthread is not None:
            self._vthread.stop_now()
            self._vthread = None

    def _kill(self):
        for t in (self._vthread, self._athread):
            if t is not None:
                t.stop_now()
                try:
                    t.wait(500)
                except Exception:
                    pass
        self._vthread = self._athread = None
        if self._audio_out is not None:
            try:
                self._audio_out.stop()
            except Exception:
                pass
            self._audio_out = None
        self._audio_sink = None
        try:
            self._apump.stop()
        except Exception:
            pass

    def _spawn(self, from_ms: int):
        start_sec = from_ms / 1000.0
        # 从 from_ms 重新起播：基准必须跟着走，否则 set_rate/换解码宽度后
        # position() 会回跳到旧基准（老代码的隐性 bug）
        self._base_ms = int(from_ms)

        self._clock.restart()
        self._athread = None
        self._audio_out = None
        self._audio_sink = None

        # --- 音频立即起（主时钟=声卡消耗时钟，由泵线程持续刷新）---
        if self.info.has_audio:
            try:
                fmt = QAudioFormat()
                fmt.setSampleRate(44100)
                fmt.setChannelCount(2)
                fmt.setSampleSize(16)
                fmt.setCodec("audio/pcm")
                fmt.setByteOrder(QAudioFormat.LittleEndian)
                fmt.setSampleType(QAudioFormat.SignedInt)
                out = QAudioOutput(fmt, self)
                out.setBufferSize(1 << 18)   # 256KB ≈ 1.5s：主线程卡一下也不断音
                sink = out.start()
                if sink is None:
                    out.stop()
                else:
                    self._audio_out = out
                    self._audio_sink = sink
                    self._audio_base_us = -1
                    self._athread = AudioThread(self.ffmpeg, self.path, start_sec,
                                                self.rate, self)
                    self._athread.start()
                    self._apump.start()
            except Exception:
                self._audio_out = None
                self._audio_sink = None

        # --- 视频跟随主时钟逐帧校正（无音频时主时钟退化为墙钟）---
        self._vthread = FrameThread(self.ffmpeg, self.path, start_sec,
                                    self._out_w, self._out_h, self.info.fps,
                                    self.rate, self._master_clock,
                                    self.av_offset_ms, self)
        self._vthread.frameReady.connect(self._on_frame, Qt.QueuedConnection)
        self._vthread.finished_once.connect(self._maybe_end, Qt.QueuedConnection)
        self._vthread.start()
        self._set_master(from_ms)

    def _feed_audio(self):
        """主线程喂数据：按声卡剩余空间写入 PCM，并刷新主时钟。"""
        out = self._audio_out
        sink = self._audio_sink
        th = self._athread
        if out is None or sink is None or th is None:
            return
        try:
            free = out.bytesFree()
            period = out.periodSize()
            if free < period:
                return
            want = min(free - free % 4, period * 4, 1 << 16)
            data = th.take(max(4, want))
            if data:
                sink.write(QByteArray(data))
                if self._audio_base_us < 0:
                    self._audio_base_us = int(out.processedUSecs())
                us = int(out.processedUSecs())
                if us > 0:
                    audio_ms = max(0.0, (us - self._audio_base_us) / 1000.0)
                    self._master = (self._base_ms + audio_ms,
                                    time.perf_counter(), True)
        except Exception:
            pass

    def _on_frame(self, img: QImage):
        if self._vthread is None and not self._playing:
            return
        self._last_img = img
        self.frameReady.emit(img)

    def _maybe_end(self):
        if self._playing and self.position() >= self.info.duration_ms - 300:
            self._base_ms = self.info.duration_ms
            self._kill()
            self._playing = False
            self.playingChanged.emit(False)
            self._tick.stop()
            self.ended.emit()

    def _emit_pos(self):
        if not self._playing:
            return
        # 无音频素材：主时钟按墙钟×倍速推进（有音频时由 _feed_audio 刷新）
        if self._audio_out is None:
            self._set_master(self._base_ms + self._clock.elapsed() * max(0.1, self.rate))
        pos = self.position()
        if pos >= self.info.duration_ms:
            self._maybe_end()
            return
        self.positionChanged.emit(pos)

    def last_frame(self) -> QImage | None:
        return self._last_img


# ------------------------------------------------------------------ 显示部件
class VideoSurface(QWidget):
    """自绘视频画面。

    播放中用 FastTransformation（缩放成本约为 Smooth 的 1/5，这是此前
    卡顿的主因），暂停/静帧时自动切回 Smooth 看清细节；
    按 devicePixelRatio 缩放，高分屏不糊。
    """

    doubleClicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setMinimumHeight(180)
        self._img: QImage | None = None
        self._note = ""
        self._smooth = True          # True=静帧高质量；播放中由外部切为 False
        self._scaled: tuple | None = None   # (key, img) 同尺寸连续帧的缩放缓存
        self.setStyleSheet("QWidget{background:#0E1320;}")

    def set_image(self, img: QImage):
        self._img = img
        self._scaled = None
        self.update()

    def set_note(self, text: str):
        self._note = text
        self._img = None
        self._scaled = None
        self.update()

    def set_smooth(self, on: bool):
        if self._smooth != on:
            self._smooth = on
            self._scaled = None
            self.update()

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0E1320"))
        if self._img and not self._img.isNull():
            dpr = self.devicePixelRatioF() or 1.0
            tw = max(1, int(self.width() * dpr))
            th = max(1, int(self.height() * dpr))
            key = (self._img.cacheKey(), tw, th, self._smooth)
            if self._scaled is None or self._scaled[0] != key:
                mode = Qt.SmoothTransformation if self._smooth else Qt.FastTransformation
                img = self._img.scaled(tw, th, Qt.KeepAspectRatio, mode)
                img.setDevicePixelRatio(dpr)
                self._scaled = (key, img)
            img = self._scaled[1]
            lw, lh = img.width() / dpr, img.height() / dpr
            x = (self.width() - lw) / 2.0
            y = (self.height() - lh) / 2.0
            if self._smooth:
                p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.drawImage(QPointF(x, y), img)
            if self._smooth:
                p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        elif self._note:
            p.setPen(QColor("#8D97AB"))
            f = QFont()
            f.setPointSize(11)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, self._note)
        p.end()
