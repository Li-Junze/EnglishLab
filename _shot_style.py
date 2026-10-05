# -*- coding: utf-8 -*-
"""临时截图脚本：渲染改版后的界面并保存 PNG 供校验。"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

# 与 main.py 保持一致：启用高分屏缩放，px 才是逻辑像素
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
app = QApplication(sys.argv)

from src.ui.main_window import MainWindow

win = MainWindow()
win.resize(1320, 840)
win.show()

os.makedirs(os.path.join(ROOT, "shots3"), exist_ok=True)


def grab(name):
    for _ in range(5):
        app.processEvents()
    out = os.path.join(ROOT, "shots3", name)
    win.grab().save(out)
    print("saved", out)


# 1. 首页（侧栏 + 主题色）
win.goto(0)
grab("home_purple.png")

# 2. 看视频页：载入真实素材，不播放
srt_path = os.path.join("pros", "001", "Transformer的核心.srt")
video_path = os.path.join("pros", "001", "Transformer的核心.mp4")
win.session.load(srt_path, video_path)
win.goto(2)
grab("watch_purple.png")

# 3. 模拟生词卡：验证右侧面板排版与文字完整性
wp = win.watch
wp._push_words(["recap", "architecture", "transformer"], 3)
app.processEvents()
wp._push_words(["embedding", "parallel"], 7)
app.processEvents()
MEANS = {
    "recap": ("回顾；概括，总结", "/ˈriːkæp/"),
    "architecture": ("架构；体系结构", "/ˈɑːrkɪtektʃər/"),
    "transformer": ("变换器；变压器", "/trænsˈfɔːrmər/"),
    "embedding": ("嵌入；嵌入层", "/ɪmˈbedɪŋ/"),
    "parallel": ("平行的；并行的", "/ˈpærəlel/"),
}
for w, (tr, ph) in MEANS.items():
    wp._refresh_mean(w, {"translations": [tr], "us_phone": ph})
app.processEvents()
wp.panel.grab().save(os.path.join(ROOT, "shots3", "panel_cards.png"))
print("saved panel_cards.png")
grab("watch_cards.png")

# 3. 学词页
win.goto(1)
grab("learn_purple.png")

win.close()
print("done")
