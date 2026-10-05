# -*- coding: utf-8 -*-
"""主窗口：侧栏导航 + 页面栈 + 全局搜索。"""
from __future__ import annotations

import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .. import audio, config, lexicon
from ..session import Session
from . import theme
from .dialogs import SettingsDialog, WordDialog
from .page_home import HomePage
from .page_learn import LearnPage
from .page_quiz import QuizPage
from .page_vault import VaultPage
from .page_watch import WatchPage
from .widgets import NavButton


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME}  v{config.APP_VERSION}")
        self.resize(1320, 840)
        self.setMinimumSize(1120, 700)
        self.setAcceptDrops(True)
        self.setStyleSheet(theme.QSS)

        self.session = Session()
        self.speaker = audio.Speaker()
        self.session.on_change = self._on_session_change

        self._build()
        self._boot()

    # ---------------------------------------------------------------- 构建
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"QStackedWidget{{background:{theme.BG};}}")
        body.addWidget(self.stack, 1)

        bw = QWidget()
        bw.setLayout(body)
        root.addWidget(bw, 1)

    def _build_header(self):
        h = QFrame()
        h.setFixedHeight(60)
        # 清华紫大色块：与侧栏同渐变，拼成 L 形色块
        h.setStyleSheet(
            "QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #4C0558, stop:1 #7A0D8A);border:none;}"
        )
        lay = QHBoxLayout(h)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)

        logo = QLabel("EL")
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        logo.setFont(f)
        logo.setStyleSheet(
            f"background:#FFFFFF;color:{theme.ACCENT};border-radius:10px;"
        )
        lay.addWidget(logo)

        name = QLabel("English Lab")
        f2 = QFont()
        f2.setPointSize(13)
        f2.setBold(True)
        name.setFont(f2)
        name.setStyleSheet("color:#FFFFFF;background:transparent;")
        lay.addWidget(name)

        sub = QLabel("看视频 · 学长单词")
        sub.setStyleSheet("color:rgba(255,255,255,0.62);background:transparent;font-size:9pt;")
        lay.addWidget(sub)

        lay.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("输入任意单词，回车查询")
        self.search.setFixedWidth(300)
        self.search.setMinimumHeight(36)
        self.search.setProperty("line", "search")
        self.search.returnPressed.connect(self._do_search)
        lay.addWidget(self.search)

        btn_set = QPushButton("设置")
        btn_set.setFixedSize(52, 32)
        btn_set.setCursor(Qt.PointingHandCursor)
        btn_set.setToolTip("设置")
        btn_set.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.14);color:#FFFFFF;"
            "border:1px solid rgba(255,255,255,0.28);border-radius:9px;"
            "padding:0;font-size:9pt;}"
            "QPushButton:hover{background:rgba(255,255,255,0.24);}"
        )
        btn_set.clicked.connect(self._open_settings)
        lay.addWidget(btn_set)
        return h

    def _build_sidebar(self):
        side = QFrame()
        side.setFixedWidth(132)
        # 清华紫大色块（与顶栏相接）
        side.setStyleSheet(
            "QFrame{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #7A0D8A, stop:1 #4C0558);border:none;}"
        )
        lay = QVBoxLayout(side)
        lay.setContentsMargins(10, 14, 10, 14)
        lay.setSpacing(3)

        tip = QLabel("学习流程")
        tip.setStyleSheet("color:rgba(255,255,255,0.55);background:transparent;font-size:8pt;")
        lay.addWidget(tip)
        lay.addSpacing(6)

        self.navs: list[NavButton] = []
        labels = ["导入", "学词", "视频", "测验", "词库"]
        fulls = ["导入素材", "学词卡", "看视频", "拼写测验", "我的词库"]
        for i, t in enumerate(labels):
            b = NavButton(str(i + 1), t, dark=True)
            b.setToolTip(fulls[i])
            b.clicked.connect(lambda _, idx=i: self.goto(idx))
            self.navs.append(b)
            lay.addWidget(b)

        lay.addStretch(1)

        self.lbl_prog = QLabel("")
        self.lbl_prog.setWordWrap(True)
        self.lbl_prog.setStyleSheet(
            "color:rgba(255,255,255,0.65);background:transparent;font-size:8pt;"
        )
        lay.addWidget(self.lbl_prog)
        return side

    def _boot(self):
        # 页面
        self.home = HomePage(self.session)
        self.learn = LearnPage(self.session, self.speaker)
        self.watch = WatchPage(self.session, self.speaker)
        self.quiz = QuizPage(self.session, self.speaker)
        self.vault = VaultPage(self.speaker)
        self.pages = [self.home, self.learn, self.watch, self.quiz, self.vault]
        for p in self.pages:
            self.stack.addWidget(p)

        self.home.loaded.connect(self._on_loaded)
        self.home.openMaterial.connect(self.open_material)
        self.learn.finished.connect(lambda: self.goto(2))
        self.watch.finished.connect(lambda: self.goto(3))
        self.quiz.finished.connect(lambda: self.goto(4))

        self.goto(0)

    # ---------------------------------------------------------------- 流程
    def goto(self, index: int):
        prev = getattr(self, "_cur", 0)
        # 离开"看视频"时记下进度，下次从历史里打开能接着看
        if prev == 2 and index != 2 and self.session.material_id:
            try:
                self.session.save_progress(self.watch.player.position())
            except Exception:
                pass
            try:
                self.watch.save_recent()   # 最近 5 个视频缓存（含续播位置）
            except Exception:
                pass
        self._cur = index
        for i, b in enumerate(self.navs):
            b.set_active(i == index)
        self.stack.setCurrentIndex(index)
        page = self.pages[index]
        for name in ("bind", "refresh", "refresh_stats"):
            fn = getattr(page, name, None)
            if callable(fn):
                try:
                    fn()
                except TypeError:
                    try:
                        fn(False)
                    except Exception:
                        pass
                except Exception:
                    pass
        self._update_progress()

    def _on_loaded(self, srt_path: str, video_path: str):
        info = self.session.load(srt_path, video_path)
        n_pool = info.get("pool", 0)
        self.home.hint.setText(
            f"已从 {len(self.session.cues)} 条字幕中筛出 {n_pool} 个生词，"
            f"其中 {info['candidates']} 个排进了学词列表（看视频时全部都会高亮）"
        )
        pool = [it["word"] for it in self.session.pool]
        audio.prefetch_audio(pool[:80])
        from .. import dictionary
        # 整个生词池都预热释义，看视频时才能瞬间显示中文
        dictionary.prefetch(pool)
        self.home.refresh_stats()
        self.goto(1)

    def open_material(self, mid: int, go: int = 2):
        """从首页历史列表直接打开旧素材复习。"""
        info = self.session.load_material(mid)
        if not info:
            self.home.hint.setText("这个素材的字幕文件找不到了，请重新导入")
            return
        from .. import dictionary
        dictionary.prefetch([it["word"] for it in self.session.pool])
        self.home.hint.setText(
            f"已重新载入「{self.session.title}」，{info.get('pool', 0)} 个生词待复习"
        )
        self.goto(go)

    def _on_session_change(self):
        self.learn.refresh()
        self.learn.refresh_list()
        self._update_progress()

    def _update_progress(self):
        total = len(self.session.words)
        if not total:
            self.lbl_prog.setText("还没有进行中的素材")
            return
        done = sum(1 for w in self.session.words if w["status"] == "known")
        self.lbl_prog.setText(f"当前素材：{done}/{total} 已掌握")

    def refresh_all(self):
        for i, p in enumerate(self.pages):
            fn = getattr(p, "refresh_stats", None) or getattr(p, "refresh", None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        self._update_progress()

    # ---------------------------------------------------------------- 交互
    def _do_search(self):
        w = self.search.text().strip().lower()
        if not w:
            return
        import re
        if not re.fullmatch(r"[a-z\-']+", w):
            self.search.setToolTip("请输入英文单词")
            return
        dlg = WordDialog(w, self.speaker, self)
        dlg.exec_()

    def _open_settings(self):
        SettingsDialog(self).exec_()

    # ---------------------------------------------------------------- 拖拽
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        if paths:
            self.goto(0)
            self.home._on_files(paths)
