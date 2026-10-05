# -*- coding: utf-8 -*-
"""基础词库（高中 3500）与轻量词形还原。"""
from __future__ import annotations

import os
import re
from functools import lru_cache

from . import config, db, vocab

# 需要排除的极高频功能词（即使是生词也不值得占用名额）
STOP = {
    "the", "and", "you", "that", "was", "for", "are", "with", "his", "they",
    "this", "have", "from", "one", "had", "but", "what", "all", "were", "when",
    "your", "can", "said", "there", "use", "each", "which", "she", "how", "their",
    "will", "other", "about", "out", "many", "then", "them", "these", "some",
    "her", "would", "make", "like", "him", "into", "time", "has", "look", "two",
    "more", "write", "see", "number", "way", "could", "people", "than", "first",
    "been", "call", "who", "oil", "its", "now", "find", "long", "down", "day",
    "did", "get", "come", "made", "may", "part", "over", "new", "sound", "take",
    "only", "little", "work", "know", "place", "year", "live", "me", "back",
    "give", "most", "very", "after", "thing", "our", "just", "name", "good",
    "sentence", "man", "think", "say", "great", "where", "help", "through",
    "much", "before", "line", "right", "too", "mean", "old", "any", "same",
    "tell", "boy", "follow", "came", "want", "show", "also", "around", "form",
    "three", "small", "set", "put", "end", "does", "another", "well", "large",
    "must", "big", "even", "such", "because", "turn", "here", "why", "ask",
    "went", "men", "read", "need", "land", "different", "home", "us", "move",
    "try", "kind", "hand", "picture", "again", "change", "off", "play", "spell",
    "air", "away", "animal", "house", "point", "page", "letter", "mother",
    "answer", "found", "study", "still", "learn", "should", "america", "world",
    "high", "every", "near", "add", "food", "between", "own", "below", "country",
    "plant", "last", "school", "father", "keep", "tree", "never", "start",
    "city", "earth", "eye", "light", "thought", "head", "under", "story",
    "saw", "left", "don", "few", "while", "along", "might", "close", "something",
    "seem", "next", "hard", "open", "example", "begin", "life", "always",
    "those", "both", "paper", "together", "got", "group", "often", "run",
    "important", "until", "children", "side", "feet", "car", "mile", "night",
    "walk", "white", "sea", "began", "grow", "took", "river", "four", "carry",
    "state", "once", "book", "hear", "stop", "without", "second", "later",
    "miss", "idea", "enough", "eat", "face", "watch", "far", "really", "almost",
    "above", "girl", "sometimes", "mountain", "cut", "young", "talk", "soon",
    "list", "song", "being", "leave", "family", "it's", "i'm", "you're",
    "we're", "they're", "don't", "doesn't", "isn't", "wasn't", "can't",
    "won't", "didn't", "couldn't", "wouldn't", "shouldn't", "let's", "that's",
    "there's", "what's", "he's", "she's", "i've", "you've", "we've", "i'll",
    "you'll", "he'll", "we'll", "they'll", "i'd", "you'd", "he'd", "we'd",
    "ain", "aren", "couldn", "didn", "doesn", "hadn", "hasn", "haven", "isn",
    "ma", "mightn", "mustn", "needn", "shan", "shouldn", "wasn", "weren",
    "won", "wouldn", "d", "ll", "m", "o", "re", "ve", "y", "s", "t",
}

# 常见不规则变化 -> 原形
IRREGULAR = {
    "am": "be", "is": "be", "are": "be", "was": "be", "were": "be", "been": "be",
    "being": "be", "has": "have", "had": "have", "having": "have", "does": "do",
    "did": "do", "done": "do", "doing": "do", "went": "go", "gone": "go",
    "going": "go", "goes": "go", "made": "make", "making": "make", "took": "take",
    "taken": "take", "taking": "take", "came": "come", "coming": "come",
    "saw": "see", "seen": "see", "seeing": "see", "knew": "know", "known": "know",
    "knowing": "know", "got": "get", "gotten": "get", "getting": "get",
    "gave": "give", "given": "give", "giving": "give", "found": "find",
    "finding": "find", "thought": "think", "thinking": "think", "told": "tell",
    "telling": "tell", "became": "become", "becoming": "become", "left": "leave",
    "leaving": "leave", "felt": "feel", "feeling": "feel", "put": "put",
    "brought": "bring", "bringing": "bring", "began": "begin", "begun": "begin",
    "beginning": "begin", "kept": "keep", "keeping": "keep", "held": "hold",
    "holding": "hold", "wrote": "write", "written": "write", "writing": "write",
    "stood": "stand", "standing": "stand", "heard": "hear", "hearing": "hear",
    "let": "let", "meant": "mean", "meaning": "mean", "met": "meet",
    "meeting": "meet", "ran": "run", "running": "run", "paid": "pay",
    "paying": "pay", "sat": "sit", "sitting": "sit", "spoke": "speak",
    "spoken": "speak", "speaking": "speak", "lay": "lie", "lying": "lie",
    "led": "lead", "leading": "lead", "grew": "grow", "grown": "grow",
    "growing": "grow", "lost": "lose", "losing": "lose", "fell": "fall",
    "fallen": "fall", "falling": "fall", "sent": "send", "sending": "send",
    "built": "build", "building": "build", "understood": "understand",
    "understanding": "understand", "drew": "draw", "drawn": "draw",
    "drawing": "draw", "broke": "break", "broken": "break", "breaking": "break",
    "spent": "spend", "spending": "spend", "cut": "cut", "cutting": "cut",
    "rose": "rise", "risen": "rise", "rising": "rise", "drove": "drive",
    "driven": "drive", "driving": "drive", "bought": "buy", "buying": "buy",
    "wore": "wear", "worn": "wear", "wearing": "wear", "chose": "choose",
    "chosen": "choose", "choosing": "choose", "men": "man", "women": "woman",
    "children": "child", "people": "person", "feet": "foot", "teeth": "tooth",
    "mice": "mouse", "geese": "goose", "lives": "life", "leaves": "leaf",
    "knives": "knife", "wives": "wife", "wolves": "wolf", "halves": "half",
    "shelves": "shelf", "thieves": "thief", "selves": "self", "loaves": "loaf",
    "better": "good", "best": "good", "worse": "bad", "worst": "bad",
    "further": "far", "furthest": "far", "farther": "far", "farthest": "far",
    "more": "much", "most": "much", "mice": "mouse", "oxen": "ox",
    "phenomena": "phenomenon", "criteria": "criterion", "data": "datum",
    "analyses": "analysis", "theses": "thesis", "bases": "basis",
    "indices": "index", "matrices": "matrix", "appendices": "appendix",
}

_VOWELS = set("aeiou")


@lru_cache(maxsize=1)
def base_words() -> dict[str, tuple[str, str]]:
    """返回 {word: (phonetic, meaning)}。"""
    out: dict[str, tuple[str, str]] = {}
    path = config.BASE_WORDS
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            next(f, None)  # 跳过表头
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if not parts or not parts[0]:
                    continue
                w = parts[0].strip().lower()
                ph = parts[1] if len(parts) > 1 else ""
                mn = parts[2] if len(parts) > 2 else ""
                out[w] = (ph, mn)
    return out


def load_base_into_db() -> int:
    """把基础词库写入知识库（只补不覆盖）。"""
    words = base_words()
    c = db.conn()
    n = 0
    for w, (ph, mn) in words.items():
        row = db.get_word(w)
        if row is None:
            c.execute(
                "INSERT INTO words (word, status, origin, phonetic, meaning, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (w, db.KNOWN, db.ORIGIN_BASE, ph, mn, 0, 0),
            )
            n += 1
        elif row["status"] != db.KNOWN and row["origin"] == db.ORIGIN_BASE:
            db.set_status(w, db.KNOWN, db.ORIGIN_BASE)
    c.commit()
    return n


# 已知词 / 屏蔽词缓存：看视频时要实时反映"刚掌握的词"，所以按 db 版本号失效
# 弹出规则（模式 / 词频上限）改了也要失效，所以签名是 (版本号, 模式, 上限, 跳过)
_cache: dict = {"sig": None, "known": set(), "blocked": set()}


def _signature():
    return (
        db.words_version(),
        vocab.popup_mode(),
        vocab.freq_top(),
        vocab.freq_skip_known(),
    )


def _refresh() -> None:
    sig = _signature()
    if _cache["sig"] != sig:
        # 已认识的词 = 当前词汇水准的基准词 + 用户自己的知识库
        _cache["known"] = set(vocab.level_words()) | db.known_words()
        _cache["blocked"] = db.blocked_words()
        _cache["sig"] = sig


def _known_vocab() -> set[str]:
    """用于校验还原结果是否合理的词表。"""
    _refresh()
    return _cache["known"]


def known_vocab() -> set[str]:
    _refresh()
    return _cache["known"]


def blocked_vocab() -> set[str]:
    _refresh()
    return _cache["blocked"]


def lemma(word: str) -> str:
    """轻量词形还原。优先命中已知词表，其次走规则。"""
    w = word.lower().strip()
    if not w:
        return w
    if w in IRREGULAR:
        return IRREGULAR[w]
    vocab = _known_vocab()
    if w in vocab:
        return w

    cands: list[str] = []

    def add(x: str):
        if x and x != w:
            cands.append(x)

    # 复数 / 第三人称
    if w.endswith("ies") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("ves") and len(w) > 4:
        add(w[:-3] + "f")
        add(w[:-3] + "fe")
    if w.endswith("es") and len(w) > 3:
        add(w[:-2])
        add(w[:-1])
    if w.endswith("s") and not w.endswith(("ss", "us", "is", "as")):
        add(w[:-1])

    # 过去式 / 进行时
    if w.endswith("ied") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("ed") and len(w) > 3:
        add(w[:-2])
        add(w[:-1])
        if len(w) > 4 and w[-3] == w[-4] and w[-3] not in _VOWELS:
            add(w[:-3])
    if w.endswith("ing") and len(w) > 4:
        stem = w[:-3]
        add(stem)
        add(stem + "e")
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in _VOWELS:
            add(stem[:-1])

    # 副词 / 比较级
    if w.endswith("ly") and len(w) > 4:
        add(w[:-2])
    if w.endswith("ier") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("iest") and len(w) > 5:
        add(w[:-4] + "y")
    if w.endswith("er") and len(w) > 3:
        add(w[:-2])
        add(w[:-1])
    if w.endswith("est") and len(w) > 4:
        add(w[:-3])
        add(w[:-2])
    if w.endswith("ion") and len(w) > 5:
        add(w[:-3] + "e")

    for c in cands:
        if c in vocab:
            return c
    for c in cands:
        if c in IRREGULAR:
            return IRREGULAR[c]
    return w


_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")


def tokenize(text: str) -> list[str]:
    return [m.group(0) for m in _TOKEN_RE.finditer(text)]


def normalize(tok: str) -> str:
    t = tok.replace("’", "'").lower()
    if "'" in t:
        head, _, tail = t.partition("'")
        if tail in ("s", "re", "ve", "ll", "d", "m", "t"):
            t = head
    return t.strip("-")


def candidates_from_texts(texts: list[str]) -> dict[str, dict]:
    """从一组字幕文本里统计"非知识库词"。

    返回 {lemma: {"freq": 总次数, "spread": 出现在几条字幕里, "forms": {词形}}}。
    spread 很关键：只在一段例子里反复出现的词（比如视频里的 fluffy）
    不该压过零星出现但真正有用的词。
    """
    _refresh()
    known = _cache["known"]
    blocked = _cache["blocked"]
    min_len = int(config.get("min_word_len", 3))
    out: dict[str, dict] = {}
    for text in texts:
        seen_here: set[str] = set()
        for tok in tokenize(text):
            w = normalize(tok)
            if len(w) < min_len or w.isdigit():
                continue
            lm = lemma(w)
            if len(lm) < min_len:
                continue
            if lm in STOP or lm in blocked:
                continue
            if not vocab.accept(lm, lm in known):
                continue
            it = out.get(lm)
            if it is None:
                it = out[lm] = {"freq": 0, "spread": 0, "forms": set()}
            it["freq"] += 1
            it["forms"].add(w)
            if lm not in seen_here:
                seen_here.add(lm)
                it["spread"] += 1
    return out


def score(item: dict) -> float:
    """综合分：覆盖了多少句 比 单纯堆次数 更能说明这个词值得学。"""
    return item.get("spread", 0) * 2.0 + item.get("freq", 0)


def rank(cands: dict[str, dict]) -> list[tuple[str, dict]]:
    return sorted(cands.items(), key=lambda kv: (-score(kv[1]), kv[0]))


def is_target(word: str) -> bool:
    """这个词在当前弹出规则下算不算"目标词"（要弹出 / 高亮 / 进候选池）。

    规则由 vocab.accept 统一判定：
    - 按知识库（默认）：知识库外的一律算，不做任何二次挑选；
    - 按词频：只看词频排名在上限以内的词，与知识库无关。
    """
    _refresh()
    w = (word or "").lower().strip()
    if len(w) < int(config.get("min_word_len", 3)) or w.isdigit():
        return False
    if w in STOP or w in _cache["blocked"]:
        return False
    return vocab.accept(w, w in _cache["known"])


def is_unknown(word: str) -> bool:
    """是否算生词（看视频时实时判定）。"""
    return is_target(word)


def unknown_in_text(text: str) -> list[str]:
    """一句话里所有知识库外的词，按出现顺序返回，无数量上限。"""
    out: list[str] = []
    seen: set[str] = set()
    for tok in tokenize(text or ""):
        w = normalize(tok)
        if not w or w.isdigit():
            continue
        lm = lemma(w)
        if lm in seen:
            continue
        seen.add(lm)
        if is_unknown(lm):
            out.append(lm)
    return out
