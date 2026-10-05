# -*- coding: utf-8 -*-
"""
English Lab 启动入口。

以无控制台方式运行时（pythonw），stdout/stderr 会被重定向到 error.log，
任何未捕获异常会写入日志，方便排查但不会弹出黑窗口。
"""
from __future__ import annotations

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LOG = os.path.join(ROOT, "error.log")


def _redirect_streams():
    """pythonw 下没有控制台，把输出接到日志文件。"""
    if sys.stdout is None or sys.stderr is None:
        try:
            f = open(LOG, "a", encoding="utf-8")
            sys.stdout = f
            sys.stderr = f
        except Exception:
            pass


def _fatal(msg: str):
    try:
        from PyQt5.QtWidgets import QMessageBox, QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "English Lab 启动失败", msg)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "English Lab 启动失败", 0x10)
        except Exception:
            pass


def main() -> int:
    _redirect_streams()
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QFont
        from PyQt5.QtWidgets import QApplication
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        traceback.print_exc()
        _fatal("缺少 PyQt5，请先运行 init.bat 完成依赖安装。")
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("English Lab")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))

    try:
        # 按当前词汇水准灌入基准词（首次运行用默认水准，之后跟随设置）
        from src import vocab
        vocab.set_level(vocab.current_level_key(), write_db=True)
    except Exception:
        traceback.print_exc()

    try:
        from src.ui.main_window import MainWindow
        win = MainWindow()
        win.show()
        return app.exec_()
    except Exception:
        traceback.print_exc()
        _fatal("程序启动出错，详情已写入 error.log\n\n" + traceback.format_exc()[-1500:])
        return 1


if __name__ == "__main__":
    sys.exit(main())
