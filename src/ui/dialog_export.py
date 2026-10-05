# -*- coding: utf-8 -*-
"""导出知识库：选范围、选格式，一键落盘或复制到剪贴板。"""
from __future__ import annotations

import json
import os
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from .. import config, db
from . import theme
from .widgets import Card, MutedLabel, SectionTitle

SCOPE_ALL = "all"
SCOPE_FILTERED = "filtered"
SCOPE_ACTIVE = "active"


def _csv_cell(v) -> str:
    s = str(v).replace("\n", " ").replace("\r", " ")
    if any(c in s for c in (",", '"')):
        s = '"' + s.replace('"', '""') + '"'
    return s


class ExportDialog(QDialog):
    FORMATS = [
        ("csv", "CSV（Excel / 数字表格直接打开）", "csv"),
        ("anki", "TSV（Anki 直接导入）", "txt"),
        ("md", "Markdown 表格（贴进笔记）", "md"),
        ("json", "JSON（给别的程序用）", "json"),
        ("txt", "纯文本（只有单词）", "txt"),
    ]

    def __init__(self, fetch_all, fetch_filtered, parent=None):
        super().__init__(parent)
        self.fetch_all = fetch_all
        self.fetch_filtered = fetch_filtered
        self.setWindowTitle("导出知识库")
        self.setMinimumWidth(580)
        self.setStyleSheet(f"QDialog{{background:{theme.BG};}}")
        self._build()

    # ---------------------------------------------------------------- UI
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        root.addWidget(SectionTitle("导出知识库"))

        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        lay.addLayout(self._row(
            "导出范围", self._mk_combo(
                "combo_scope",
                [("当前筛选的词（推荐）", SCOPE_FILTERED),
                 ("全部词条", SCOPE_ALL),
                 ("只要还没掌握的词", SCOPE_ACTIVE)],
                self._preview,
            )))
        lay.addLayout(self._row(
            "文件格式",
            self._mk_combo(
                "combo_fmt",
                [(name, key) for key, name, _ext in self.FORMATS],
                self._on_fmt,
            )))

        self.chk_example = QCheckBox("附带视频原句（从你看过的素材里取）")
        self.chk_example.setChecked(True)
        self.chk_example.setStyleSheet(f"color:{theme.TEXT_2};background:transparent;")
        self.chk_example.toggled.connect(self._preview)
        lay.addWidget(self.chk_example)

        self.lbl_preview = MutedLabel("")
        self.lbl_preview.setWordWrap(True)
        lay.addWidget(self.lbl_preview)
        root.addWidget(card)

        path_card = Card()
        pl = QHBoxLayout(path_card)
        pl.setContentsMargins(14, 10, 14, 10)
        pl.setSpacing(8)
        self.edit_path = QLineEdit()
        self.edit_path.setMinimumHeight(32)
        pl.addWidget(self.edit_path, 1)
        btn_browse = QPushButton("浏览")
        btn_browse.setProperty("btn", "ghost")
        btn_browse.setMinimumHeight(32)
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.clicked.connect(self._browse)
        pl.addWidget(btn_browse)
        root.addWidget(path_card)

        bottom = QHBoxLayout()
        btn_copy = QPushButton("复制到剪贴板")
        btn_copy.setProperty("btn", "soft")
        btn_copy.setMinimumHeight(34)
        btn_copy.setCursor(Qt.PointingHandCursor)
        btn_copy.setToolTip("不生成文件，直接把内容拷出来粘贴")
        btn_copy.clicked.connect(self._copy)
        bottom.addWidget(btn_copy)
        bottom.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setProperty("btn", "soft")
        ok = QPushButton("导出")
        ok.setProperty("btn", "primary")
        for b in (cancel, ok):
            b.setMinimumHeight(34)
            b.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._save)
        bottom.addWidget(cancel)
        bottom.addWidget(ok)
        root.addLayout(bottom)

        self._suggest_path()
        self._preview()

    def _mk_combo(self, attr: str, items, slot):
        cb = QComboBox()
        for name, data in items:
            cb.addItem(name, data)
        cb.setMinimumHeight(32)
        cb.currentIndexChanged.connect(slot)
        setattr(self, attr, cb)
        return cb

    def _row(self, title: str, widget) -> QHBoxLayout:
        r = QHBoxLayout()
        lab = QLabel(title)
        lab.setFixedWidth(90)
        lab.setStyleSheet(f"color:{theme.TEXT_2};background:transparent;")
        r.addWidget(lab)
        r.addWidget(widget, 1)
        return r

    # ---------------------------------------------------------------- 数据
    def _rows(self):
        scope = self.combo_scope.currentData()
        rows = self.fetch_all()
        if not rows:
            return []
        if scope == SCOPE_ALL:
            return rows
        if scope == SCOPE_ACTIVE:
            return [r for r in rows if r["status"] != db.KNOWN]
        filtered = self.fetch_filtered()
        return filtered or rows

    def _fmt_key(self) -> str:
        return self.combo_fmt.currentData() or "csv"

    def _ext(self) -> str:
        for key, _n, ext in self.FORMATS:
            if key == self._fmt_key():
                return ext
        return "csv"

    def _example_of(self, rows_cache: dict, word: str) -> str:
        if not self.chk_example.isChecked():
            return ""
        if word not in rows_cache:
            rows_cache[word] = ""
            ex = db.exposures(word, 1)
            if ex:
                rows_cache[word] = ex[0]["sentence"].replace("\n", " ").strip()
        return rows_cache[word]

    def render_text(self) -> str:
        rows = self._rows()
        key = self._fmt_key()
        with_ex = self.chk_example.isChecked()
        ex_cache: dict[str, str] = {}

        if key == "csv":
            head = ["word", "phonetic", "meaning", "status", "encounter",
                    "total_freq", "quiz_right", "quiz_wrong"]
            if with_ex:
                head.append("example")
            out = [",".join(head)]
            for r in rows:
                vals = [r["word"], r["phonetic"], r["meaning"], r["status"],
                        r["encounter"], r["total_freq"], r["right_cnt"], r["wrong_cnt"]]
                if with_ex:
                    vals.append(self._example_of(ex_cache, r["word"]))
                out.append(",".join(_csv_cell(v) for v in vals))
            return "\n".join(out)

        if key == "anki":
            out = []
            for r in rows:
                fields = [r["word"], r["phonetic"], r["meaning"] or "",
                          self._example_of(ex_cache, r["word"])]
                out.append("\t".join(str(f).replace("\t", " ") for f in fields))
            return "\n".join(out)

        if key == "json":
            payload = []
            for r in rows:
                d = {
                    "word": r["word"], "phonetic": r["phonetic"],
                    "meaning": r["meaning"], "status": r["status"],
                    "encounter": int(r["encounter"]),
                    "total_freq": int(r["total_freq"]),
                    "quiz": {"right": int(r["right_cnt"]), "wrong": int(r["wrong_cnt"])},
                }
                if with_ex:
                    d["example"] = self._example_of(ex_cache, r["word"])
                payload.append(d)
            return json.dumps(payload, ensure_ascii=False, indent=2)

        if key == "md":
            if with_ex:
                out = ["| 单词 | 音标 | 释义 | 例句 | 状态 |",
                       "| --- | --- | --- | --- | --- |"]
            else:
                out = ["| 单词 | 音标 | 释义 | 状态 |", "| --- | --- | --- | --- |"]
            for r in rows:
                cells = [r["word"], r["phonetic"], (r["meaning"] or "").replace("|", "/")]
                if with_ex:
                    cells.append(self._example_of(ex_cache, r["word"]).replace("|", "/"))
                cells.append(r["status"])
                out.append("| " + " | ".join(str(c).replace("\n", " ") for c in cells) + " |")
            return "\n".join(out)

        return "\n".join(r["word"] for r in rows)

    # ---------------------------------------------------------------- 交互
    def _suggest_path(self):
        desk = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desk):
            desk = config.DATA_DIR
        stamp = datetime.now().strftime("%Y%m%d")
        self.edit_path.setText(
            os.path.join(desk, f"EnglishLab-词库-{stamp}.{self._ext()}")
        )

    def _preview(self):
        rows = self._rows()
        size = len(self.render_text().encode("utf-8"))
        kb = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
        self.lbl_preview.setText(f"将导出 {len(rows)} 个词 · {kb}")

    def _on_fmt(self):
        old = self.edit_path.text().strip()
        if not old:
            self._suggest_path()
            return
        self.edit_path.setText(f"{os.path.splitext(old)[0]}.{self._ext()}")
        self._preview()

    def _browse(self):
        ext = self._ext()
        p, _ = QFileDialog.getSaveFileName(
            self, "导出到", self.edit_path.text(), f"{ext.upper()} 文件 (*.{ext});;所有文件 (*.*)"
        )
        if p:
            self.edit_path.setText(p)

    def _copy(self):
        QApplication.clipboard().setText(self.render_text())
        QMessageBox.information(self, "已复制", "内容已放进剪贴板，直接粘贴即可")

    def _save(self):
        p = self.edit_path.text().strip()
        if not p:
            QMessageBox.information(self, "还没选位置", "先填一个文件路径")
            return
        rows = self._rows()
        txt = self.render_text()
        encoding = "utf-8-sig" if self._fmt_key() == "csv" else "utf-8"
        try:
            with open(p, "w", encoding=encoding, newline="\n") as f:
                f.write(txt)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return

        box = QMessageBox(self)
        box.setWindowTitle("导出完成")
        box.setText(f"已导出 {len(rows)} 个词：\n{p}")
        btn_open = box.addButton("打开文件夹", QMessageBox.ActionRole)
        btn_file = box.addButton("打开文件", QMessageBox.ActionRole)
        box.addButton("关闭", QMessageBox.AcceptRole)
        box.exec_()
        clicked = box.clickedButton()
        try:
            if clicked is btn_open:
                os.startfile(os.path.dirname(p))
            elif clicked is btn_file:
                os.startfile(p)
        except Exception:
            pass
        self.accept()
