# -*- coding: utf-8 -*-
"""查词：有道词典接口 + SQLite 缓存 + 内存 LRU + 后台并发任务。"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import OrderedDict
from typing import Any

import requests

from . import config, db

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
TIMEOUT = 12

JSONAPI = "https://dict.youdao.com/jsonapi?q={w}"
SUGGEST = "https://dict.youdao.com/suggest?q={w}&num=1&doctype=json"
VOICE = "https://dict.youdao.com/dictvoice?audio={w}&type={t}"

_B_RE = re.compile(r"</?b>")
_WS_RE = re.compile(r"\s+")


def _txt(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (list, tuple)):
        return " ".join(_txt(i) for i in x).strip()
    if isinstance(x, dict):
        for k in ("i", "#text", "value", "l"):
            if k in x:
                return _txt(x[k])
        return ""
    return _WS_RE.sub(" ", _B_RE.sub("", str(x))).strip()


def _first(d: Any) -> Any:
    if isinstance(d, list):
        return d[0] if d else None
    return d


def voice_url(word: str, accent: str = "us") -> str:
    return VOICE.format(w=requests.utils.quote(word), t=1 if accent == "uk" else 2)


def _parse_ec(data: dict, word: str) -> dict:
    out: dict[str, Any] = {
        "word": word,
        "uk_phone": "",
        "us_phone": "",
        "translations": [],
        "exam_types": [],
        "en_defs": [],
        "examples": [],
        "related": [],
        "source": "youdao",
        "ok": False,
    }

    simple = _first(data.get("simple", {}).get("word")) or {}
    ec = _first(data.get("ec", {}).get("word")) or {}
    out["uk_phone"] = _txt(ec.get("ukphone") or simple.get("ukphone"))
    out["us_phone"] = _txt(ec.get("usphone") or simple.get("usphone"))

    exam = data.get("ec", {}).get("exam_type")
    if isinstance(exam, list):
        out["exam_types"] = [str(e) for e in exam]

    # 中文释义（含词性）
    for tr in ec.get("trs", []) or []:
        for item in tr.get("tr", []) or []:
            s = _txt(item.get("l"))
            if s:
                out["translations"].append(s)
    if not out["translations"]:
        for tr in data.get("web_trans", {}).get("web-translation", []) or []:
            for t in tr.get("trans", []) or []:
                v = _txt(t.get("value"))
                if v:
                    out["translations"].append(v)
            break

    # 英文释义（WordNet）
    ee = data.get("ee", {}).get("word") or {}
    for tr in ee.get("trs", []) or []:
        pos = _txt(tr.get("pos"))
        mean = _txt(tr.get("tr"))
        if mean:
            out["en_defs"].append(f"{pos} {mean}".strip())

    # 例句：优先柯林斯权威例句（带中文）
    ex: list[dict[str, str]] = []
    exp = _first(data.get("expand_ec", {}).get("word")) or {}
    for tl in exp.get("transList", []) or []:
        content = tl.get("content") or {}
        for s in content.get("sents", []) or []:
            en = _txt(s.get("sentSpeech") or s.get("sentOrig"))
            zh = _txt(s.get("sentTrans"))
            if en:
                ex.append({"en": en, "zh": zh})
    if not ex:
        for sp in data.get("blng_sents_part", {}).get("sentence-pair", []) or []:
            en = _txt(sp.get("sentence"))
            zh = _txt(sp.get("sentence-translation"))
            if en:
                ex.append({"en": en, "zh": zh})
    if not ex:
        for s in data.get("auth_sents_part", {}).get("sent", []) or []:
            en = _txt(s.get("foreign"))
            if en:
                ex.append({"en": en, "zh": ""})
    # 去重
    seen = set()
    for e in ex:
        key = e["en"][:60]
        if key not in seen:
            seen.add(key)
            out["examples"].append(e)
    out["examples"] = out["examples"][:5]

    # 词族
    for rel in data.get("rel_word", {}).get("rels", []) or []:
        r = rel.get("rel") or {}
        pos = _txt(r.get("pos"))
        for w in r.get("words", []) or []:
            out["related"].append(
                {"word": _txt(w.get("word")), "pos": pos, "tran": _txt(w.get("tran"))}
            )
        if len(out["related"]) >= 8:
            break

    out["ok"] = bool(out["translations"] or out["en_defs"])
    return out


def _fetch_suggest(word: str) -> dict:
    r = requests.get(SUGGEST.format(w=requests.utils.quote(word)),
                     headers={"User-Agent": UA}, timeout=TIMEOUT)
    js = r.json()
    entries = (js.get("data") or {}).get("entries") or []
    if entries:
        return {
            "word": word,
            "uk_phone": "",
            "us_phone": "",
            "translations": [_txt(entries[0].get("explain"))],
            "exam_types": [],
            "en_defs": [],
            "examples": [],
            "related": [],
            "source": "youdao-suggest",
            "ok": True,
        }
    return {}


def fetch(word: str) -> dict:
    """联网查询（阻塞）。失败返回 ok=False 的最小结构。"""
    w = word.lower().strip()
    try:
        r = requests.get(JSONAPI.format(w=requests.utils.quote(w)),
                         headers={"User-Agent": UA}, timeout=TIMEOUT)
        data = r.json()
    except Exception:
        try:
            return _fetch_suggest(w)
        except Exception:
            return {"word": w, "ok": False, "translations": [], "examples": [],
                    "en_defs": [], "related": [], "exam_types": [],
                    "uk_phone": "", "us_phone": ""}
    try:
        res = _parse_ec(data, w)
    except Exception:
        res = {"word": w, "ok": False, "translations": [], "examples": [],
               "en_defs": [], "related": [], "exam_types": [],
               "uk_phone": "", "us_phone": ""}
    if not res.get("ok"):
        try:
            sg = _fetch_suggest(w)
            if sg:
                res.update({k: v for k, v in sg.items() if not res.get(k)})
                res["ok"] = True
        except Exception:
            pass
    # 基础词库兜底音标/释义
    if not res.get("us_phone") or not res.get("translations"):
        try:
            from . import lexicon
            bw = lexicon.base_words()
            if w in bw:
                ph, mn = bw[w]
                res["us_phone"] = res.get("us_phone") or ph
                res["uk_phone"] = res.get("uk_phone") or ph
                if not res.get("translations") and mn:
                    res["translations"] = [mn]
                    res["ok"] = True
        except Exception:
            pass
    res["fetched_at"] = time.time()
    return res


def lookup(word: str, force: bool = False) -> dict:
    """三级缓存：内存 LRU(10000) → SQLite dict_cache → 联网。"""
    w = word.lower().strip()
    if not force:
        hit = mem_get(w)
        if hit is not None:
            return hit
        c = db.cache_get(w)
        if c:
            mem_put(w, c)
            _record_history(w)
            return c
    res = fetch(w)
    if res.get("ok"):
        db.cache_put(w, res)
        mem_put(w, res)
    _record_history(w)
    return res


def brief(word: str) -> str:
    """一行中文释义，用于侧栏快速展示（内存缓存命中时零 IO）。"""
    w = word.lower()
    hit = mem_get(w)
    if hit is not None:
        trs = hit.get("translations") or []
        if trs:
            return trs[0]
        eds = hit.get("en_defs") or []
        return eds[0] if eds else ""
    c = db.cache_get(w)
    if c:
        mem_put(w, c)
    if not c:
        try:
            from . import lexicon
            bw = lexicon.base_words()
            if w in bw:
                return bw[w][1]
        except Exception:
            pass
        return ""
    trs = c.get("translations") or []
    if trs:
        return trs[0]
    eds = c.get("en_defs") or []
    return eds[0] if eds else ""


# ------------------------------------------------------ 内存 LRU + 查词历史
# 最近 10000 条查词常驻内存：字幕/词卡的热路径不再每词一次 SQLite 往返；
# 查词历史落盘 JSON，重启后仍保留"最近查过什么"。
MEM_MAX = 10000
HIST_PATH = os.path.join(config.DATA_DIR, "cache", "lookup_history.json")

_mem: "OrderedDict[str, dict]" = OrderedDict()
_mem_lock = threading.Lock()
_hist: "OrderedDict[str, float]" = OrderedDict()
_hist_lock = threading.Lock()
_hist_loaded = False


def _load_hist() -> None:
    global _hist_loaded
    if _hist_loaded:
        return
    _hist_loaded = True
    try:
        with open(HIST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                _hist[str(k)] = float(v)
    except Exception:
        pass


def _save_hist() -> None:
    try:
        os.makedirs(os.path.dirname(HIST_PATH), exist_ok=True)
        tmp = HIST_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(_hist), f, ensure_ascii=False)
        os.replace(tmp, HIST_PATH)
    except Exception:
        pass


def _record_history(w: str) -> None:
    with _hist_lock:
        _load_hist()
        _hist[w] = time.time()
        _hist.move_to_end(w)
        while len(_hist) > MEM_MAX:
            _hist.popitem(last=False)
        _save_hist()


def mem_get(w: str) -> dict | None:
    with _mem_lock:
        hit = _mem.get(w)
        if hit is not None:
            _mem.move_to_end(w)
        return hit


def mem_put(w: str, payload: dict) -> None:
    with _mem_lock:
        _mem[w] = payload
        _mem.move_to_end(w)
        while len(_mem) > MEM_MAX:
            _mem.popitem(last=False)


def history(limit: int = 100) -> list[tuple[str, float]]:
    """最近的查词记录，新的在前。"""
    with _hist_lock:
        _load_hist()
        return list(reversed(list(_hist.items())[-limit:]))


# ------------------------------------------------------------------ 异步任务
try:
    from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

    class _Signals(QObject):
        finished = pyqtSignal(str, dict)

    class LookupTask(QRunnable):
        def __init__(self, word: str, force: bool = False):
            super().__init__()
            self.word = word
            self.force = force
            self.signals = _Signals()

        def run(self):
            try:
                res = lookup(self.word, self.force)
            except Exception as e:  # pragma: no cover
                res = {"word": self.word, "ok": False, "error": str(e)}
            self.signals.finished.emit(self.word, res)

    _POOL = QThreadPool()
    _POOL.setMaxThreadCount(6)

    def lookup_async(word: str, callback, force: bool = False) -> None:
        """后台查词，完成后在主线程回调 (word, result)。"""
        task = LookupTask(word, force)
        task.signals.finished.connect(callback)
        _POOL.start(task)

    def prefetch(words: list[str]) -> None:
        """批量预热缓存（无回调）。"""
        for w in words:
            t = LookupTask(w)
            _POOL.start(t)

except Exception:  # pragma: no cover - 无 Qt 时仍可单测
    def lookup_async(word, callback, force=False):  # type: ignore
        callback(word, lookup(word, force))

    def prefetch(words):  # type: ignore
        pass
