# -*- coding: utf-8 -*-
"""弹窗：单词详情、设置。"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from .. import config, db, dictionary, vocab
from . import theme
from .widgets import Card, MutedLabel, SectionTitle


class WordDialog(QDialog):
    """单词详情：可随时查询并决定是否纳入知识库。"""

    def __init__(self, word: str, speaker, parent=None):
        super().__init__(parent)
        self.word = word.lower()
        self.speaker = speaker
        self.setWindowTitle(f"单词 · {self.word}")
        self.setMinimumSize(560, 460)
        self.resize(620, 520)
        self.setStyleSheet(f"QDialog{{background:{theme.BG};}}")
        self._build()
        dictionary.lookup_async(self.word, self._on_info)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)

        h = QHBoxLayout()
        self.lbl_word = QLabel(self.word)
        f = QFont()
        f.setPointSize(24)
        f.setBold(True)
        self.lbl_word.setFont(f)
        self.lbl_word.setStyleSheet(f"color:{theme.TEXT};background:transparent;")
        h.addWidget(self.lbl_word)
        h.addStretch(1)
        b1 = QPushButton("🔊 美音")
        b2 = QPushButton("🔊 英音")
        for b in (b1, b2):
            b.setProperty("btn", "ghost")
            b.setCursor(Qt.PointingHandCursor)
        b1.clicked.connect(lambda: self.speaker.speak(self.word, "us"))
        b2.clicked.connect(lambda: self.speaker.speak(self.word, "uk"))
        h.addWidget(b1)
        h.addWidget(b2)
        lay.addLayout(h)

        self.lbl_phone = MutedLabel("")
        lay.addWidget(self.lbl_phone)

        self.lbl_mean = QLabel("查询中…")
        self.lbl_mean.setWordWrap(True)
        self.lbl_mean.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_mean.setStyleSheet(
            f"color:{theme.TEXT};background:transparent;font-size:11pt;"
        )
        lay.addWidget(self.lbl_mean)

        self.lbl_en = MutedLabel("")
        self.lbl_en.setWordWrap(True)
        lay.addWidget(self.lbl_en)

        self.lbl_stat = MutedLabel("")
        lay.addWidget(self.lbl_stat)

        root.addWidget(card)

        self.ex_box = QWidget()
        theme.self_only(self.ex_box, "dlg_ex", "background:transparent;")
        self.ex_lay = QVBoxLayout(self.ex_box)
        self.ex_lay.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.ex_box, 1)

        root.addStretch(0)

        bottom = QHBoxLayout()
        self.btn_known = QPushButton("加入知识库（已掌握）")
        self.btn_known.setProperty("btn", "success")
        self.btn_unknown = QPushButton("移出知识库")
        self.btn_unknown.setProperty("btn", "danger")
        close = QPushButton("关闭")
        close.setProperty("btn", "soft")
        for b in (self.btn_known, self.btn_unknown, close):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(34)
        self.btn_known.clicked.connect(self._add)
        self.btn_unknown.clicked.connect(self._remove)
        close.clicked.connect(self.accept)
        bottom.addWidget(self.btn_unknown)
        bottom.addStretch(1)
        bottom.addWidget(close)
        bottom.addWidget(self.btn_known)
        root.addLayout(bottom)
        self._sync_buttons()

    def _on_info(self, word, info):
        if word != self.word:
            return
        parts = []
        if info.get("us_phone"):
            parts.append(f"美 /{info['us_phone']}/")
        if info.get("uk_phone"):
            parts.append(f"英 /{info['uk_phone']}/")
        self.lbl_phone.setText("    ".join(parts))
        trs = info.get("translations") or []
        self.lbl_mean.setText("<br/>".join(f"· {t}" for t in trs[:8]) or "（无释义）")
        en = info.get("en_defs") or []
        self.lbl_en.setText("<br/>".join(f"· {e}" for e in en[:3]))
        for ex in (info.get("examples") or [])[:3]:
            c = QFrame()
            c.setProperty("card", "flat")
            l = QVBoxLayout(c)
            l.setContentsMargins(12, 9, 12, 9)
            a = QLabel(ex["en"])
            a.setWordWrap(True)
            a.setTextInteractionFlags(Qt.TextSelectableByMouse)
            a.setStyleSheet(f"color:{theme.TEXT};background:transparent;")
            l.addWidget(a)
            if ex.get("zh"):
                b = QLabel(ex["zh"])
                b.setWordWrap(True)
                b.setStyleSheet(f"color:{theme.MUTED};background:transparent;")
                l.addWidget(b)
            self.ex_lay.addWidget(c)

    def _sync_buttons(self):
        known = db.is_known(self.word)
        self.btn_known.setVisible(not known)
        self.btn_unknown.setVisible(known)
        row = db.get_word(self.word)
        if row:
            self.lbl_stat.setText(
                f"状态：{'已掌握' if row['status'] == db.KNOWN else '学习中'}"
                f" · 遇到过 {row['encounter']} 次 · 累计出现 {row['total_freq']} 次"
                f" · 测验 对 {row['right_cnt']} 错 {row['wrong_cnt']}"
            )
        else:
            self.lbl_stat.setText("这个词还没有进入你的词库")

    def _add(self):
        db.mark_known(self.word, db.ORIGIN_USER)
        self._sync_buttons()
        if self.parent():
            try:
                self.parent().refresh_all()
            except Exception:
                pass

    def _remove(self):
        db.unmark_known(self.word)
        self._sync_buttons()
        if self.parent():
            try:
                self.parent().refresh_all()
            except Exception:
                pass


class AboutDialog(QDialog):
    """联网与用量说明 —— 说清楚哪些地方要上网、要不要钱。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("联网与用量说明")
        self.setMinimumWidth(560)
        self.setStyleSheet(f"QDialog{{background:{theme.BG};}}")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        head = Card()
        hl = QVBoxLayout(head)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(6)
        t = QLabel("English Lab 是纯本地程序")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        t.setFont(f)
        t.setStyleSheet(f"color:{theme.TEXT};background:transparent;")
        hl.addWidget(t)
        sub = QLabel(
            "你的词库存放在本机 data/lexicon.db。整个学习流程（筛词、高亮、"
            "掌握度、测验、导出）都是本地计算，\n默认不需要联网。"
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{theme.TEXT_2};background:transparent;font-size:9.5pt;")
        hl.addWidget(sub)
        root.addWidget(head)

        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(10)
        lay.addWidget(SectionTitle("只有两件事会联网"))

        rows = [
            ("查单词（音标/释义/例句）",
             "有道公开词典接口 dict.youdao.com，免费、无需注册"),
            ("朗读发音",
             "有道 dictvoice 下载 mp3，第一次听过就存到 data/cache/audio"),
        ]
        for name, detail in rows:
            lay.addLayout(self._kv(name, detail))

        note = QLabel(
            "这两个接口都是公开免费的，不需要 API Key，不涉及任何大模型，\n"
            "所以不会消耗 token、没有账号额度，也不上传你的任何文件内容。\n"
            "查询结果写入词典缓存，同一个词只会请求一次。\n"
            "句子释义本来就不需要：整句翻译已移除，只显示字幕自带的中文对照。"
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.MUTED};background:transparent;font-size:9pt;")
        lay.addWidget(note)
        root.addWidget(card)

        card2 = Card()
        l2 = QVBoxLayout(card2)
        l2.setContentsMargins(20, 14, 20, 14)
        l2.setSpacing(10)
        l2.addWidget(SectionTitle("断网会怎样"))
        l2.addLayout(self._kv(
            "照样能用",
            "导入字幕、筛生词、看视频、字幕高亮、标记掌握、拼写测验、导出词表 "
            "全部正常（发音和释义需要联网，视频播放走本机 ffmpeg）",
        ))
        l2.addLayout(self._kv(
            "会缺的部分",
            "单词没有中文释义、点发音没声音（双语字幕的中文照常显示）；\n"
            "联网后重开软件（或重新触发查词）会自动补上并缓存",
        ))
        root.addWidget(card2)

        bottom = QHBoxLayout()
        btn = QPushButton("知道了")
        btn.setProperty("btn", "primary")
        btn.setMinimumHeight(34)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.accept)
        bottom.addStretch(1)
        bottom.addWidget(btn)
        root.addLayout(bottom)

    def _kv(self, name: str, detail: str):
        row = QHBoxLayout()
        row.setSpacing(12)
        n = QLabel(name)
        n.setFixedWidth(150)
        n.setWordWrap(True)
        n.setStyleSheet(f"color:{theme.TEXT};background:transparent;font-weight:600;")
        d = QLabel(detail)
        d.setWordWrap(True)
        d.setStyleSheet(f"color:{theme.MUTED};background:transparent;font-size:9pt;")
        row.addWidget(n, 0)
        row.addWidget(d, 1)
        return row


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(520)
        self.setStyleSheet(f"QDialog{{background:{theme.BG};}}")
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        # ------------------------------------------------ 卡片 1：词汇水准
        card_lv = Card()
        cl = QVBoxLayout(card_lv)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(10)
        cl.addWidget(SectionTitle("词汇水准"))

        row = QHBoxLayout()
        row.setSpacing(10)
        self.combo_level = QComboBox()
        for lv in vocab.LEVELS:
            self.combo_level.addItem(lv["name"], lv["key"])
        cur = vocab.current_level_key()
        idx = max(0, [lv["key"] for lv in vocab.LEVELS].index(cur))
        self.combo_level.setCurrentIndex(idx)
        self.combo_level.setMinimumHeight(32)
        self.combo_level.currentIndexChanged.connect(self._level_desc)
        row.addWidget(self.combo_level, 1)

        self.btn_apply_level = QPushButton("切换水准")
        self.btn_apply_level.setProperty("btn", "primary")
        self.btn_apply_level.setCursor(Qt.PointingHandCursor)
        self.btn_apply_level.setMinimumHeight(32)
        self.btn_apply_level.clicked.connect(self._apply_level)
        row.addWidget(self.btn_apply_level)
        cl.addLayout(row)

        self.lbl_level = MutedLabel("")
        self.lbl_level.setWordWrap(True)
        cl.addWidget(self.lbl_level)

        self.lbl_lib = MutedLabel("")
        cl.addWidget(self.lbl_lib)
        self._level_desc()
        root.addWidget(card_lv)

        # ------------------------------------------------ 卡片 2：学习参数
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(SectionTitle("学习参数"))

        self.spin_thr = self._row_int(
            lay, "自动掌握阈值", "遇到次数达到该值后，自动纳入知识库", 1, 50,
            int(config.get("auto_master_threshold", 5)),
        )
        self.spin_cap = self._row_int(
            lay, "遇到次数上限", "统计到该次数后停止累加", 5, 999,
            int(config.get("encounter_cap", 50)),
        )
        self.spin_max = self._row_int(
            lay, "单素材生词上限", "一个素材最多筛出多少生词", 5, 300,
            int(config.get("max_new_words", 60)),
        )
        self.spin_quiz = self._row_int(
            lay, "测验题量", "每轮拼写测验的题目数", 5, 100,
            int(config.get("quiz_size", 20)),
        )
        self.spin_len = self._row_int(
            lay, "最短词长", "短于该长度的单词忽略不计", 2, 8,
            int(config.get("min_word_len", 3)),
        )
        self.spin_panel = self._row_int(
            lay, "生词面板保留条数", "看视频时右侧面板最多保留多少个词", 10, 200,
            int(config.get("recent_panel_size", 40)),
        )

        self.chk_known = self._row_switch(
            lay, "已掌握的词也标注", "已掌握的词在字幕里用淡色标出，方便确认语境",
            int(config.get("highlight_known", 0)),
        )

        row = QHBoxLayout()
        lab = QLabel("发音偏好")
        lab.setStyleSheet(f"color:{theme.TEXT_2};background:transparent;")
        self.combo = QComboBox()
        self.combo.addItems(["美音 (us)", "英音 (uk)"])
        self.combo.setCurrentIndex(0 if config.get("accent", "us") == "us" else 1)
        row.addWidget(lab)
        row.addWidget(self.combo, 1)
        lay.addLayout(row)

        root.addWidget(card)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.btn_reset = QPushButton("重置知识库")
        self.btn_reset.setProperty("btn", "danger")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setMinimumHeight(34)
        self.btn_reset.setToolTip("清空所有学词记录，回到第一次打开的状态")
        self.btn_reset.clicked.connect(self._reset)
        bar.addWidget(self.btn_reset)

        btn_clear = QPushButton("清除词典缓存")
        btn_clear.setProperty("btn", "danger")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setMinimumHeight(34)
        btn_clear.clicked.connect(self._clear)
        bar.addWidget(btn_clear)
        bar.addStretch(1)

        btn_about = QPushButton("联网与用量说明")
        btn_about.setProperty("btn", "ghost")
        btn_about.setCursor(Qt.PointingHandCursor)
        btn_about.setMinimumHeight(34)
        btn_about.clicked.connect(self._about)
        bar.addWidget(btn_about)

        cancel = QPushButton("取消")
        cancel.setProperty("btn", "soft")
        ok = QPushButton("保存")
        ok.setProperty("btn", "primary")
        for b in (cancel, ok):
            b.setMinimumHeight(34)
            b.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._save)
        bar.addWidget(cancel)
        bar.addWidget(ok)
        root.addLayout(bar)

    # ---------------------------------------------------------------- 词汇水准
    def _level_desc(self):
        key = self.combo_level.currentData()
        lv = vocab.level_by_key(key)
        self.lbl_level.setText(
            f"{lv['desc']}。基准对该档位以下的词不再弹出；"
            f"切换只影响「没有学习痕迹」的词，你手动标记和测试过的都留着。"
        )
        st = db.stats()
        self.lbl_lib.setText(
            f"当前知识库：已掌握 {st['known']}（其中 {st['base']} 个是基准词，"
            f"你真正学到的是 {st['known'] - st['base']} 个）"
            f" · 学习中 {st['learning'] + st['new']} · 素材 {st['materials']} 条"
        )

    def _apply_level(self):
        key = self.combo_level.currentData()
        self.btn_apply_level.setEnabled(False)
        self.btn_apply_level.setText("正在重建词表…")
        QApplication.processEvents()
        try:
            res = vocab.set_level(key, write_db=True)
        finally:
            self.btn_apply_level.setEnabled(True)
            self.btn_apply_level.setText("切换水准")
        self._level_desc()
        self.combo_level.setToolTip(f"已切换到 {vocab.level_by_key(key)['name']}")
        QMessageBox.information(
            self, "已切换",
            f"词汇水准：{vocab.level_by_key(key)['name']}\n\n"
            f"基准词 {res['known']} 个，其中新写入 {res.get('added', 0)} 个、"
            f"回收 {res.get('removed', 0)} 个、恢复 {res.get('revived', 0)} 个。\n\n"
            f"如果现在正在看素材，字幕和右侧面板会立刻按新水准重新筛选。",
        )
        try:
            if self.parent():
                self.parent().refresh_all()
        except Exception:
            pass

    def _reset(self):
        key = self.combo_level.currentData()
        lv = vocab.level_by_key(key)
        r = QMessageBox.warning(
            self, "确认重置知识库",
            f"这会删除全部 {db.stats()['known'] + db.stats()['learning'] + db.stats()['new']} "
            "条词条、所有曝光记录和素材历史，并按\n\n"
            f"「{lv['name']}」\n\n"
            "重新灌入基准词。\n\n此操作不可撤销，建议先到「我的词库」导出备份。确定继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if r != QMessageBox.Yes:
            return
        self.btn_reset.setEnabled(False)
        self.btn_reset.setText("正在重置…")
        QApplication.processEvents()
        try:
            vocab.reset_knowledge(key)
        finally:
            self.btn_reset.setEnabled(True)
            self.btn_reset.setText("重置知识库")
        self._level_desc()
        QMessageBox.information(self, "已重置", "知识库已恢复到初始状态。")
        try:
            if self.parent():
                self.parent().refresh_all()
        except Exception:
            pass

    def _about(self):
        AboutDialog(self).exec_()

    def _row_int(self, lay, title, desc, lo, hi, val):
        row = QHBoxLayout()
        box = QVBoxLayout()
        box.setSpacing(0)
        t = QLabel(title)
        t.setStyleSheet(f"color:{theme.TEXT};background:transparent;font-weight:600;")
        d = QLabel(desc)
        d.setStyleSheet(f"color:{theme.MUTED};background:transparent;font-size:8.5pt;")
        box.addWidget(t)
        box.addWidget(d)
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(val)
        sp.setFixedWidth(90)
        row.addLayout(box, 1)
        row.addWidget(sp)
        lay.addLayout(row)
        return sp

    def _row_switch(self, lay, title, desc, val: int):
        row = QHBoxLayout()
        box = QVBoxLayout()
        box.setSpacing(0)
        t = QLabel(title)
        t.setStyleSheet(f"color:{theme.TEXT};background:transparent;font-weight:600;")
        d = QLabel(desc)
        d.setStyleSheet(f"color:{theme.MUTED};background:transparent;font-size:8.5pt;")
        box.addWidget(t)
        box.addWidget(d)
        chk = QCheckBox()
        chk.setChecked(bool(val))
        chk.setFixedWidth(60)
        row.addLayout(box, 1)
        row.addWidget(chk)
        lay.addLayout(row)
        return chk

    def _clear(self):
        db.clear_cache()

    def _save(self):
        config.save_settings(
            {
                "auto_master_threshold": self.spin_thr.value(),
                "encounter_cap": self.spin_cap.value(),
                "max_new_words": self.spin_max.value(),
                "quiz_size": self.spin_quiz.value(),
                "min_word_len": self.spin_len.value(),
                "recent_panel_size": self.spin_panel.value(),
                "highlight_known": 1 if self.chk_known.isChecked() else 0,
                "accent": "us" if self.combo.currentIndex() == 0 else "uk",
            }
        )
        self.accept()
