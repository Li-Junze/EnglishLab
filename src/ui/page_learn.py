# -*- coding: utf-8 -*-
"""步骤 2：学词（对照知识库筛出的生词，逐词学习）。"""
from __future__ import annotations

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import config, db, dictionary
from . import theme
from .widgets import Card, EmptyState, FlowLayout, MutedLabel, SectionTitle


def _mk_btn(text, kind="soft", min_h=32):
    b = QPushButton(text)
    b.setProperty("btn", kind)
    b.setCursor(Qt.PointingHandCursor)
    b.setMinimumHeight(min_h)
    return b


class LearnPage(QWidget):
    finished = pyqtSignal()

    def __init__(self, session, speaker, parent=None):
        super().__init__(parent)
        self.session = session
        self.speaker = speaker
        self._build()

    # ---------------------------------------------------------------- UI
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(14)

        # ---- 顶部进度
        top = QHBoxLayout()
        self.lbl_pos = QLabel("0 / 0")
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        self.lbl_pos.setFont(f)
        self.lbl_pos.setStyleSheet(f"color:{theme.TEXT};background:transparent;")
        top.addWidget(self.lbl_pos)

        self.bar = QProgressBar()
        self.bar.setFixedHeight(9)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(320)
        top.addWidget(self.bar)

        top.addStretch(1)
        self.chk_auto = QPushButton("🔊 自动朗读：开")
        self.chk_auto.setProperty("btn", "soft")
        self.chk_auto.setCheckable(True)
        self.chk_auto.setChecked(True)
        self.chk_auto.setCursor(Qt.PointingHandCursor)
        self.chk_auto.toggled.connect(self._on_auto_toggle)
        top.addWidget(self.chk_auto)
        root.addLayout(top)

        # ---- 主体
        body = QHBoxLayout()
        body.setSpacing(16)

        self.detail = self._build_detail()
        body.addWidget(self.detail, 3)

        right = QVBoxLayout()
        right.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(SectionTitle("生词列表"))
        head.addStretch(1)
        self.btn_only_new = _mk_btn("只看未掌握", "soft", 28)
        self.btn_only_new.setCheckable(True)
        self.btn_only_new.setChecked(True)
        self.btn_only_new.toggled.connect(self.refresh_list)
        head.addWidget(self.btn_only_new)
        right.addLayout(head)

        self.listw = QListWidget()
        self.listw.setSelectionMode(QAbstractItemView.SingleSelection)
        self.listw.itemClicked.connect(self._on_item_clicked)
        right.addWidget(self.listw, 1)
        body.addLayout(right, 2)

        root.addLayout(body, 1)

        # ---- 底部操作
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.btn_prev = _mk_btn("← 上一个", "soft", 38)
        self.btn_next = _mk_btn("下一个 →", "soft", 38)
        self.btn_known = _mk_btn("✓ 已掌握，加入词库", "success", 38)
        self.btn_again = _mk_btn("再看看", "ghost", 38)
        self.btn_finish = _mk_btn("完成，去看视频 →", "primary", 38)
        self.btn_prev.clicked.connect(lambda: self.session.advance(-1))
        self.btn_next.clicked.connect(lambda: self.session.advance(1))
        self.btn_known.clicked.connect(self._mark_known)
        self.btn_again.clicked.connect(self._mark_again)
        self.btn_finish.clicked.connect(self.finished.emit)
        bottom.addWidget(self.btn_prev)
        bottom.addWidget(self.btn_next)
        bottom.addStretch(1)
        bottom.addWidget(self.btn_again)
        bottom.addWidget(self.btn_known)
        bottom.addWidget(self.btn_finish)
        root.addLayout(bottom)

        self.stack_empty = EmptyState("还没有素材", "回到第 1 步，拖入视频和字幕文件")
        root.addWidget(self.stack_empty)

    def _build_detail(self):
        card = Card()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        inner = QWidget()
        theme.self_only(inner, "learn_inner", "background:transparent;")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(12)

        # 单词 + 音标
        h = QHBoxLayout()
        self.lbl_word = QLabel("—")
        f = QFont()
        f.setPointSize(30)
        f.setBold(True)
        self.lbl_word.setFont(f)
        self.lbl_word.setStyleSheet(f"color:{theme.TEXT};background:transparent;")
        h.addWidget(self.lbl_word)

        self.btn_us = _mk_btn("🔊 美音", "ghost", 34)
        self.btn_uk = _mk_btn("🔊 英音", "ghost", 34)
        self.btn_us.clicked.connect(lambda: self.speaker.speak(self._word, "us"))
        self.btn_uk.clicked.connect(lambda: self.speaker.speak(self._word, "uk"))
        h.addStretch(1)
        h.addWidget(self.btn_us)
        h.addWidget(self.btn_uk)
        lay.addLayout(h)

        self.lbl_phone = MutedLabel("")
        self.lbl_phone.setStyleSheet(
            f"color:{theme.TEXT_2};background:transparent;font-size:11pt;"
        )
        lay.addWidget(self.lbl_phone)

        # 标签行
        self.tag_row = QHBoxLayout()
        self.tag_row.setSpacing(8)
        self.tag_box = QWidget()
        theme.self_only(self.tag_box, "learn_tags", "background:transparent;")
        self.tag_box.setLayout(FlowLayout(margin=0, hspacing=8, vspacing=6))
        self.tag_row.addWidget(self.tag_box, 1)
        lay.addLayout(self.tag_row)

        # 释义
        lay.addWidget(self._sec("释义"))
        self.lbl_meaning = QLabel("加载中…")
        self.lbl_meaning.setWordWrap(True)
        self.lbl_meaning.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_meaning.setStyleSheet(
            f"color:{theme.TEXT};background:transparent;font-size:11.5pt;line-height:150%;"
        )
        lay.addWidget(self.lbl_meaning)

        # 英文释义
        self.sec_en = self._sec("英文释义")
        lay.addWidget(self.sec_en)
        self.lbl_en = QLabel("")
        self.lbl_en.setWordWrap(True)
        self.lbl_en.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_en.setStyleSheet(
            f"color:{theme.TEXT_2};background:transparent;font-size:10pt;"
        )
        lay.addWidget(self.lbl_en)

        # 字幕原句
        self.sec_ctx = self._sec("视频里的原句")
        lay.addWidget(self.sec_ctx)
        self.ctx_box = QWidget()
        theme.self_only(self.ctx_box, "learn_ctx", "background:transparent;")
        self.ctx_lay = QVBoxLayout(self.ctx_box)
        self.ctx_lay.setContentsMargins(0, 0, 0, 0)
        self.ctx_lay.setSpacing(6)
        lay.addWidget(self.ctx_box)

        # 例句
        self.sec_ex = self._sec("例句")
        lay.addWidget(self.sec_ex)
        self.ex_box = QWidget()
        theme.self_only(self.ex_box, "learn_ex", "background:transparent;")
        self.ex_lay = QVBoxLayout(self.ex_box)
        self.ex_lay.setContentsMargins(0, 0, 0, 0)
        self.ex_lay.setSpacing(8)
        lay.addWidget(self.ex_box)

        # 词族
        self.sec_rel = self._sec("相关词")
        lay.addWidget(self.sec_rel)
        self.rel_box = QWidget()
        theme.self_only(self.rel_box, "learn_rel", "background:transparent;")
        self.rel_box.setLayout(FlowLayout(margin=0, hspacing=8, vspacing=8))
        lay.addWidget(self.rel_box)

        lay.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return card

    def _sec(self, text) -> QWidget:
        w = QWidget()
        theme.self_only(w, "learn_sec", "background:transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 2)
        lay.setSpacing(8)
        lab = QLabel(text)
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        lab.setFont(f)
        lab.setStyleSheet(f"color:{theme.MUTED};background:transparent;")
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"background:{theme.BORDER};max-height:1px;border:none;")
        lay.addWidget(lab)
        lay.addWidget(line, 1)
        return w

    # ---------------------------------------------------------------- 数据
    def _word(self) -> str:
        return getattr(self, "_word", "")

    @property
    def _word(self) -> str:
        item = self.session.current
        return item["word"] if item else ""

    def bind(self):
        has = bool(self.session.words)
        self.detail.setVisible(has)
        self.listw.setVisible(has)
        self.stack_empty.setVisible(not has)
        self.refresh_list()
        self.refresh()

    def refresh_list(self):
        self.listw.clear()
        only_new = self.btn_only_new.isChecked()
        for i, item in enumerate(self.session.words):
            if only_new and item["status"] == db.KNOWN:
                continue
            row = QListWidgetItem()
            w = self._row_widget(i, item)
            row.setSizeHint(QSize(0, 40))
            self.listw.addItem(row)
            self.listw.setItemWidget(row, w)

    def _row_widget(self, index: int, item: dict):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(8)
        dot = QLabel("●")
        color = theme.SUCCESS if item["status"] == db.KNOWN else theme.ACCENT
        dot.setStyleSheet(f"color:{color};background:transparent;font-size:8pt;")
        dot.setFixedWidth(12)
        name = QLabel(item["word"])
        name.setStyleSheet(f"color:{theme.TEXT};background:transparent;font-size:10pt;")
        freq = QLabel(f"{item['freq']} 次")
        freq.setStyleSheet(f"color:{theme.MUTED};background:transparent;font-size:8.5pt;")
        lay.addWidget(dot)
        lay.addWidget(name, 1)
        lay.addWidget(freq)
        cur = index == self.session.index
        w.setStyleSheet(
            f"QWidget{{background:{'#FFFFFF' if cur else 'transparent'};border-radius:8px;}}"
        )
        w._index = index
        return w

    def _on_item_clicked(self, item):
        w = self.listw.itemWidget(item)
        if w is not None:
            self.session.goto(getattr(w, "_index", 0))

    def refresh(self):
        item = self.session.current
        if not item:
            return
        w = item["word"]
        total = len(self.session.words)
        self.lbl_pos.setText(f"第 {self.session.index + 1} / {total} 个生词")
        done = sum(1 for x in self.session.words if x["status"] == db.KNOWN)
        self.bar.setMaximum(max(1, total))
        self.bar.setValue(done)

        row = db.get_word(w)
        enc = int(row["encounter"]) if row else 0
        cap = int(config.get("encounter_cap", 50))
        thr = int(config.get("auto_master_threshold", 5))

        self.lbl_word.setText(w)
        self.lbl_phone.setText("")
        self.lbl_meaning.setText("正在查询释义…")
        self.lbl_en.setText("")
        self._clear_box(self.ex_lay)
        self._clear_box(self.ctx_lay)
        self._clear_flow(self.rel_box)
        self._clear_flow(self.tag_box)
        self._add_tag(f"本片出现 {item['freq']} 次", theme.ACCENT)
        self._add_tag(f"遇到过 {enc}/{cap}", theme.WARN if enc < thr else theme.SUCCESS)
        if row and row["status"] == db.KNOWN:
            self._add_tag("已掌握", theme.SUCCESS)

        self._load_context(w)
        dictionary.lookup_async(w, self._on_lookup)
        dictionary.prefetch([x["word"] for x in self.session.words[self.session.index + 1:
                                                                   self.session.index + 6]])

    def _load_context(self, w: str):
        rows = db.exposures(w, 3)
        for r in rows:
            txt = r["sentence"]
            zh = dict(r).get("translation") or ""
            card = QFrame()
            card.setProperty("card", "flat")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(12, 9, 12, 9)
            lay.setSpacing(3)
            en = QLabel(self._highlight(txt, w))
            en.setWordWrap(True)
            en.setTextFormat(Qt.RichText)
            en.setStyleSheet(
                f"color:{theme.TEXT};background:transparent;font-size:10.5pt;"
            )
            lay.addWidget(en)
            # 中文只显示字幕自带的对照；不做联网翻译
            if zh:
                cn = QLabel(zh)
                cn.setWordWrap(True)
                cn.setObjectName("ctxZh")
                cn.setStyleSheet(
                    f"color:{theme.MUTED};background:transparent;font-size:9.5pt;"
                )
                lay.addWidget(cn)
            self.ctx_lay.addWidget(card)

    def _highlight(self, sentence: str, word: str) -> str:
        import re
        return re.sub(
            rf"\b({re.escape(word)}\w*)\b",
            rf'<span style="color:{theme.ACCENT};font-weight:600;">\1</span>',
            sentence,
            flags=re.I,
        )

    def _on_lookup(self, word: str, info: dict):
        if word != self._word:
            return
        phone_parts = []
        if info.get("us_phone"):
            phone_parts.append(f"美 /{info['us_phone']}/")
        if info.get("uk_phone"):
            phone_parts.append(f"英 /{info['uk_phone']}/")
        self.lbl_phone.setText("     ".join(phone_parts))

        trs = info.get("translations") or []
        if trs:
            self.lbl_meaning.setText("<br/>".join(f"· {t}" for t in trs[:6]))
        else:
            self.lbl_meaning.setText("（没有查到中文释义，可以手动补充或标记为已掌握）")

        en = info.get("en_defs") or []
        self.sec_en.setVisible(bool(en))
        self.lbl_en.setVisible(bool(en))
        self.lbl_en.setText("<br/>".join(f"· {e}" for e in en[:3]))

        for ex in info.get("examples", [])[:3]:
            card = QFrame()
            card.setProperty("card", "flat")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(12, 9, 12, 9)
            lay.setSpacing(3)
            e1 = QLabel(self._highlight(ex["en"], word))
            e1.setWordWrap(True)
            e1.setTextFormat(Qt.RichText)
            e1.setTextInteractionFlags(Qt.TextSelectableByMouse)
            e1.setStyleSheet(f"color:{theme.TEXT};background:transparent;font-size:10.5pt;")
            lay.addWidget(e1)
            if ex.get("zh"):
                e2 = QLabel(ex["zh"])
                e2.setWordWrap(True)
                e2.setStyleSheet(
                    f"color:{theme.MUTED};background:transparent;font-size:9.5pt;"
                )
                lay.addWidget(e2)
            self.ex_lay.addWidget(card)
        self.sec_ex.setVisible(bool(info.get("examples")))
        self.ex_box.setVisible(bool(info.get("examples")))

        for rel in (info.get("related") or [])[:8]:
            b = QPushButton(rel["word"])
            b.setCursor(Qt.PointingHandCursor)
            tip = " ".join(x for x in (rel.get("pos"), rel.get("tran")) if x)
            if tip:
                b.setToolTip(tip)
            b.setStyleSheet(
                f"QPushButton{{background:{theme.ACCENT_SOFT};color:{theme.ACCENT};"
                f"border:none;border-radius:8px;padding:5px 10px;font-size:9pt;}}"
                f"QPushButton:hover{{background:#F1E2F5;}}"
            )
            b.clicked.connect(lambda _, x=rel["word"]: self._jump_word(x))
            self.rel_box.layout().addWidget(b)
        self.sec_rel.setVisible(bool(info.get("related")))
        self.rel_box.setVisible(bool(info.get("related")))

        if info.get("ok"):
            db.update_info(word, info.get("us_phone", ""), trs[0] if trs else "")
        if self.chk_auto.isChecked():
            self.speaker.speak(word, str(config.get("accent", "us")))

    def _jump_word(self, w: str):
        for i, item in enumerate(self.session.words):
            if item["word"] == w:
                self.session.goto(i)
                return
        self.speaker.speak(w)

    # ---------------------------------------------------------------- 操作
    def _mark_known(self):
        self.session.mark_current(True)
        if self.session.index < len(self.session.words) - 1:
            self.session.advance(1)

    def _mark_again(self):
        self.session.mark_current(False)
        if self.session.index < len(self.session.words) - 1:
            self.session.advance(1)

    def _on_auto_toggle(self, on: bool):
        self.chk_auto.setText(f"🔊 自动朗读：{'开' if on else '关'}")

    # ---------------------------------------------------------------- 工具
    def _clear_box(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _clear_flow(self, box):
        lay = box.layout()
        if lay:
            lay.clear()

    def _add_tag(self, text, color):
        b = QPushButton(text)
        b.setStyleSheet(theme.badge_style(color))
        b.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.tag_box.layout().addWidget(b)
