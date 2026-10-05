# -*- coding: utf-8 -*-
"""分级词库：初始词汇水准 + 看视频时的"弹出规则"。

设计思路（一套数据同时支撑两个功能）：

- **初始水准**（LEVELS）：决定"你已经认识多少词"。水准越高，基准已知词越多，
  弹出的生词就越少、越难。恒定并入高中 3500 大纲（data/base3500.tsv），
  因为它是国内学习者的硬底线，避免出现"选了六级却连大纲词都弹出"的倒挂。
- **弹出规则**（POPUP_MODES）：决定"字幕里哪些词算目标词"。两种口径，
  在看视频页面右上角现场切换，改完立刻重筛：
    1. 按知识库（默认）——知识库外的词一律弹出并配解释，看得懂的词不打扰；
    2. 按词频——不管在不在知识库，只看词频排名在上限以内的词，
       上限用滑块现场拖（拖到最右 = 不限，全弹）。

注意：默认口径下程序**不做任何挑选**，只要不在知识库里就全部给出解释；
想收窄范围时再切到词频模式并用滑块控制，选择权完全在使用者手上。
"""

from __future__ import annotations

import os
from functools import lru_cache

from . import config, db

FREQ_FILE = os.path.join(config.DATA_DIR, "vocab", "freq20k.txt")


# ---------------------------------------------------------------- 档位定义
# key, 名称, freq-topN, 是否并入高中大纲, 一句人话解释
LEVELS: list[dict] = [
    {"key": "starter", "name": "起步 · 1000 词", "top": 1000, "with_base": False,
     "desc": "只认最基础的一千词，几乎句句有生词"},
    {"key": "junior", "name": "初中 · 2000 词", "top": 2000, "with_base": False,
     "desc": "覆盖日常高频表达，初中毕业水平"},
    {"key": "senior", "name": "高中 · 3500 词", "top": 3500, "with_base": True,
     "desc": "高中大纲全量，默认推荐"},
    {"key": "cet4", "name": "四级 · 5000 词", "top": 5000, "with_base": True,
     "desc": "通过四级考试的词汇量"},
    {"key": "cet6", "name": "六级 · 8000 词", "top": 8000, "with_base": True,
     "desc": "六级 / 考研起步的词汇量"},    {"key": "advanced", "name": "高阶 · 15000 词", "top": 15000, "with_base": True,
     "desc": "托福雅思水平，只弹学术难词"},
]

DEFAULT_LEVEL = "cet4"

# ---------------------------------------------------------------- 弹出规则
# 判定口径：二选一，看视频页面现场切换
POPUP_MODES: list[dict] = [
    {"key": "lexicon", "name": "按知识库",
     "desc": "知识库外的词全部弹出并解释（陌生/学习中），已经认识的词不再打扰"},
    {"key": "freq", "name": "按词频",
     "desc": "不管在不在知识库，只看词频排名在上限以内的词；滑块拖到最右 = 不限"},
]

DEFAULT_POPUP_MODE = "lexicon"

# 词频滑块的可选档位（排名上限，0 表示"不限"）
FREQ_STEPS: list[int] = [500, 1000, 2000, 3000, 5000, 8000, 12000, 0]
DEFAULT_FREQ_TOP = 8000


def mode_by_key(key: str) -> dict:
    for m in POPUP_MODES:
        if m["key"] == key:
            return m
    return POPUP_MODES[0]


def popup_mode() -> str:
    return str(config.get("popup_mode", DEFAULT_POPUP_MODE))


def popup_mode_name() -> str:
    return mode_by_key(popup_mode())["name"]


def popup_mode_desc() -> str:
    return mode_by_key(popup_mode())["desc"]


def freq_top() -> int:
    """当前设定的词频排名上限，0 = 不限。"""
    try:
        return int(config.get("popup_freq_top", DEFAULT_FREQ_TOP))
    except Exception:
        return DEFAULT_FREQ_TOP


def freq_skip_known() -> bool:
    return bool(int(config.get("popup_freq_skip_known", 1)))


def _nearest_step(value: int) -> int:
    """把任意值吸附到滑块档位上。"""
    best = FREQ_STEPS[-1]
    best_d = None
    for s in FREQ_STEPS:
        if s == 0:
            continue
        d = abs(s - value)
        if best_d is None or d < best_d:
            best_d, best = d, s
    return best


def freq_top_index(top: int | None = None) -> int:
    """当前词频上限在滑块上的位置。"""
    t = _nearest_step(freq_top()) if top is None else _nearest_step(top)
    for i, s in enumerate(FREQ_STEPS):
        if s == t:
            return i
    return len(FREQ_STEPS) - 1


def freq_label(top: int | None = None) -> str:
    t = freq_top() if top is None else top
    return "不限词频" if not t else f"词频前 {t}"


def set_popup_mode(key: str) -> str:
    key = mode_by_key(key)["key"]
    config.save_settings({"popup_mode": key})
    return key


def set_freq_top(top: int) -> int:
    t = int(top)
    config.save_settings({"popup_freq_top": t})
    return t


def set_freq_skip_known(on: bool) -> bool:
    config.save_settings({"popup_freq_skip_known": 1 if on else 0})
    return on


def accept(word: str, known: bool) -> bool:
    """统一判定：这个词要不要弹出 / 高亮 / 进候选池。

    known 由调用方给出（该词是否已存在于当前已知集合），
    因为不同调用方手上的"已知集"来源不同。
    """
    if popup_mode() == "freq":
        top = freq_top()
        if known and freq_skip_known():
            return False
        if top and rank(word) >= int(top):
            return False
        return True
    # 默认：完全以知识库为准，不做任何二次挑选
    return not known


def rule_summary() -> str:
    """一行人话描述当前规则，用于界面显示。"""
    if popup_mode() == "freq":
        extra = "（跳过已掌握）" if freq_skip_known() else "（含已掌握）"
        return f"按词频 · {freq_label()}{extra}"
    return "按知识库 · 库外的词全弹"


def level_by_key(key: str) -> dict:
    for lv in LEVELS:
        if lv["key"] == key:
            return lv
    return LEVELS[0]


# ---------------------------------------------------------------- 底层数据
@lru_cache(maxsize=1)
def freq_ranks() -> dict[str, int]:
    """{word: rank}，rank 从 0 开始越小越常用。"""
    out: dict[str, int] = {}
    if not os.path.exists(FREQ_FILE):
        return out
    with open(FREQ_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            w = line.strip().lower()
            if w and w not in out:
                out[w] = i
    return out


@lru_cache(maxsize=1)
def base_words_set() -> frozenset[str]:
    """高中 3500 大纲词（自带音标释义），单独缓存避免和 lexicon 循环依赖。"""
    out: set[str] = set()
    path = config.BASE_WORDS
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            next(f, None)
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if parts and parts[0].strip():
                    out.add(parts[0].strip().lower())
    return frozenset(out)


def refresh() -> None:
    """外部词表文件变了就清缓存。"""
    freq_ranks.cache_clear()
    base_words_set.cache_clear()


def rank(word: str) -> int:
    """词频排名，不在表里返回 10**9。"""
    r = freq_ranks().get((word or "").lower().strip())
    return r if r is not None else 10 ** 9


# ---------------------------------------------------------------- 已知词集
_LEVEL_CACHE: dict = {"key": "", "words": frozenset()}


def current_level_key() -> str:
    return str(config.get("vocab_level", DEFAULT_LEVEL))


def level_words(level_key: str = "") -> frozenset[str]:
    """该水准下"默认已认识"的词集（含高中大纲，按配置决定是否并入）。"""
    lv = level_by_key(level_key or current_level_key())
    if _LEVEL_CACHE["key"] == lv["key"]:
        return _LEVEL_CACHE["words"]
    n = int(lv["top"])
    words = {w for w, r in freq_ranks().items() if r < n}
    if lv.get("with_base"):
        words |= set(base_words_set())
    res = frozenset(words)
    _LEVEL_CACHE["key"], _LEVEL_CACHE["words"] = lv["key"], res
    return res


def invalidate_level_cache() -> None:
    _LEVEL_CACHE["key"] = ""


# ---------------------------------------------------------------- 弹出过滤
def rank_of_level(level_key: str = "") -> int:
    """当前词汇水准对应的词频排名宽度（界面显示用）。"""
    lv = level_by_key(level_key or current_level_key())
    return int(lv["top"])


def set_level(level_key: str, write_db: bool = True) -> dict:
    """切换词汇水准。

    - 升级：新纳入的词写入知识库（status=known, origin=base）
    - 降级：只回收"纯粹因为水位线而认识、且没有任何学习痕迹"的词，
      用户手动标记 / 测验过 / 真实曝光过的词一律保留
    """
    lv = level_by_key(level_key)
    config.save_settings({"vocab_level": lv["key"]})
    invalidate_level_cache()
    target = level_words(lv["key"])
    if not write_db:
        return {"level": lv["key"], "known": len(target)}

    c = db.conn()
    have = {r["word"] for r in c.execute("SELECT word FROM words").fetchall()}
    added = 0
    for w in target:
        if w not in have:
            c.execute(
                "INSERT INTO words (word, status, origin, created_at, updated_at)"
                " VALUES (?,?,?,0,0)",
                (w, db.KNOWN, db.ORIGIN_BASE),
            )
            added += 1
    # 升级：原本因降级被收走的 base 词重新回归
    revived = 0
    rows = c.execute(
        "SELECT word FROM words WHERE origin=? AND status!=?", (db.ORIGIN_BASE, db.KNOWN)
    ).fetchall()
    for r in rows:
        w = r["word"]
        if w in target:
            c.execute(
                "UPDATE words SET status=?, updated_at=0 WHERE word=?", (db.KNOWN, w)
            )
            revived += 1
    # 降级：回收没有学习痕迹的水位词
    removed = 0
    rows2 = c.execute(
        "SELECT word FROM words WHERE origin=? AND status=? AND encounter=0"
        " AND total_freq=0 AND right_cnt=0 AND wrong_cnt=0 AND blocked=0",
        (db.ORIGIN_BASE, db.KNOWN),
    ).fetchall()
    for r in rows2:
        if r["word"] not in target:
            c.execute("DELETE FROM words WHERE word=?", (r["word"],))
            removed += 1
    c.commit()
    db.bump()
    return {"level": lv["key"], "known": len(target), "added": added,
            "revived": revived, "removed": removed}


def reset_knowledge(level_key: str = "") -> dict:
    """把知识库清干净重来：词表、曝光记录、素材历史、词典缓存全部删除，
    然后按给定（或当前）水准重新灌入基准词。相当于"第一次打开软件"。

    用户手动标记过的掌握词会一并消失，所以调用方必须先弹确认框。
    """
    key = level_key or current_level_key()
    c = db.conn()
    c.execute("DELETE FROM words")
    c.execute("DELETE FROM exposures")
    c.execute("DELETE FROM materials")
    c.execute("DELETE FROM dict_cache")
    c.commit()
    db._bump()
    return set_level(key, write_db=True)


def level_summary(level_key: str = "") -> str:
    lv = level_by_key(level_key or current_level_key())
    return f"{lv['name']} · {lv['desc']}"


def count_known_at(level_key: str) -> int:
    return len(level_words(level_key))
