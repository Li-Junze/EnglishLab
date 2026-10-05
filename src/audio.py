# -*- coding: utf-8 -*-
"""发音：下载音频到缓存并播放（Qt 多媒体，带 TTS 兜底）。"""
from __future__ import annotations

import hashlib
import os
import threading
from typing import Iterable

import requests

from . import config, dictionary

try:
    from PyQt5.QtCore import QUrl
    from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
except Exception:  # pragma: no cover
    QMediaPlayer = None


def _path_for(word: str, accent: str) -> str:
    key = hashlib.md5(f"{word}|{accent}".encode("utf-8")).hexdigest()[:16]
    return os.path.join(config.AUDIO_CACHE, f"{key}.mp3")


def ensure_audio(word: str, accent: str = "us", ttl_days: int = 30) -> str | None:
    """确保本地有该词的发音文件，返回路径。"""
    p = _path_for(word, accent)
    if os.path.exists(p) and os.path.getsize(p) > 512:
        return p
    url = dictionary.voice_url(word, accent)
    try:
        r = requests.get(url, headers={"User-Agent": dictionary.UA}, timeout=15)
        if r.status_code == 200 and len(r.content) > 512:
            with open(p, "wb") as f:
                f.write(r.content)
            return p
    except Exception:
        pass
    return None


def prefetch_audio(words: Iterable[str], accent: str = "us") -> None:
    def work():
        for w in words:
            try:
                ensure_audio(w, accent)
            except Exception:
                pass

    threading.Thread(target=work, daemon=True).start()


class Speaker:
    """单词朗读器。"""

    def __init__(self):
        self._player = None
        self._tts = None
        self._fallback_ready = False

    def _get_player(self):
        if self._player is None and QMediaPlayer is not None:
            try:
                self._player = QMediaPlayer()
                self._player.setVolume(90)
            except Exception:
                self._player = None
        return self._player

    def _get_tts(self):
        if self._tts is None and not self._fallback_ready:
            self._fallback_ready = True
            try:
                from PyQt5.QtTextToSpeech import QTextToSpeech
                self._tts = QTextToSpeech()
            except Exception:
                self._tts = None
        return self._tts

    def speak(self, word: str, accent: str | None = None) -> None:
        accent = accent or str(config.get("accent", "us"))
        p = ensure_audio(word, accent)
        player = self._get_player()
        if p and player is not None:
            try:
                player.setMedia(QMediaContent(QUrl.fromLocalFile(p)))
                player.play()
                return
            except Exception:
                pass
        tts = self._get_tts()
        if tts is not None:
            try:
                tts.say(word)
            except Exception:
                pass
