# -*- coding: utf-8 -*-
"""全局配置与路径管理。"""
from __future__ import annotations

import json
import os
import sys

# ---------------------------------------------------------------- 路径
def _app_root() -> str:
    """项目根目录（兼容打包 / 脚本两种运行方式）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ROOT = _app_root()
SRC_DIR = os.path.join(ROOT, "src")
DATA_DIR = os.path.join(ROOT, "data")
ASSETS_DIR = os.path.join(ROOT, "assets")
AUDIO_CACHE = os.path.join(DATA_DIR, "cache", "audio")

for _d in (DATA_DIR, ASSETS_DIR, AUDIO_CACHE):
    os.makedirs(_d, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "lexicon.db")
BASE_WORDS = os.path.join(DATA_DIR, "base3500.tsv")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

APP_NAME = "English Lab"
APP_VERSION = "1.1.0"

# ---------------------------------------------------------------- 默认设置
DEFAULTS = {
    # 遇到次数上限，达到后停止累加
    "encounter_cap": 50,
    # 曝光达到该次数后自动纳入知识库（视为已掌握）
    "auto_master_threshold": 5,
    # 生词最短长度（更短的一律忽略）
    "min_word_len": 3,
    # 单个素材最多筛出多少生词（进入"学词"列表；看视频时不受这个限制）
    "max_new_words": 100,
    # 发音偏好：us / uk
    "accent": "us",
    # 看视频时侧栏生词面板的保留条数（不限学习列表）
    "recent_panel_size": 40,
    # 测验默认题量
    "quiz_size": 20,
    # 自动标记掌握所需的最小词频（低于该词频不自动掌握，避免误判）
    "auto_master_min_freq": 1,
    # 发音偏好：us / uk
    "accent": "us",
    # 面板分层：区分"当前句 / 上一句 / 更早"
    "panel_layered": 1,
    # 初始词汇水准（见 vocab.LEVELS）：决定基准已知词有多少
    "vocab_level": "cet4",
    # -------- 看视频时的"弹出规则" --------
    # 判定方式：lexicon=按知识库内外 / freq=按词频
    "popup_mode": "lexicon",
    # 词频模式的排名上限（0 = 不限）
    "popup_freq_top": 8000,
    # 词频模式下是否跳过已掌握的词
    "popup_freq_skip_known": 1,
}

_settings_cache: dict | None = None


def load_settings() -> dict:
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    data = dict(DEFAULTS)
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception:
            pass
    _settings_cache = data
    return data


def save_settings(patch: dict | None = None) -> dict:
    global _settings_cache
    data = load_settings()
    if patch:
        data.update(patch)
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    _settings_cache = data
    return data


def get(key: str, default=None):
    return load_settings().get(key, DEFAULTS.get(key, default))
