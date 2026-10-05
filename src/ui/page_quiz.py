# -*- coding: utf-8 -*-
"""步骤 4：根据释义拼写单词，检验学习效果并更新知识库。"""
from __future__ import annotations

import random

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from .. import config, db, dictionary
from . import theme
from .widgets import Card, EmptyState, MutedLabel, SectionTitle


class QuizPage(QWidget):
    finished = pyqtSignal()

    def __init__(self, session, speaker, parent=None):
        super().__init__(parent)
        self.session = session
        self.speaker = speaker
        self.queue: list[str] = []
        self.idx = 0
        self.results: list[dict] = []
        self._hints = 0
        self._build()

    # ---------------------------------------------------------------- UI
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.addWidget(SectionTitle("拼写测验"))
        head.addStretch(1)
        self.lbl_pos = MutedLabel("")
        head.addWidget(self.lbl_pos)
        root.addLayout(head)

        self.bar = QProgressBar()
        self.bar.setFixedHeight(8)
        self.bar.setTextVisible(False)
        root.addWidget(self.bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        host = QWidget()
        theme.self_only(host, "quiz_host", "background:transparent;")
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)

        self.card = Card()
        self.card.setMinimumHeight(300)
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(14)
        cl.setAlignment(Qt.AlignTop)

        self.lbl_mean = QLabel("准备开始")
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        self.lbl_mean.setFont(f)
        self.lbl_mean.setWordWrap(True)
        self.lbl_mean.setAlignment(Qt.AlignCenter)
        self.lbl_mean.setStyleSheet(f"color:{theme.TEXT};background:transparent;")
        cl.addWidget(self.lbl_mean)

        self.lbl_blanks = QLabel("")
        f2 = QFont()
        f2.setPointSize(22)
        f2.setFamily(theme.MONO)
        self.lbl_blanks.setFont(f2)
        self.lbl_blanks.setAlignment(Qt.AlignCenter)
        self.lbl_blanks.setStyleSheet(f"color:{theme.ACCENT};background:transparent;")
        cl.addWidget(self.lbl_blanks)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.input = QLineEdit()
        self.input.setMinimumHeight(44)
        self.input.setPlaceholderText("在这里拼写单词，回车提交")
        f3 = QFont()
        f3.setPointSize(13)
        self.input.setFont(f3)
        self.input.setAlignment(Qt.AlignCenter)
        self.input.returnPressed.connect(self._submit)
        row.addWidget(self.input, 1)
        self.btn_say = QPushButton("🔊")
        self.btn_say.setFixedSize(48, 44)
        self.btn_say.setProperty("btn", "ghost")
        self.btn_say.setCursor(Qt.PointingHandCursor)
        self.btn_say.clicked.connect(self._say)
        row.addWidget(self.btn_say)
        cl.addLayout(row)

        self.lbl_fb = QLabel("")
        self.lbl_fb.setAlignment(Qt.AlignCenter)
        self.lbl_fb.setWordWrap(True)
        self.lbl_fb.setStyleSheet(f"color:{theme.MUTED};background:transparent;")
        cl.addWidget(self.lbl_fb)

        hrow = QHBoxLayout()
        hrow.setSpacing(8)
        self.btn_hint = QPushButton("提示首字母")
        self.btn_hint.setProperty("btn", "soft")
        self.btn_hint.setCursor(Qt.PointingHandCursor)
        self.btn_hint.clicked.connect(self._hint)
        self.btn_skip = QPushButton("不会，跳过")
        self.btn_skip.setProperty("btn", "soft")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        self.btn_skip.clicked.connect(self._skip)
        self.btn_ok = QPushButton("提交")
        self.btn_ok.setProperty("btn", "primary")
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.clicked.connect(self._submit)
        for b in (self.btn_hint, self.btn_skip, self.btn_ok):
            b.setMinimumHeight(36)
        hrow.addWidget(self.btn_hint)
        hrow.addWidget(self.btn_skip)
        hrow.addStretch(1)
        hrow.addWidget(self.btn_ok)
        cl.addLayout(hrow)

        hl.addWidget(self.card)
        hl.addStretch(1)
        self.scroll.setWidget(host)
        root.addWidget(self.scroll, 1)

        # 结果页
        self.result_card = Card()
        rl = QVBoxLayout(self.result_card)
        rl.setContentsMargins(28, 22, 28, 22)
        rl.setSpacing(12)
        self.lbl_score = QLabel("")
        f4 = QFont()
        f4.setPointSize(18)
        f4.setBold(True)
        self.lbl_score.setFont(f4)
        self.lbl_score.setAlignment(Qt.AlignCenter)
        self.lbl_score.setStyleSheet(f"color:{theme.ACCENT};background:transparent;")
        rl.addWidget(self.lbl_score)
        self.lbl_detail = MutedLabel("")
        self.lbl_detail.setAlignment(Qt.AlignCenter)
        rl.addWidget(self.lbl_detail)
        self.wrong_box = QWidget()
        theme.self_only(self.wrong_box, "quiz_wrong", "background:transparent;")
        self.wrong_lay = QVBoxLayout(self.wrong_box)
        self.wrong_lay.setContentsMargins(0, 0, 0, 0)
        self.wrong_lay.setSpacing(6)
        rl.addWidget(self.wrong_box)

        brow = QHBoxLayout()
        self.btn_retry = QPushButton("只重测错的词")
        self.btn_retry.setProperty("btn", "soft")
        self.btn_retry.setCursor(Qt.PointingHandCursor)
        self.btn_retry.clicked.connect(self._retry_wrong)
        self.btn_done = QPushButton("完成，更新词库 →")
        self.btn_done.setProperty("btn", "primary")
        self.btn_done.setCursor(Qt.PointingHandCursor)
        self.btn_done.clicked.connect(self.finished.emit)
        for b in (self.btn_retry, self.btn_done):
            b.setMinimumHeight(38)
        brow.addWidget(self.btn_retry)
        brow.addStretch(1)
        brow.addWidget(self.btn_done)
        rl.addLayout(brow)
        self.result_card.hide()
        root.addWidget(self.result_card)

        self.empty = EmptyState("还没有可测的词", "先完成前两步：导入素材并学词")
        root.addWidget(self.empty)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_start = QPushButton("开始测验")
        self.btn_start.setProperty("btn", "primary")
        self.btn_start.setMinimumHeight(38)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.start)
        bottom.addWidget(self.btn_start)
        root.addLayout(bottom)

    # ---------------------------------------------------------------- 流程
    def refresh(self):
        has = bool(self.session.words)
        self.scroll.setVisible(has and not self.session.quiz_done)
        self.result_card.setVisible(has and self.session.quiz_done)
        self.empty.setVisible(not has)
        self.btn_start.setVisible(has)

    def start(self, words: list[str] | None = None):
        pool = words or self.session.quiz_words()
        if not pool:
            return
        self.queue = pool[:]
        random.shuffle(self.queue)
        self.idx = 0
        self.results = []
        self.session.quiz_done = False
        self.result_card.hide()
        self.scroll.show()
        self.btn_start.hide()
        self._render()

    def _render(self):
        if self.idx >= len(self.queue):
            self._finish()
            return
        w = self.queue[self.idx]
        self.lbl_pos.setText(f"第 {self.idx + 1} / {len(self.queue)} 题")
        self.bar.setMaximum(len(self.queue))
        self.bar.setValue(self.idx)
        self._hints = 0
        self.input.clear()
        self.input.setEnabled(True)
        self.input.setFocus()
        self.lbl_fb.setText("")
        self.lbl_fb.setStyleSheet(f"color:{theme.MUTED};background:transparent;")
        self.lbl_blanks.setText(" ".join("_" for _ in w))
        self.lbl_mean.setText("加载释义…")
        self._current = w
        dictionary.lookup_async(w, self._on_info)

    def _on_info(self, word, info):
        if word != getattr(self, "_current", None):
            return
        trs = info.get("translations") or []
        txt = trs[0] if trs else (info.get("en_defs") or [""])[0]
        self.lbl_mean.setText(txt or word)
        if info.get("us_phone"):
            self.lbl_mean.setText(f"{txt}\n/{info['us_phone']}/")
        db.update_info(word, info.get("us_phone", ""), trs[0] if trs else "")

    def _say(self):
        w = getattr(self, "_current", "")
        if w:
            self.speaker.speak(w)

    def _hint(self):
        w = getattr(self, "_current", "")
        if not w:
            return
        self._hints += 1
        n = min(self._hints + 1, len(w))
        shown = w[:n] + " " * 0
        self.lbl_blanks.setText(" ".join(list(shown) + ["_"] * (len(w) - n)))

    def _skip(self):
        self._record(False, skipped=True)

    def _submit(self):
        w = getattr(self, "_current", "")
        if not w:
            return
        ans = self.input.text().strip().lower()
        ok = ans == w
        self._record(ok, answer=ans)

    def _record(self, ok: bool, answer: str = "", skipped: bool = False):
        w = getattr(self, "_current", "")
        if not w:
            return
        self.input.setEnabled(False)
        db.record_quiz(w, ok)
        db.bump_encounter(w, 1)
        self.results.append({"word": w, "ok": ok, "answer": answer, "skipped": skipped})
        if ok:
            self.lbl_fb.setText("✓ 正确")
            self.lbl_fb.setStyleSheet(
                f"color:{theme.SUCCESS};background:transparent;font-size:12pt;font-weight:600;"
            )
        else:
            self.lbl_fb.setText(f"✗ 正确答案：{w}" + (f"（你写了 {answer}）" if answer else ""))
            self.lbl_fb.setStyleSheet(
                f"color:{theme.DANGER};background:transparent;font-size:12pt;font-weight:600;"
            )
        self.lbl_blanks.setText(" ".join(list(w)))
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(900 if ok else 1600, self._next)

    def _next(self):
        self.idx += 1
        self._render()

    def _finish(self):
        self.session.quiz_done = True
        self.scroll.hide()
        self.result_card.show()
        self.btn_start.show()
        self.btn_start.setText("再来一轮")
        right = sum(1 for r in self.results if r["ok"])
        total = len(self.results)
        rate = int(right * 100 / total) if total else 0
        self.lbl_score.setText(f"{rate}%   ({right}/{total})")
        self.lbl_detail.setText(
            "答对的词已累计一次遇到记录，达到阈值会自动纳入知识库；答错的词保留在学习列表中"
        )
        while self.wrong_lay.count():
            it = self.wrong_lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        wrongs = [r["word"] for r in self.results if not r["ok"]]
        if wrongs:
            lab = QLabel("需要再看一眼：")
            lab.setStyleSheet(f"color:{theme.TEXT_2};background:transparent;font-weight:600;")
            self.wrong_lay.addWidget(lab)
            row = QHBoxLayout()
            row.setSpacing(6)
            from .widgets import FlowLayout
            box = QWidget()
            theme.self_only(box, "quiz_wrong_row", "background:transparent;")
            box.setLayout(FlowLayout(margin=0))
            for w in wrongs:
                b = QPushButton(w)
                b.setCursor(Qt.PointingHandCursor)
                b.setStyleSheet(
                    f"QPushButton{{background:#FFF0F3;color:{theme.DANGER};border:none;"
                    f"border-radius:8px;padding:5px 10px;font-size:9.5pt;}}"
                )
                b.clicked.connect(lambda _, x=w: self.speaker.speak(x))
                box.layout().addWidget(b)
            self.wrong_lay.addWidget(box)
        else:
            lab = QLabel("全部正确，漂亮 🎉")
            lab.setStyleSheet(f"color:{theme.SUCCESS};background:transparent;font-weight:600;")
            self.wrong_lay.addWidget(lab)
        self._wrongs = wrongs

    def _retry_wrong(self):
        wrongs = getattr(self, "_wrongs", [])
        if wrongs:
            self.start(wrongs)
        else:
            self.start(self.session.quiz_words())
