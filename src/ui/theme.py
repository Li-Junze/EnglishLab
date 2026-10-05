# -*- coding: utf-8 -*-
"""视觉主题：配色常量 + 全局 QSS。"""
from __future__ import annotations

BG = "#F4F6FB"
PANEL = "#FFFFFF"
PANEL_2 = "#FAFBFF"
TEXT = "#1E2433"
TEXT_2 = "#5A6478"
MUTED = "#95A0B5"
BORDER = "#E7EBF3"
ACCENT = "#660874"      # 清华紫 PANTONE 259C
ACCENT_2 = "#C2247F"    # 玫红（辅助色渐变端 #D93379 的过渡）
ACCENT_SOFT = "#F6EBF8"
SUCCESS = "#16C79A"
WARN = "#FFA94D"
DANGER = "#FF5C7C"
SHADOW = "rgba(30,36,51,0.08)"

FONT = '"Microsoft YaHei UI","Microsoft YaHei","Segoe UI",sans-serif'
MONO = '"Cascadia Mono","Consolas",monospace'

QSS = f"""
/* ---------------- 基础 ---------------- */
QWidget {{
    font-family: {FONT};
    font-size: 10pt;
    color: {TEXT};
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QToolTip {{
    background: #2B3245; color: #FFFFFF; border: none;
    padding: 5px 9px; border-radius: 6px; font-size: 9pt;
}}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px 2px 2px 2px;
}}
QScrollBar::handle:vertical {{
    background: #D3D9E8; border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #B9C2D8; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #D3D9E8; border-radius: 5px; min-width: 28px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

/* ---------------- 通用按钮 ---------------- */
QPushButton {{
    border: 1px solid {BORDER}; border-radius: 9px; padding: 8px 16px;
    background: #FFFFFF; color: {TEXT};
}}
QPushButton:hover {{ background: #F7F9FD; border: 1px solid #D6DCEA; }}
QPushButton:pressed {{ background: #EAEEF7; }}
QPushButton:disabled {{ color: #B7BECF; background: #F2F4F9; border: 1px solid {BORDER}; }}

QPushButton[btn="primary"] {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT_2}, stop:1 {ACCENT});
    color: #FFFFFF; font-weight: 600; border: 1px solid transparent;
}}
QPushButton[btn="primary"]:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #A81B74, stop:1 #550663);
}}
QPushButton[btn="primary"]:disabled {{
    background: #C9CFEA; color: #FFFFFF; border: 1px solid transparent;
}}

QPushButton[btn="ghost"] {{
    background: {ACCENT_SOFT}; color: {ACCENT}; font-weight: 600;
    border: 1px solid #E4CFEE;
}}
QPushButton[btn="ghost"]:hover {{ background: #F1E2F5; border: 1px solid {ACCENT}; }}

QPushButton[btn="soft"] {{
    background: #F4F6FB; color: {TEXT_2}; border: 1px solid #E3E8F2;
}}
QPushButton[btn="soft"]:hover {{ background: #ECF0F8; border: 1px solid #CBD3E4; }}

QPushButton[btn="danger"] {{
    background: #FFF0F3; color: {DANGER}; font-weight: 600;
    border: 1px solid #FFD6DE;
}}
QPushButton[btn="danger"]:hover {{ background: #FFE2E8; }}

/* 小尺寸按钮：覆盖全局大 padding，防止按钮文字被裁。
   注意：不能用 property("size")——QWidget 自带 QSize 型 size 属性，
   setProperty("size","mini") 会静默失败，选择器永远匹配不上 */
QPushButton[btnsize="mini"] {{
    padding: 2px 10px; font-size: 9pt; border-radius: 7px;
}}

QPushButton[btn="success"] {{
    background: #E6F9F3; color: #0FA47F; font-weight: 600;
    border: 1px solid #C3EEDF;
}}
QPushButton[btn="success"]:hover {{ background: #D6F5EB; }}

/* ---------------- 卡片 ---------------- */
QFrame[card="true"] {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame[card="flat"] {{
    background: {PANEL_2};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame[card="accent"] {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #F8EFF9, stop:1 #FDF0F6);
    border: 1px solid #EBDCF2;
    border-radius: 14px;
}}

/* ---------------- 输入 ---------------- */
QLineEdit {{
    background: #FFFFFF; border: 1px solid {BORDER};
    border-radius: 10px; padding: 9px 12px; selection-background-color: {ACCENT};
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; background: #FFFFFF; }}
QLineEdit[line="search"] {{
    border-radius: 12px; padding-left: 34px; background: #F5F7FD; border: 1px solid transparent;
}}
QLineEdit[line="search"]:focus {{ background: #FFFFFF; border: 1px solid {ACCENT}; }}

QTextEdit {{
    background: #FFFFFF; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px;
}}
QTextEdit:focus {{ border: 1px solid {ACCENT}; }}

QComboBox {{
    background: #FFFFFF; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 7px 10px; min-width: 80px;
}}
QComboBox:hover {{ border: 1px solid #CDD4E6; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    border: 1px solid {BORDER}; border-radius: 8px; background: #FFFFFF;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
}}

QCheckBox {{ spacing: 6px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px;
    border: 1px solid #C8CFE0; background: #FFFFFF;
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QCheckBox::indicator:hover {{ border: 1px solid {ACCENT}; }}

QSlider::groove:horizontal {{
    height: 5px; background: #E3E7F2; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
    background: {ACCENT}; border: 2px solid #FFFFFF;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}

/* ---------------- 列表 ---------------- */
QListWidget, QTableWidget {{
    background: #FFFFFF; border: 1px solid {BORDER}; border-radius: 12px;
    outline: none;
}}
QListWidget::item {{ padding: 8px 10px; border-radius: 8px; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QListWidget::item:hover {{ background: #F5F7FD; }}

QTableWidget {{
    gridline-color: #F0F2F8; selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: #FAFBFF; border: none; border-bottom: 1px solid {BORDER};
    padding: 8px 10px; font-weight: 600; color: {TEXT_2};
}}

QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{
    padding: 8px 18px; margin-right: 4px; border-radius: 9px;
    background: transparent; color: {TEXT_2};
}}
QTabBar::tab:selected {{ background: #FFFFFF; color: {ACCENT}; font-weight: 600; }}
QTabBar::tab:hover {{ background: #EDF0F9; }}

QProgressBar {{
    background: #EDF0F8; border: none; border-radius: 6px; height: 10px; text-align: center;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2});
    border-radius: 6px;
}}
"""


def badge_style(color: str) -> str:
    # Qt QSS 不支持 #RRGGBBAA（会被当成 #AARRGGBB 解析成不透明色），
    # 必须用 rgba() 写半透明背景
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    return (
        f"background:rgba({r},{g},{b},0.10); color:{color}; border:none;"
        f"border-radius:8px; padding:3px 9px; font-size:9pt; font-weight:600;"
    )


def self_only(widget, name: str, body: str) -> None:
    """把 QWidget{...} 规则限定在控件自身，不级联到后代。

    中间容器写 QWidget{background:...} 会匹配所有后代（包括按钮），
    与全局 QSS 组合时会盖掉 QPushButton 的背景（如 primary 渐变消失）。
    改用 #objectName 选择器只匹配容器本身。
    """
    widget.setObjectName(name)
    widget.setStyleSheet(f"QWidget#{name}{{{body}}}")
