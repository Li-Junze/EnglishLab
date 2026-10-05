# -*- coding: utf-8 -*-
"""步骤 3：看视频，右侧实时显示最近用到的生词。"""
from __future__ import annotations

import os
import subprocess
import sys

import re

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QShortcut, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from .. import config, db, dictionary, lexicon, srt, videocache, vocab
from ..player import FFPlayer, VideoSurface, find_ffmpeg
from . import theme
from .dialogs import WordDialog
from .widgets import Card, EmptyState, MutedLabel, SectionTitle


def _fmt(ms: int) -> str:
    s = max(0, int(ms / 1000))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------- 状态配色
# 陌生 / 学习中 / 已掌握 —— 看视频时一眼分辨
STATUS_STYLE = {
    "new":      ("#D9550B", "#FFF5EE", "#FBDCC4", "陌生"),
    "learning": ("#8E24AA", "#F9F2FC", "#E6D2F0", "学习中"),
    "known":    ("#0E9C77", "#EFFAF6", "#C6EADF", "已掌握"),
}
NEUTRAL = "#8D97AB"


class SegButton(QPushButton):
    """二选一的分段按钮（动态属性切换样式时需要 unpolish/polish 才生效）。"""

    def __init__(self, text: str, tip: str = "", parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(27)
        self.setProperty("btnsize", "mini")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        if tip:
            self.setToolTip(tip)

    def set_on(self, on: bool):
        self.setChecked(on)
        self.setProperty("btn", "primary" if on else "soft")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


def _style_of(status: str):
    return STATUS_STYLE.get(status, STATUS_STYLE["new"])


class WatchPage(QWidget):
    finished = pyqtSignal()

    def __init__(self, session, speaker, parent=None):
        super().__init__(parent)
        self.session = session
        self.speaker = speaker
        self.player = FFPlayer(self)
        self.player.frameReady.connect(self._on_frame)
        self.player.positionChanged.connect(self._update)
        self.player.playingChanged.connect(self._on_play_state)
        self.player.ended.connect(self._on_end)
        self.player.errorOccurred.connect(self._on_error)
        self.video_widget: VideoSurface | None = None
        self._cue_idx = -1
        # 按"出现轮次"分层：0=刚刚这句，1=上一句，2=更早
        self._layers: list[list[str]] = [[], [], []]
        self._counted: set[tuple[str, int]] = set()
        self._virtual_ms = 0
        self._playing = False
        self._seeking = False
        self._sub_zh = ""
        self._dlg = None
        self._cinema = False
        self._was_max = False
        self._status_cache: dict[str, str] = {}   # 词→掌握状态，避免每词一查库
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._tick)
        # 规则滑块的防抖：拖动过程中不重筛，停下来才真正生效
        self._rule_timer = QTimer(self)
        self._rule_timer.setSingleShot(True)
        self._rule_timer.setInterval(260)
        self._rule_timer.timeout.connect(self._commit_rule)
        self._build()
        self._install_shortcuts()

    # ---------------------------------------------------------------- UI
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # 头部行（影院模式整体隐藏）
        self.wgt_head = QWidget()
        self.wgt_head.setStyleSheet("background:transparent;")
        head = QHBoxLayout(self.wgt_head)
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(SectionTitle("边看边复习"))
        head.addSpacing(14)
        # 右上角只显示当前规则的摘要，改规则在右侧面板顶部的卡片里操作
        self.lbl_rule = QLabel("")
        self.lbl_rule.setStyleSheet(theme.badge_style(theme.ACCENT))
        head.addWidget(self.lbl_rule)

        head.addStretch(1)
        self.lbl_material = MutedLabel("")
        head.addWidget(self.lbl_material)
        root.addWidget(self.wgt_head)

        body = QHBoxLayout()
        body.setSpacing(14)
        body.addLayout(self._build_left(), 10)
        body.addLayout(self._build_right(), 9)
        root.addLayout(body, 1)

        # 底部行（影院模式整体隐藏）
        self.wgt_bottom = QWidget()
        self.wgt_bottom.setStyleSheet("background:transparent;")
        bottom = QHBoxLayout(self.wgt_bottom)
        bottom.setContentsMargins(0, 0, 0, 0)
        self.lbl_tip = QLabel(
            "字幕里的彩色词都会自动配解释：点一下看详情，右侧面板按 当前句 / 上一句 / 更早 分层\n"
            "右侧面板顶部的「弹出规则」可以随时切换判定口径，词频模式直接拖动滑块即时生效"
        )
        self.lbl_tip.setStyleSheet(f"color:{theme.MUTED};background:transparent;")
        bottom.addWidget(self.lbl_tip)
        bottom.addStretch(1)
        self.btn_finish = QPushButton("看完了，去拼写测验 →")
        self.btn_finish.setProperty("btn", "primary")
        self.btn_finish.setCursor(Qt.PointingHandCursor)
        self.btn_finish.setMinimumHeight(38)
        self.btn_finish.clicked.connect(self.finished.emit)
        bottom.addWidget(self.btn_finish)
        root.addWidget(self.wgt_bottom)

        self.empty = EmptyState("还没有素材", "先回到第 1 步导入视频和字幕")
        root.addWidget(self.empty)

    def _build_left(self):
        lay = QVBoxLayout()
        lay.setSpacing(10)

        self.video_card = Card()
        self.video_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vl = QVBoxLayout(self.video_card)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        self.stage = QWidget()
        theme.self_only(self.stage, "video_stage", "background:#0E1320;border-radius:14px;")
        sl = QVBoxLayout(self.stage)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self.video_widget = VideoSurface()
        self.video_widget.doubleClicked.connect(
            lambda: self._set_cinema(not self._cinema))
        self.video_widget.setToolTip("双击进入/退出影院模式（快捷键 F，Esc 退出）")
        sl.addWidget(self.video_widget)
        vl.addWidget(self.stage, 1)

        lay.addWidget(self.video_card, 1)

        # 控制条
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        self.btn_play = QPushButton("播放")
        self.btn_play.setFixedSize(64, 36)
        self.btn_play.setProperty("btn", "ghost")
        self.btn_play.setCursor(Qt.PointingHandCursor)
        self.btn_play.clicked.connect(self.toggle_play)
        ctrl.addWidget(self.btn_play)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        # 拖动时只更新时间文字，松手才真正跳转
        self.slider.sliderMoved.connect(self._seek_preview)
        self.slider.sliderReleased.connect(self._seek_commit)
        ctrl.addWidget(self.slider, 1)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setFixedWidth(110)
        self.lbl_time.setStyleSheet(
            f"color:{theme.TEXT_2};background:transparent;font-family:{theme.MONO};"
        )
        ctrl.addWidget(self.lbl_time)

        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.5x", "0.75x", "1.0x", "1.25x", "1.5x"])
        self.combo_speed.setCurrentIndex(2)
        self.combo_speed.currentIndexChanged.connect(self._set_speed)
        self.combo_speed.setFixedWidth(78)
        ctrl.addWidget(self.combo_speed)

        self.btn_sys = QPushButton("系统播放器")
        self.btn_sys.setProperty("btn", "soft")
        self.btn_sys.setCursor(Qt.PointingHandCursor)
        self.btn_sys.setToolTip("如果内置播放器无法解码，用系统默认程序打开")
        self.btn_sys.clicked.connect(self._open_system)
        ctrl.addWidget(self.btn_sys)

        self.btn_cine = QPushButton("影院模式")
        self.btn_cine.setProperty("btn", "soft")
        self.btn_cine.setCursor(Qt.PointingHandCursor)
        self.btn_cine.setToolTip(
            "放大画面，只保留 视频 + 字幕 + 右侧生词面板\n快捷键 F，Esc 或再点一次退出")
        self.btn_cine.clicked.connect(lambda: self._set_cinema(not self._cinema))
        ctrl.addWidget(self.btn_cine)
        lay.addLayout(ctrl)

        # 字幕
        self.sub_card = Card()
        self.sub_card.setFixedHeight(110)
        sbl = QVBoxLayout(self.sub_card)
        sbl.setContentsMargins(18, 12, 18, 12)
        self.lbl_sub = QLabel("")
        self.lbl_sub.setWordWrap(True)
        self.lbl_sub.setAlignment(Qt.AlignCenter)
        self.lbl_sub.setTextFormat(Qt.RichText)
        f2 = QFont()
        f2.setPointSize(12)
        self.lbl_sub.setFont(f2)
        self.lbl_sub.setStyleSheet(
            f"color:{theme.TEXT};background:transparent;line-height:150%;"
        )
        # 字幕里的生词做成可点击链接，点一下直接看详情
        self.lbl_sub.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.lbl_sub.setOpenExternalLinks(False)
        self.lbl_sub.linkActivated.connect(self._on_word_clicked)
        sbl.addWidget(self.lbl_sub)
        lay.addWidget(self.sub_card)
        return lay

    def _build_rule_card(self) -> QWidget:
        """右侧面板顶部的「弹出规则」：随时切换判定口径 + 拖动词频上限。"""
        card = Card("accent")
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.rule_card = card
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(7)

        row = QHBoxLayout()
        row.setSpacing(8)
        t = QLabel("弹出规则")
        t.setStyleSheet(
            f"color:{theme.TEXT};background:transparent;font-weight:600;font-size:9.5pt;"
        )
        row.addWidget(t)
        row.addStretch(1)
        self.seg_lex = SegButton("按知识库", vocab.POPUP_MODES[0]["desc"])
        self.seg_freq = SegButton("按词频", vocab.POPUP_MODES[1]["desc"])
        self.seg_lex.clicked.connect(lambda: self._switch_mode("lexicon"))
        self.seg_freq.clicked.connect(lambda: self._switch_mode("freq"))
        row.addWidget(self.seg_lex)
        row.addWidget(self.seg_freq)
        lay.addLayout(row)

        # ---- 词频模式的专属行
        self.freq_row = QWidget()
        theme.self_only(self.freq_row, "freq_row", "background:transparent;")
        fl = QVBoxLayout(self.freq_row)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(4)

        ftop = QHBoxLayout()
        ftop.setSpacing(8)
        self.lbl_freq = QLabel("")
        self.lbl_freq.setStyleSheet(
            f"color:{theme.ACCENT};background:transparent;font-weight:600;font-size:9pt;"
        )
        ftop.addWidget(self.lbl_freq)
        ftop.addStretch(1)
        self.chk_skip = QCheckBox("跳过已掌握")
        self.chk_skip.setStyleSheet(
            f"QCheckBox{{background:transparent;color:{theme.TEXT_2};font-size:9pt;}}"
        )
        self.chk_skip.setToolTip("勾上时，已经认识的词不会出现在词频结果里")
        self.chk_skip.stateChanged.connect(lambda _s: self._queue_rule())
        ftop.addWidget(self.chk_skip)
        fl.addLayout(ftop)

        self.slider_freq = QSlider(Qt.Horizontal)
        self.slider_freq.setRange(0, len(vocab.FREQ_STEPS) - 1)
        self.slider_freq.setPageStep(1)
        self.slider_freq.setMinimumWidth(170)
        self.slider_freq.setToolTip("拖到最右 = 不限词频；松手后立刻按新规则重筛")
        self.slider_freq.valueChanged.connect(self._on_freq_move)
        fl.addWidget(self.slider_freq)
        lay.addWidget(self.freq_row)

        self.lbl_hit = MutedLabel("")
        self.lbl_hit.setStyleSheet(
            f"color:{theme.TEXT_2};background:transparent;font-size:9pt;"
        )
        lay.addWidget(self.lbl_hit)
        self._sync_rule_ui()
        return card

    def _build_right(self):
        lay = QVBoxLayout()
        lay.setSpacing(8)

        lay.addWidget(self._build_rule_card())

        head = QHBoxLayout()
        head.addWidget(SectionTitle("生词实时面板"))
        head.addStretch(1)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setProperty("btn", "soft")
        self.btn_clear.setFixedHeight(26)
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self._clear_recent)
        head.addWidget(self.btn_clear)
        lay.addLayout(head)

        # 配色图例：一眼看懂颜色代表什么
        leg = QHBoxLayout()
        leg.setSpacing(10)
        for st in ("new", "learning", "known"):
            color, bg, bd, name = STATUS_STYLE[st]
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(
                f"QLabel{{background:{color};border-radius:5px;border:none;}}"
            )
            t = QLabel(name)
            t.setStyleSheet(f"color:{theme.MUTED};background:transparent;font-size:8.5pt;")
            r = QHBoxLayout()
            r.setSpacing(4)
            r.addWidget(dot)
            r.addWidget(t)
            leg.addLayout(r)
        leg.addStretch(1)
        lay.addLayout(leg)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.panel = QWidget()
        theme.self_only(self.panel, "word_panel", "background:transparent;")
        self.panel_lay = QVBoxLayout(self.panel)
        self.panel_lay.setContentsMargins(2, 2, 6, 2)
        self.panel_lay.setSpacing(5)
        self.panel_lay.addStretch(1)
        self.scroll.setWidget(self.panel)
        lay.addWidget(self.scroll, 1)
        return lay

    def _layer_title(self, text: str, count: int, color: str) -> QLabel:
        lab = QLabel(f"{text}  ·  {count}")
        lab.setStyleSheet(
            f"color:{color};background:transparent;font-size:9pt;font-weight:600;"
        )
        return lab

    # ------------------------------------------------------------ 弹出规则
    def _sync_rule_ui(self):
        """把配置值回填到控件（模式 / 滑块位置 / 勾选项 / 文案）。"""
        mode = vocab.popup_mode()
        self.seg_lex.set_on(mode == "lexicon")
        self.seg_freq.set_on(mode == "freq")
        self.freq_row.setVisible(mode == "freq")
        top = vocab.freq_top()
        self.slider_freq.blockSignals(True)
        self.slider_freq.setValue(vocab.freq_top_index(top))
        self.slider_freq.blockSignals(False)
        self.lbl_freq.setText(vocab.freq_label(top))
        self.chk_skip.blockSignals(True)
        self.chk_skip.setChecked(vocab.freq_skip_known())
        self.chk_skip.blockSignals(False)
        self.lbl_rule.setText(vocab.rule_summary())

    def _switch_mode(self, key: str):
        if vocab.popup_mode() == key:
            self._sync_rule_ui()      # 点已选中的按钮会取消勾选，立刻还原
            return
        vocab.set_popup_mode(key)
        self._sync_rule_ui()
        self._apply_rule()

    def _on_freq_move(self, v: int):
        """拖动中只更新文字，停一下才真正重筛（避免每像素重建一次词表）。"""
        self.lbl_freq.setText(vocab.freq_label(vocab.FREQ_STEPS[v]))
        self._queue_rule()

    def _queue_rule(self):
        self._rule_timer.start(260)

    def _commit_rule(self):
        v = self.slider_freq.value()
        vocab.set_freq_top(vocab.FREQ_STEPS[v])
        vocab.set_freq_skip_known(self.chk_skip.isChecked())
        self._apply_rule()

    def _apply_rule(self):
        """规则变了：立刻按新规则重筛当前素材，并重画字幕与右侧面板。"""
        self.lbl_rule.setText(vocab.rule_summary())
        if not self.session.cues:
            self.lbl_hit.setText("导入素材后按新规则筛选")
            return
        info = self.session.reapply_filter()
        # 已经显示出来的旧词先清掉，避免混进不符合新规则的词
        self._clear_recent()
        if self._cue_idx >= 0:
            # 不打断播放进度，只把当前这句的字幕和面板按新规则重画
            self._rerender_subtitle()
            self._push_words(self.session.words_in_cue(self._cue_idx), self._cue_idx)
        self.lbl_hit.setText(
            f"按当前规则，本素材共 {info['pool']} 个目标词"
            f"（其中 {info['candidates']} 个已排进学词列表）"
        )
        if info["pool"] == 0 and vocab.popup_mode() == "freq" and vocab.freq_skip_known():
            self.lbl_hit.setText(
                "当前词频区间里的词你都认识了\n取消勾选「跳过已掌握」可以把它们也列出来"
            )
        self.lbl_tip.setText(
            f"已切到「{vocab.rule_summary()}」，字幕与右侧面板已按新规则重画"
        )

    # ---------------------------------------------------------------- 绑定
    def bind(self):
        has = bool(self.session.cues)
        self.video_card.setVisible(has)
        self.sub_card.setVisible(has)
        self.scroll.setVisible(has)
        self.empty.setVisible(not has)
        self._status_cache.clear()
        if not has:
            return
        dur = int((self.session.cues[-1].end + 1) * 1000)
        self.lbl_material.setText(
            f"{self.session.title} · {srt.summarize_langs(self.session.cues)}"
        )
        self._virtual_ms = 0
        self._cue_idx = -1
        self._clear_recent()
        self._setup_player(dur)
        self._sync_rule_ui()
        self.lbl_hit.setText(
            f"按当前规则，本素材共 {len(self.session.pool)} 个目标词"
            f"（其中 {len(self.session.words)} 个已排进学词列表）"
        )

    def _setup_player(self, dur_ms: int):
        self._dur = dur_ms
        self.lbl_time.setText(f"00:00 / {_fmt(dur_ms)}")

        vp = self.session.video_path
        if not (vp and os.path.exists(vp)):
            self.video_widget.set_note("没有视频文件\n只用字幕播放：进度条会按字幕时间推进")
            self.btn_play.setEnabled(True)
            return

        if not self.player.available():
            ff, _p = find_ffmpeg()
            if ff:
                self.player.set_ffmpeg(ff)
        if not self.player.available():
            self.video_widget.set_note(
                "没有找到 ffmpeg，内置播放器不可用\n"
                "可以点右下角「系统播放器」用外部程序打开，\n"
                "或在 ⚙ 设置里手动指定 ffmpeg.exe 的路径"
            )
            return

        ok = self.player.open(vp)
        if not ok:
            self.video_widget.set_note("视频无法打开，可以试试「系统播放器」")
            return
        # 最近视频缓存命中：直接续播到上次位置
        rec = videocache.get(vp) or {}
        last_ms = int(rec.get("position_ms") or 0)
        if 5000 < last_ms < self._dur - 3000:
            self.player.seek(last_ms)
            self.video_widget.set_note(
                f"已定位到上次看到的位置 {_fmt(last_ms)}\n点 ▶ 继续播放")
        else:
            self.video_widget.set_note("点 ▶ 开始播放")
        if self.player.duration():
            self._dur = self.player.duration()
            self.lbl_time.setText(f"00:00 / {_fmt(self._dur)}")

    # ---------------------------------------------------------------- 播放
    def toggle_play(self):
        p = self.player
        if p is not None and p.path and p.available() and p.duration():
            p.toggle()
            return
        # 没有可用视频时退回字幕时间轴推演
        self._playing = not self._playing
        if self._playing:
            self.timer.start()
        else:
            self.timer.stop()
        self.btn_play.setText("暂停" if self._playing else "播放")

    def _on_play_state(self, playing: bool):
        self.btn_play.setText("暂停" if playing else "播放")
        # 播放中低耗渲染，暂停时切高质量重采样看清细节
        if self.video_widget is not None:
            self.video_widget.set_smooth(not playing)
        if not playing:
            self.save_recent()

    def _on_end(self):
        self.btn_play.setText("播放")
        self.lbl_tip.setText("这一遍看完了，可以去做拼写测验了")

    def _on_frame(self, img):
        if self.video_widget is not None:
            self.video_widget.set_image(img)

    def _on_error(self, msg: str):
        self.video_widget.set_note(msg)
        self.lbl_tip.setText(msg + "；也可以点「系统播放器」用外部程序打开")

    def _seek_commit(self):
        self._seek(self.slider.value())

    def _is_playing(self) -> bool:
        return self.player is not None and self.player.is_playing()

    def _set_speed(self, i: int):
        rate = [0.5, 0.75, 1.0, 1.25, 1.5][i]
        if self.player is not None:
            self.player.set_rate(rate)
        self._rate = rate

    def _seek_preview(self, value: int):
        """拖动中只更新时间文字，不真的跳转（否则每像素都要重启 ffmpeg）。"""
        ms = int(self._dur * value / 1000.0)
        self.lbl_time.setText(f"{_fmt(ms)} / {_fmt(self._dur)}")

    def _seek(self, value: int):
        ms = int(self._dur * value / 1000.0)
        p = self.player
        if p is not None and p.path and p.available():
            p.seek(ms)
        else:
            self._virtual_ms = ms
            self._update(ms)

    def _open_system(self):
        p = self.session.video_path
        if p and os.path.exists(p):
            try:
                os.startfile(p)  # noqa: S606
            except Exception:
                try:
                    subprocess.Popen(["start", "", p], shell=True)
                except Exception:
                    pass

    # ------------------------------------------------------------ 影院模式
    def _install_shortcuts(self):
        """F 切换影院模式；Esc 退出。只在看视频页生效。"""
        sc_f = QShortcut(QKeySequence(Qt.Key_F), self)
        sc_f.setContext(Qt.WidgetWithChildrenShortcut)
        sc_f.activated.connect(lambda: self._set_cinema(not self._cinema))
        sc_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        sc_esc.setContext(Qt.WidgetWithChildrenShortcut)
        sc_esc.activated.connect(lambda: self._set_cinema(False))

    def _set_cinema(self, on: bool):
        """影院模式：放大画面，只留 视频 + 字幕 + 右侧生词面板。"""
        if on == self._cinema:
            return
        self._cinema = on
        self.wgt_head.setVisible(not on)
        self.wgt_bottom.setVisible(not on)
        root = self.layout()
        if on:
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(6)
        else:
            root.setContentsMargins(24, 20, 24, 20)
            root.setSpacing(14)
        self.sub_card.setFixedHeight(150 if on else 110)
        f = self.lbl_sub.font()
        f.setPointSize(17 if on else 12)
        self.lbl_sub.setFont(f)
        self.btn_cine.setText("退出影院" if on else "影院模式")
        # 解码宽度：影院 1600，标准 960（播放中会原地无缝切换）
        if self.player is not None and self.player.path and self.player.available():
            self.player.set_output_width(
                FFPlayer.CINEMA_W if on else FFPlayer.MAX_W)
        if self.video_widget is not None:
            self.video_widget.set_smooth(not self._is_playing())
        # 窗口：进影院自动最大化，退出恢复
        win = self.window()
        if on:
            self._was_max = win.isMaximized()
            win.showMaximized()
        elif getattr(self, "_was_max", False):
            win.showMaximized()
        else:
            win.showNormal()
        self.lbl_tip.setText(
            "已进入影院模式：双击画面或按 Esc 退出"
            if on else "已退出影院模式，按 F 可再次进入")

    # ------------------------------------------------------------ 最近视频缓存
    def save_recent(self):
        """把当前素材的续播信息写进最近缓存（LRU 5 个，落盘）。"""
        try:
            s = self.session
            if not (s.video_path and os.path.exists(s.video_path)):
                return
            videocache.touch(
                s.video_path, s.srt_path, s.material_id, s.title,
                self.player.position() if self.player else 0,
                int(getattr(self, "_dur", 0) or 0),
                getattr(self, "_rate", 1.0),
            )
        except Exception:
            pass

    def _tick(self):
        if not self._playing:
            return
        self._virtual_ms += int(120 * getattr(self, "_rate", 1.0))
        if self._virtual_ms >= self._dur:
            self._virtual_ms = self._dur
            self._playing = False
            self.timer.stop()
            self.btn_play.setText("播放")
        self._update(self._virtual_ms)

    def _update(self, ms: int):
        self.lbl_time.setText(f"{_fmt(ms)} / {_fmt(self._dur)}")
        if self._dur:
            self.slider.blockSignals(True)
            self.slider.setValue(int(ms * 1000.0 / self._dur))
            self.slider.blockSignals(False)
        t = ms / 1000.0
        idx = srt.find_index(self.session.cues, t)
        if idx == self._cue_idx:
            return
        self._cue_idx = idx
        if idx < 0:
            self.lbl_sub.setText("")
            return
        cue = self.session.cues[idx]
        en, zh = self.session.cue_text(idx)
        en = en or cue.text
        parts = [self._highlight(en)]
        if zh:
            parts.append(
                f'<span style="color:{theme.MUTED};font-size:15px;">{zh}</span>'
            )
        self.lbl_sub.setText("<br>".join(parts))
        self._push_words(self.session.words_in_cue(idx), idx)

    # ---------------------------------------------------------------- 高亮
    def _status_of(self, w: str) -> str:
        st = self._status_cache.get(w)
        if st is not None:
            return st
        row = db.get_word(w)
        st = row["status"] if row else db.NEW
        self._status_cache[w] = st
        return st

    def _highlight(self, text: str) -> str:
        """字幕高亮：所有知识库外的词都标出来，颜色 = 掌握程度，且可点击。"""
        if not text:
            return ""
        words = lexicon.unknown_in_text(text)
        if not words:
            return text
        color_of = {w: _style_of(self._status_of(w))[0] for w in words}
        pat = r"\b(" + "|".join(
            re.escape(w) + r"\w*" for w in sorted(words, key=len, reverse=True)
        ) + r")\b"

        def rep(m: "re.Match") -> str:
            raw = m.group(0)
            base = lexicon.normalize(raw).lower()
            lm = lexicon.lemma(base)
            color = color_of.get(lm) or color_of.get(base)
            if color is None:
                return raw
            return (
                f'<a href="{lm}" style="color:{color};font-weight:700;'
                f'text-decoration:none;">{raw}</a>'
            )

        return re.sub(pat, rep, text, flags=re.I)

    def _on_word_clicked(self, word: str):
        """点字幕里的生词：发音 + 弹出详情（非模态，视频继续播）。"""
        w = (word or "").lower().strip()
        if not w:
            return
        self.speaker.speak(w)
        dlg = WordDialog(w, self.speaker, self)
        dlg.finished.connect(lambda _r: setattr(self, "_dlg", None))
        self._dlg = dlg
        dlg.show()

    # ---------------------------------------------------------------- 词面板
    def _push_words(self, words: list[str], cue_idx: int):
        """新的句子来了：轮次往下压一层，并实时更新知识库。"""
        for w in words:
            if (w, cue_idx) not in self._counted:
                self._counted.add((w, cue_idx))
                # 出现次数累计到阈值会自动纳入知识库（不用手动点掌握）
                seen = db.bump_encounter(w, 1)
                try:
                    if int(seen) >= int(config.get("auto_master_threshold", 5)):
                        self._status_cache.pop(w, None)   # 状态可能已自动升级
                except Exception:
                    pass
                for item in self.session.words:
                    if item["word"] == w:
                        item["status"] = self._status_of(w)
                for item in self.session.pool:
                    if item["word"] == w:
                        item["status"] = self._status_of(w)

        prev = self._layers[0]
        older = (self._layers[1] + self._layers[2])
        cap = int(config.get("recent_panel_size", 40))
        self._layers[2] = [w for w in older if w not in words][:cap]
        self._layers[1] = [w for w in prev if w not in words]
        self._layers[0] = list(words)
        self._render_panel()

    def _render_panel(self):
        while self.panel_lay.count() > 1:
            it = self.panel_lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        if not any(self._layers):
            tip = MutedLabel("还没有捕捉到生词，开始播放后这里会实时列出")
            tip.setAlignment(Qt.AlignCenter)
            self.panel_lay.insertWidget(0, tip)
            return

        titles = [("刚刚这句", theme.ACCENT), ("上一句", theme.TEXT_2), ("更早", theme.MUTED)]
        shown: set[str] = set()
        n = self.panel_lay.count() - 1
        for li, layer in enumerate(self._layers):
            if not layer:
                continue
            text, color = titles[li]
            self.panel_lay.insertWidget(n, self._layer_title(text, len(layer), color))
            n += 1
            for w in layer:
                if w in shown:
                    continue
                shown.add(w)
                self.panel_lay.insertWidget(n, self._word_card(w, fresh=(li == 0)))
                n += 1

    def _word_card(self, w: str, fresh: bool = False) -> QWidget:
        status = self._status_of(w)
        color, bg, bd, name = _style_of(status)
        row = db.get_word(w)
        phonetic = (row["phonetic"] if row else "") or ""
        times = int(row["encounter"]) if row else 0

        c = Card()
        # 只匹配卡片自身（#objectName），避免 QFrame{...} 规则参与后代按钮的
        # 样式级联（曾与面板的 QWidget 规则组合，把 primary 渐变盖成透明）
        border = f"border:1px solid {bd};" + (f"border-left:4px solid {color};" if fresh else "")
        c.setObjectName("word_card")
        c.setStyleSheet(f"QWidget#word_card{{background:{bg};{border}border-radius:12px;}}")
        lay = QHBoxLayout(c)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(8)

        # 左：词 + 释义 + 元信息
        left = QVBoxLayout()
        left.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)
        name_lbl = QLabel(w)
        name_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f = QFont()
        f.setPointSize(12 if fresh else 11)
        f.setBold(True)
        name_lbl.setFont(f)
        name_lbl.setStyleSheet(f"color:{color};background:transparent;")
        top.addWidget(name_lbl)
        if phonetic:
            ph = QLabel(phonetic)
            ph.setStyleSheet(
                f"color:{theme.MUTED};background:transparent;font-size:8.5pt;"
            )
            top.addWidget(ph)
        top.addStretch(1)
        left.addLayout(top)

        mean = QLabel(dictionary.brief(w) or "正在查释义…")
        mean.setWordWrap(True)
        # wordWrap 的 QLabel 在滚动区里不会撑开父卡片，给足两行高度防止截断
        mean.setMinimumHeight(30)
        mean.setStyleSheet(
            f"color:{theme.TEXT};background:transparent;font-size:10pt;"
        )
        left.addWidget(mean)

        meta = QLabel(
            f"{name} · 见过 {times} 次"
            + (" · 已在学词列表" if self.session.in_study(w) else "")
        )
        meta.setStyleSheet(
            f"color:{theme.MUTED};background:transparent;font-size:8pt;"
        )
        left.addWidget(meta)
        lay.addLayout(left, 1)

        # 右：操作
        ops = QVBoxLayout()
        ops.setSpacing(3)
        b_say = QPushButton("发音")
        b_say.setProperty("btn", "ghost")
        b_say.setProperty("btnsize", "mini")
        b_say.setCursor(Qt.PointingHandCursor)
        b_say.setFixedHeight(26)
        b_say.clicked.connect(lambda: self.speaker.speak(w))
        ops.addWidget(b_say)

        if status != db.KNOWN:
            b_ok = QPushButton("掌握")
            b_ok.setProperty("btn", "success")
            b_ok.setProperty("btnsize", "mini")
            b_ok.setToolTip("标记为已掌握，立即写入知识库")
            b_ok.setCursor(Qt.PointingHandCursor)
            b_ok.setFixedHeight(26)
            b_ok.clicked.connect(lambda: self._mark(w))
            ops.addWidget(b_ok)
        elif not self.session.in_study(w):
            b_add = QPushButton("加入学习")
            b_add.setProperty("btn", "primary")
            b_add.setProperty("btnsize", "mini")
            b_add.setToolTip("排进学词列表，之后会出拼写测验")
            b_add.setCursor(Qt.PointingHandCursor)
            b_add.setFixedHeight(26)
            b_add.clicked.connect(lambda: self._add(w))
            ops.addWidget(b_add)

        b_hide = QPushButton("不再显示")
        b_hide.setProperty("btn", "soft")
        b_hide.setProperty("btnsize", "mini")
        b_hide.setToolTip("以后所有素材都不再捕捉和高亮它（可在词库里恢复）")
        b_hide.setCursor(Qt.PointingHandCursor)
        b_hide.setFixedHeight(26)
        b_hide.clicked.connect(lambda: self._hide(w))
        ops.addWidget(b_hide)
        lay.addLayout(ops)

        # wordWrap 的 QLabel 在滚动区里不会自动撑开父卡片，
        # 按实际可用宽度算出释义需要的行数高度，保证完整显示
        avail = max(160, self.scroll.viewport().width() - 160)
        h = mean.heightForWidth(avail)
        if h > mean.minimumHeight():
            mean.setMinimumHeight(h)

        if not dictionary.brief(w):
            dictionary.lookup_async(w, lambda wd, info: self._refresh_mean(wd, info))
        return c

    def _refresh_mean(self, word: str, info: dict):
        """后台查词回来了，把释义和音标补到卡片上。"""
        txt = (info.get("translations") or [""])[0]
        if not txt:
            return
        for i in range(self.panel_lay.count() - 1):
            card = self.panel_lay.itemAt(i).widget()
            if not card:
                continue
            labels = card.findChildren(QLabel)
            if labels and labels[0].text() == word:
                for lb in labels:
                    if lb.text().startswith("正在查释义"):
                        lb.setText(txt)
                ph = info.get("us_phone") or info.get("uk_phone") or ""
                if ph and len(labels) > 1 and len(labels[1].text()) < 20:
                    labels[1].setText(ph)
                return

    def _mark(self, w: str):
        db.mark_known(w, db.ORIGIN_USER)
        self._status_cache.pop(w, None)
        for item in self.session.words + self.session.pool:
            if item["word"] == w:
                item["status"] = db.KNOWN
        self._render_panel()
        self._rerender_subtitle()

    def _add(self, w: str):
        self.session.add_to_study(w)
        self._render_panel()

    def _hide(self, w: str):
        """以后不再出现这个词。"""
        self.session.block_word(w)
        self._status_cache.pop(w, None)
        self._layers = [
            [x for x in layer if x != w] for layer in self._layers
        ]
        self._render_panel()
        self._rerender_subtitle()

    def _rerender_subtitle(self):
        """词状态变了，字幕高亮要立刻跟着变。"""
        if self._cue_idx < 0:
            return
        en, zh = self.session.cue_text(self._cue_idx)
        if not en:
            return
        parts = [self._highlight(en)]
        if zh:
            parts.append(
                f'<span style="color:{theme.MUTED};font-size:15px;">{zh}</span>'
            )
        self.lbl_sub.setText("<br>".join(parts))

    def _clear_recent(self):
        self._layers = [[], [], []]
        self._render_panel()
