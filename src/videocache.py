# -*- coding: utf-8 -*-
"""最近视频缓存 —— LRU 保留最近 5 个视频的续播信息，持久化到 JSON。

记录内容：视频/字幕路径、素材 id、标题、上次播放位置、倍速、时长。
打开过的视频再次进入时直接定位到上次位置，字幕/规则不用重新摸黑。
"""
from __future__ import annotations

import json
import os
import threading
import time

from . import config

PATH = os.path.join(config.DATA_DIR, "cache", "recent_videos.json")
MAX_ITEMS = 5

_lock = threading.Lock()
_items: list[dict] = []
_loaded = False


def _load() -> None:
    global _loaded, _items
    if _loaded:
        return
    _loaded = True
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            _items = [x for x in data if isinstance(x, dict) and x.get("video_path")]
    except Exception:
        _items = []


def _save() -> None:
    try:
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, PATH)
    except Exception:
        pass


def all_items() -> list[dict]:
    """最近视频列表，新的在前。"""
    with _lock:
        _load()
        return [dict(x) for x in _items]


def get(video_path: str) -> dict | None:
    """按视频路径取缓存记录；命中时移到队首。"""
    if not video_path:
        return None
    key = os.path.normcase(os.path.abspath(video_path))
    with _lock:
        _load()
        for i, x in enumerate(_items):
            if os.path.normcase(os.path.abspath(x["video_path"])) == key:
                hit = _items.pop(i)
                _items.insert(0, hit)
                return dict(hit)
    return None


def touch(video_path: str, srt_path: str = "", material_id: int = 0,
          title: str = "", position_ms: int = 0, duration_ms: int = 0,
          rate: float = 1.0) -> None:
    """记录/更新一个视频的缓存信息并置顶，超出 MAX_ITEMS 淘汰最旧的。"""
    if not video_path:
        return
    key = os.path.normcase(os.path.abspath(video_path))
    rec = {
        "video_path": video_path,
        "srt_path": srt_path or "",
        "material_id": int(material_id or 0),
        "title": title or os.path.splitext(os.path.basename(video_path))[0],
        "position_ms": max(0, int(position_ms)),
        "duration_ms": max(0, int(duration_ms)),
        "rate": float(rate or 1.0),
        "saved_at": time.time(),
    }
    with _lock:
        _load()
        global _items
        _items = [x for x in _items
                  if os.path.normcase(os.path.abspath(x["video_path"])) != key]
        _items.insert(0, rec)
        del _items[MAX_ITEMS:]
        _save()


def forget(video_path: str) -> None:
    global _items
    key = os.path.normcase(os.path.abspath(video_path))
    with _lock:
        _load()
        _items = [x for x in _items
                  if os.path.normcase(os.path.abspath(x["video_path"])) != key]
        _save()
