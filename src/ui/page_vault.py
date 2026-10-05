# -*- coding: utf-8 -*-
"""步骤 5：我的词库 —— 浏览、搜索、手动调整掌握状态、导出。"""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import config, db
from . import theme
from .dialog_export import ExportDialog
from .widgets import Card, MutedLabel, SectionTitle


class VaultPage(QWidget):
    def __init__(self, speaker, parent=None):
        super().__init__(parent)
        self.speaker = speaker
        self._cur_rows: list = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.addWidget(SectionTitle("我的词库"))
        head.addStretch(1)
        self.lbl_stat = MutedLabel("")
        head.addWidget(self.lbl_stat)
        root.addLayout(head)

        bar = Card()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 10, 14, 10)
        bl.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索单词")
        self.search.setFixedWidth(200)
        self.search.setMinimumHeight(32)
        self.search.textChanged.connect(self.refresh)
        bl.addWidget(self.search)

        self.combo = QComboBox()
        self.combo.addItems(["全部", "已掌握", "学习中", "未处理", "已屏蔽"])
        self.combo.setFixedWidth(110)
        self.combo.setMinimumHeight(32)
        self.combo.currentIndexChanged.connect(self.refresh)
        bl.addWidget(self.combo)

        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["按累计出现", "按遇到次数", "按字母序"])
        self.combo_sort.setFixedWidth(120)
        self.combo_sort.setMinimumHeight(32)
        self.combo_sort.currentIndexChanged.connect(self.refresh)
        bl.addWidget(self.combo_sort)

        bl.addStretch(1)
        self.btn_export = QPushButton("导出 / 备份")
        self.btn_export.setProperty("btn", "soft")
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.setMinimumHeight(32)
        self.btn_export.setToolTip("导出成 CSV / Anki / Markdown / JSON，或复制到剪贴板")
        self.btn_export.clicked.connect(self._export)
        bl.addWidget(self.btn_export)
        root.addWidget(bar)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["单词", "状态", "释义", "遇到", "累计出现", "测验", "操作"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._on_dbl)
        root.addWidget(self.table, 1)

    # ---------------------------------------------------------------- 数据
    def refresh(self):
        kw = self.search.text().strip().lower()
        mode = self.combo.currentIndex()
        status_map = {1: db.KNOWN, 2: db.LEARNING, 3: db.NEW}
        status = status_map.get(mode)
        if mode == 4:
            rows = db.blocked_rows(kw)
        else:
            rows = db.all_words(status, kw)

        sort_mode = self.combo_sort.currentIndex()
        if sort_mode == 1:
            rows = sorted(rows, key=lambda r: -r["encounter"])
        elif sort_mode == 2:
            rows = sorted(rows, key=lambda r: r["word"])
        else:
            rows = sorted(rows, key=lambda r: (-r["total_freq"], r["word"]))

        self._cur_rows = list(rows)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["word"]))
            st = r["status"]
            label = {"known": "已掌握", "learning": "学习中", "new": "未处理"}.get(st, st)
            color = {"known": theme.SUCCESS, "learning": theme.ACCENT, "new": theme.MUTED}.get(st)
            it = QTableWidgetItem(label)
            it.setForeground(Qt.black)
            it.setData(Qt.DecorationRole, None)
            it.setTextAlignment(Qt.AlignCenter)
            it.setToolTip(color)
            self.table.setItem(i, 1, it)
            self.table.setItem(i, 2, QTableWidgetItem(r["meaning"] or ""))
            self.table.setItem(i, 3, QTableWidgetItem(str(r["encounter"])))
            self.table.setItem(i, 4, QTableWidgetItem(str(r["total_freq"])))
            self.table.setItem(i, 5, QTableWidgetItem(f"{r['right_cnt']}/{r['wrong_cnt']}"))

            if int(r["blocked"]):
                btn = QPushButton("恢复显示")
                btn.setProperty("btn", "ghost")
                btn.setToolTip("取消屏蔽，重新参与高亮和捕捉")
                btn.setCursor(Qt.PointingHandCursor)
                btn.setMinimumHeight(26)
                btn.clicked.connect(
                    lambda _, w=r["word"]: (db.set_blocked(w, False), self.refresh())
                )
            else:
                btn = QPushButton("移出" if st == db.KNOWN else "已掌握")
                btn.setProperty("btn", "danger" if st == db.KNOWN else "success")
                btn.setCursor(Qt.PointingHandCursor)
                btn.setMinimumHeight(26)
                btn.clicked.connect(lambda _, w=r["word"], s=st: self._toggle(w, s))
            self.table.setCellWidget(i, 6, btn)

        st = db.stats()
        self.lbl_stat.setText(
            f"已掌握 {st['known']}（其中 {st['base']} 个是词汇水准自带的基准词）"
            f" · 学习中 {st['learning'] + st['new']} · 素材 {st['materials']}"
        )

    def _toggle(self, word: str, status: str):
        if status == db.KNOWN:
            db.unmark_known(word)
        else:
            db.mark_known(word, db.ORIGIN_USER)
        self.refresh()

    def _on_dbl(self, row, col):
        item = self.table.item(row, 0)
        if item:
            self.speaker.speak(item.text())

    def _export(self):
        dlg = ExportDialog(db.all_words, lambda: self._cur_rows, self)
        dlg.exec_()
