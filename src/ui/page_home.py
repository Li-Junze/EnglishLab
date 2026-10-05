# -*- coding: utf-8 -*-
"""步骤 1：导入素材（拖入视频 + 字幕）。"""
from __future__ import annotations

import os
import time
from typing import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .. import config, db, srt, vocab
from . import theme
from .widgets import Card, EmptyState, MutedLabel, SectionTitle

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".wmv", ".m4v", ".ts"}
SUB_EXT = {".srt", ".vtt", ".ass", ".ssa", ".txt"}


def _ago(ts: float) -> str:
    if not ts:
        return "很久以前"
    dt = time.time() - ts
    if dt < 60:
        return "刚刚"
    if dt < 3600:
        return f"{int(dt // 60)} 分钟前"
    if dt < 86400:
        return f"{int(dt // 3600)} 小时前"
    if dt < 7 * 86400:
        return f"{int(dt // 86400)} 天前"
    return time.strftime("%m-%d", time.localtime(ts))


class MaterialRow(QFrame):
    """历史素材一行：双击直接复习。"""

    openRequested = pyqtSignal(int, int)   # material_id, 目标页面

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.mid = row["id"]
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QFrame{{background:#FFFFFF;border:1px solid {theme.BORDER};"
            f"border-radius:10px;}}"
            f"QFrame:hover{{border:1px solid {theme.ACCENT};background:#FAFBFF;}}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 9, 14, 9)
        lay.setSpacing(10)

        box = QVBoxLayout()
        box.setSpacing(2)
        t = QLabel(row["title"] or "(未命名)")
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        t.setFont(f)
        t.setStyleSheet(f"color:{theme.TEXT};background:transparent;")
        known, total = db.material_mastered(self.mid)
        pct = f"{known}/{total}" if total else "—"
        sub = MutedLabel(
            f"{row['word_count']} 个生词 · 已掌握 {pct} · {_ago(row['last_opened'])}"
        )
        box.addWidget(t)
        box.addWidget(sub)
        lay.addLayout(box, 1)

        b1 = QPushButton("学词")
        b1.setProperty("btn", "soft")
        b1.setFixedHeight(28)
        b1.setCursor(Qt.PointingHandCursor)
        b1.clicked.connect(lambda: self.openRequested.emit(self.mid, 1))
        b2 = QPushButton("看视频")
        b2.setProperty("btn", "ghost")
        b2.setFixedHeight(28)
        b2.setCursor(Qt.PointingHandCursor)
        b2.clicked.connect(lambda: self.openRequested.emit(self.mid, 2))
        lay.addWidget(b1)
        lay.addWidget(b2)

    def mouseDoubleClickEvent(self, e):
        self.openRequested.emit(self.mid, 2)
        super().mouseDoubleClickEvent(e)


class DropZone(QFrame):
    """拖拽投放区。"""

    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._hover = False
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)

        self.icon = QLabel("＋")
        f = QFont()
        f.setPointSize(34)
        self.icon.setFont(f)
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet(f"color:{theme.ACCENT};background:transparent;")

        self.title = QLabel("把视频和字幕拖进来")
        f2 = QFont()
        f2.setPointSize(13)
        f2.setBold(True)
        self.title.setFont(f2)
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet(f"color:{theme.TEXT};background:transparent;")

        self.desc = MutedLabel(
            "支持 mp4 / mkv / webm 等视频，以及 srt / vtt 字幕\n"
            "两个文件一起拖进来即可自动配对，也可以分开拖"
        )
        self.desc.setAlignment(Qt.AlignCenter)

        lay.addWidget(self.icon)
        lay.addWidget(self.title)
        lay.addWidget(self.desc)
        self.setStyleSheet(
            f"DropZone{{background:{theme.PANEL};border:2px dashed {theme.BORDER};"
            f"border-radius:16px;}}"
        )

    # ------------------------------------------------------------ 拖拽
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self._hover = True
            self.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._hover = False
        self.update()

    def dropEvent(self, e):
        self._hover = False
        self.update()
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        if paths:
            self.files_dropped.emit(paths)

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self._hover:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(theme.ACCENT))
        pen.setWidth(2)
        p.setPen(pen)
        path = QPainterPath()
        path.addRoundedRect(2, 2, self.width() - 4, self.height() - 4, 16, 16)
        p.drawPath(path)


class HomePage(QWidget):
    loaded = pyqtSignal(str, str)             # srt_path, video_path
    openMaterial = pyqtSignal(int, int)       # material_id, 目标页面

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.video_path = ""
        self.srt_path = ""
        self.setAcceptDrops(True)
        self._build()

    # ---------------------------------------------------------------- UI
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        head = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(2)
        left.addWidget(SectionTitle("导入学习素材"))
        left.addWidget(MutedLabel("一段 TED 视频 + 对应字幕，开启一轮完整的学习流程"))
        head.addLayout(left)
        head.addStretch(1)

        self.stat_known = self._stat("已掌握", "0")
        self.stat_learning = self._stat("学习中", "0")
        self.stat_mat = self._stat("素材", "0")
        for w in (self.stat_known, self.stat_learning, self.stat_mat):
            head.addWidget(w)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(16)

        self.zone = DropZone()
        self.zone.files_dropped.connect(self._on_files)
        body.addWidget(self.zone, 3)

        side = QVBoxLayout()
        side.setSpacing(12)
        side.setContentsMargins(0, 0, 0, 0)

        pick = Card()
        pl = QVBoxLayout(pick)
        pl.setContentsMargins(18, 16, 18, 16)
        pl.setSpacing(10)
        pl.addWidget(SectionTitle("或者手动选择"))

        self.lbl_video = self._file_row("视频", "未选择")
        self.lbl_srt = self._file_row("字幕", "未选择")
        pl.addLayout(self.lbl_video)
        pl.addLayout(self.lbl_srt)

        row = QHBoxLayout()
        self.btn_video = self._mk_btn("选择视频", "soft")
        self.btn_srt = self._mk_btn("选择字幕", "soft")
        self.btn_video.clicked.connect(self._pick_video)
        self.btn_srt.clicked.connect(self._pick_srt)
        row.addWidget(self.btn_video)
        row.addWidget(self.btn_srt)
        pl.addLayout(row)
        side.addWidget(pick)

        self.ready_card = Card("accent")
        rl = QVBoxLayout(self.ready_card)
        rl.setContentsMargins(18, 16, 18, 16)
        rl.setSpacing(8)
        self.ready_title = QLabel("等待字幕")
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        self.ready_title.setFont(f)
        self.ready_title.setStyleSheet("QLabel{background:transparent;}")
        self.ready_desc = MutedLabel("导入字幕后会自动对照你的知识库筛出生词")
        self.btn_start = self._mk_btn("开始学词 →", "primary")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._start)
        rl.addWidget(self.ready_title)
        rl.addWidget(self.ready_desc)
        rl.addWidget(self.btn_start)
        side.addWidget(self.ready_card)
        side.addStretch(1)

        body.addLayout(side, 2)
        root.addLayout(body, 1)

        # ---- 历史素材：一键继续复习 ----
        self.hist_card = Card()
        hl = QVBoxLayout(self.hist_card)
        hl.setContentsMargins(16, 12, 16, 12)
        hl.setSpacing(8)
        hh = QHBoxLayout()
        hh.addWidget(SectionTitle("继续学习"))
        hh.addStretch(1)
        hh.addWidget(MutedLabel("双击一行直接接着看，或点「学词」重新过一遍"))
        hl.addLayout(hh)

        self.hist_scroll = QScrollArea()
        self.hist_scroll.setWidgetResizable(True)
        self.hist_scroll.setFrameShape(QFrame.NoFrame)
        self.hist_scroll.setFixedHeight(150)
        self.hist_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.hist_box = QWidget()
        theme.self_only(self.hist_box, "home_hist", "background:transparent;")
        self.hist_lay = QVBoxLayout(self.hist_box)
        self.hist_lay.setContentsMargins(0, 0, 6, 0)
        self.hist_lay.setSpacing(6)
        self.hist_lay.addStretch(1)
        self.hist_scroll.setWidget(self.hist_box)
        hl.addWidget(self.hist_scroll)
        root.addWidget(self.hist_card)

        self.hint = MutedLabel("")
        self.hint.setAlignment(Qt.AlignCenter)
        root.addWidget(self.hint)

        self.refresh_stats()

    def _stat(self, name, value) -> QWidget:
        c = Card()
        c.setFixedSize(96, 62)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(0)
        v = QLabel(value)
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        v.setFont(f)
        v.setStyleSheet(f"color:{theme.ACCENT};background:transparent;")
        v.setAlignment(Qt.AlignCenter)
        n = QLabel(name)
        n.setStyleSheet(f"color:{theme.MUTED};background:transparent;font-size:9pt;")
        n.setAlignment(Qt.AlignCenter)
        lay.addWidget(v)
        lay.addWidget(n)
        c._value = v
        return c

    def _file_row(self, tag, value):
        lay = QHBoxLayout()
        t = QLabel(tag)
        t.setFixedWidth(34)
        t.setStyleSheet(f"color:{theme.MUTED};background:transparent;")
        v = QLabel(value)
        v.setStyleSheet(f"color:{theme.TEXT_2};background:transparent;")
        v.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(v, 1)
        lay._label = v
        return lay

    def _mk_btn(self, text, kind):
        from PyQt5.QtWidgets import QPushButton
        b = QPushButton(text)
        b.setProperty("btn", kind)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(34)
        return b

    # ---------------------------------------------------------------- 交互
    def refresh_stats(self):
        st = db.stats()
        self.stat_known._value.setText(str(st["known"]))
        self.stat_learning._value.setText(str(st["learning"] + st["new"]))
        self.stat_mat._value.setText(str(st["materials"]))
        lv = vocab.level_by_key(vocab.current_level_key())
        self.stat_known.setToolTip(
            f"其中 {st['base']} 个是当前词汇水准「{lv['name']}」自带的基准词，"
            f"真正被你标记为掌握的另有 {st['known'] - st['base']} 个"
        )
        self.stat_learning.setToolTip("还没有标记为掌握的生词")
        self._render_history()

    def _render_history(self):
        while self.hist_lay.count() > 1:
            it = self.hist_lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        rows = db.materials_list(30)
        self.hist_card.setVisible(bool(rows))
        n = 0
        for r in rows:
            row = MaterialRow(r)
            row.openRequested.connect(self.openMaterial.emit)
            self.hist_lay.insertWidget(n, row)
            n += 1

    def _set_file(self, kind: str, path: str):
        name = os.path.basename(path)
        if kind == "video":
            self.video_path = path
            self.lbl_video._label.setText(name)
        else:
            self.srt_path = path
            self.lbl_srt._label.setText(name)
        self._update_ready()

    def _update_ready(self):
        if self.srt_path:
            try:
                cues = srt.parse(self.srt_path)
                dur = cues[-1].end if cues else 0
                mm, ss = divmod(int(dur), 60)
                self.ready_title.setText("字幕已就绪")
                self.ready_desc.setText(
                    f"共 {len(cues)} 条字幕 · 约 {mm} 分 {ss:02d} 秒"
                    + ("\n视频已匹配" if self.video_path else "\n（没有视频也能学，播放环节可跳过）")
                )
                self.btn_start.setEnabled(True)
            except Exception as e:
                self.ready_title.setText("字幕解析失败")
                self.ready_desc.setText(str(e))
                self.btn_start.setEnabled(False)
        else:
            self.ready_title.setText("等待字幕")
            self.ready_desc.setText("导入字幕后会自动对照你的知识库筛出生词")
            self.btn_start.setEnabled(False)

    def _on_files(self, paths: list[str]):
        expanded: list[str] = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, files in os.walk(p):
                    for fn in files:
                        expanded.append(os.path.join(root, fn))
            else:
                expanded.append(p)
        for p in expanded:
            ext = os.path.splitext(p)[1].lower()
            if ext in VIDEO_EXT:
                self._set_file("video", p)
            elif ext in SUB_EXT:
                self._set_file("srt", p)
        if not self.srt_path:
            self.hint.setText("没有识别到字幕文件，试试手动选择 srt")

    def _pick_video(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择视频", "", "视频文件 (*.mp4 *.mkv *.webm *.mov *.avi *.flv *.wmv *.m4v);;所有文件 (*.*)"
        )
        if p:
            self._set_file("video", p)

    def _pick_srt(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择字幕", "", "字幕文件 (*.srt *.vtt *.txt);;所有文件 (*.*)"
        )
        if p:
            self._set_file("srt", p)

    def _start(self):
        if not self.srt_path:
            return
        self.hint.setText("正在对照知识库筛选生词…")
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
        self.loaded.emit(self.srt_path, self.video_path)

    # ---------------------------------------------------------------- 拖拽代理
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        if paths:
            self._on_files(paths)
