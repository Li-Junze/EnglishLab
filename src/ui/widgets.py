# -*- coding: utf-8 -*-
"""通用控件：流式布局、卡片、侧栏导航、单词芯片。"""
from __future__ import annotations

from PyQt5.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QCursor, QFont
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLayout, QLayoutItem, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from . import theme


class FlowLayout(QLayout):
    """自动换行的流式布局。"""

    def __init__(self, parent=None, margin=0, hspacing=8, vspacing=8):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.hspacing = hspacing
        self.vspacing = vspacing
        self._items: list[QLayoutItem] = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def clear(self):
        while self._items:
            item = self._items.pop()
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _layout(self, rect, test_only):
        m = self.contentsMargins()
        left = rect.x() + m.left()
        top = rect.y() + m.top()
        width = rect.width() - m.left() - m.right()
        x, y, row_h = left, top, 0
        for item in self._items:
            hint = item.sizeHint()
            # 注意：不要按 isVisible() 跳过子控件——首次布局激活时
            # 子控件尚未标记为可见，会被永久跳过导致全部叠在原位
            if x != left and x + hint.width() > left + width:
                x = left
                y += row_h + self.vspacing
                row_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.hspacing
            row_h = max(row_h, hint.height())
        return y + row_h - rect.y() + m.bottom()


class Card(QFrame):
    def __init__(self, kind="true", parent=None):
        super().__init__(parent)
        self.setProperty("card", kind)


class SectionTitle(QLabel):
    def __init__(self, text, sub="", parent=None):
        super().__init__(parent)
        self.setText(text)
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        self.setFont(f)
        self.setStyleSheet(f"color:{theme.TEXT}; background:transparent;")
        if sub:
            self.setToolTip(sub)


class MutedLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"color:{theme.MUTED}; background:transparent;")
        self.setWordWrap(True)


class NavButton(QPushButton):
    """侧栏导航按钮。dark=True 用于清华紫大色块侧栏（白字）。"""

    def __init__(self, num: str, text: str, parent=None, dark: bool = False):
        super().__init__(parent)
        self._num = num
        self._dark = dark
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(36)
        self.setStyleSheet(
            "QPushButton{background:transparent;border:none;border-radius:9px;text-align:left;padding:0;}"
            "QPushButton:hover{background:#F6EEF9;}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 0, 8, 0)
        lay.setSpacing(8)

        self.badge = QLabel(num)
        self.badge.setFixedSize(20, 20)
        self.badge.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(8)
        f.setBold(True)
        self.badge.setFont(f)

        self.label = QLabel(text)
        self.label.setStyleSheet("background:transparent;")

        lay.addWidget(self.badge)
        lay.addWidget(self.label)
        lay.addStretch(1)
        self.set_active(False)

    def set_active(self, on: bool):
        if self._dark:
            if on:
                # 白底胶囊 + 紫字，在深色块上最醒目
                self.badge.setStyleSheet(
                    f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                    f"stop:0 {theme.ACCENT_2},stop:1 {theme.ACCENT});"
                    "color:#FFFFFF; border-radius:10px;"
                )
                self.label.setStyleSheet(
                    f"color:{theme.ACCENT}; font-weight:600; background:transparent;"
                )
                self.setStyleSheet(
                    "QPushButton{background:#FFFFFF;border:none;border-radius:9px;"
                    "text-align:left;padding:0;}"
                )
            else:
                self.badge.setStyleSheet(
                    "background:rgba(255,255,255,0.18); color:#FFFFFF; border-radius:10px;"
                )
                self.label.setStyleSheet(
                    "color:rgba(255,255,255,0.82); background:transparent;"
                )
                self.setStyleSheet(
                    "QPushButton{background:transparent;border:none;border-radius:9px;"
                    "text-align:left;padding:0;}"
                    "QPushButton:hover{background:rgba(255,255,255,0.12);}"
                )
        elif on:
            self.badge.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {theme.ACCENT_2},"
                f"stop:1 {theme.ACCENT}); color:#FFFFFF; border-radius:10px;"
            )
            self.label.setStyleSheet(
                f"color:{theme.ACCENT}; font-weight:600; background:transparent;"
            )
            self.setStyleSheet(
                "QPushButton{background:#FFFFFF;border:none;border-radius:9px;text-align:left;padding:0;}"
            )
        else:
            self.badge.setStyleSheet(
                f"background:#F1E9F4; color:{theme.TEXT_2}; border-radius:10px;"
            )
            self.label.setStyleSheet(f"color:{theme.TEXT_2}; background:transparent;")
            self.setStyleSheet(
                "QPushButton{background:transparent;border:none;border-radius:9px;text-align:left;padding:0;}"
                "QPushButton:hover{background:#F6EEF9;}"
            )
        self.setChecked(on)


class WordChip(QPushButton):
    """可点击的单词芯片。"""

    clicked_word = pyqtSignal(str)

    def __init__(self, word: str, freq: int = 0, state: str = "new", parent=None):
        super().__init__(parent)
        self.word = word
        self.state = state
        self.freq = freq
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        text = word if not freq else f"{word} · {freq}"
        self.setText(text)
        self.clicked.connect(lambda: self.clicked_word.emit(self.word))
        self.apply_state(state)

    def apply_state(self, state: str):
        self.state = state
        if state == "known":
            bg, fg, bd = "#E6F9F3", "#0F9C7A", "#BFEDE0"
        elif state == "learning":
            bg, fg, bd = theme.ACCENT_SOFT, theme.ACCENT, "#E6D2F0"
        else:
            bg, fg, bd = "#F5F7FD", theme.TEXT_2, theme.BORDER
        self.setStyleSheet(
            f"QPushButton{{background:{bg}; color:{fg}; border:1px solid {bd};"
            f" border-radius:9px; padding:6px 11px; font-size:9.5pt;}}"
            f"QPushButton:hover{{border:1px solid {theme.ACCENT};}}"
        )


class EmptyState(QWidget):
    """居中的空状态提示。"""

    def __init__(self, title: str, desc: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)
        t = QLabel(title)
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        t.setFont(f)
        t.setStyleSheet(f"color:{theme.TEXT_2};background:transparent;")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        if desc:
            d = MutedLabel(desc)
            d.setAlignment(Qt.AlignCenter)
            d.setMaximumWidth(460)
            lay.addWidget(d)
