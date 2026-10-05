# -*- coding: utf-8 -*-
"""字幕解析：SRT / WebVTT / 纯文本（按空行断句）。"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Cue:
    index: int
    start: float   # 秒
    end: float     # 秒
    text: str      # 英文主句；纯中文行时退化为原文
    zh: str = ""   # 同一条里的中文部分（双语字幕）
    pair_of: object | None = None   # 被配成某条英文字幕的译文时，指向它

    @property
    def en(self) -> str:
        """英文内容；整条是中文时返回空串。"""
        return self.text if not _is_zh_line(self.text) else ""

    @property
    def display(self) -> str:
        """给人看的整条内容。"""
        return self.text

    @property
    def start_ms(self) -> int:
        return int(self.start * 1000)

    @property
    def end_ms(self) -> int:
        return int(self.end * 1000)


_TIME_RE = re.compile(
    r"(?P<h>\d{1,3}):(?P<m>\d{1,2}):(?P<s>\d{1,2})[.,](?P<ms>\d{1,3})"
    r"|(?P<m2>\d{1,2}):(?P<s2>\d{1,2})[.,](?P<ms2>\d{1,3})"
)


def _to_sec(m: re.Match) -> float:
    if m.group("h") is not None:
        return (
            int(m.group("h")) * 3600
            + int(m.group("m")) * 60
            + int(m.group("s"))
            + int(m.group("ms").ljust(3, "0")) / 1000.0
        )
    return int(m.group("m2")) * 60 + int(m.group("s2")) + int(m.group("ms2").ljust(3, "0")) / 1000.0


def read_text(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


_TAG_RE = re.compile(r"<[^>]+>")
_SPEAKER_RE = re.compile(r"^\s*-?\s*[A-Z][A-Za-z.\s]{0,25}:\s*")

# 中日韩字符
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")


def _is_zh_line(s: str) -> bool:
    """判断一行（或合并后的一段）是不是中文行。"""
    s = (s or "").strip()
    if not s:
        return False
    letters = [c for c in s if not c.isspace()]
    if not letters:
        return False
    hits = len(_CJK_RE.findall(s))
    # 出现汉字就算中文行；比百分比判断更抗夹杂英文术语的情况
    return hits >= 1 and hits / len(letters) > 0.15


def _clean(line: str) -> str:
    line = _TAG_RE.sub("", line)
    line = line.replace("{\\an8}", "")
    line = _SPEAKER_RE.sub("", line)
    return line.strip()


def split_bilingual(lines: list[str]) -> tuple[str, str]:
    """把同一条字幕的多行拆成 (英文, 中文)。"""
    en_parts: list[str] = []
    zh_parts: list[str] = []
    for ln in lines:
        ln = _clean(ln)
        if not ln:
            continue
        if _is_zh_line(ln):
            zh_parts.append(ln)
        else:
            en_parts.append(ln)
    en = " ".join(en_parts).strip()
    zh = " ".join(zh_parts).strip()
    return en, zh


def parse(path: str) -> list[Cue]:
    text = read_text(path).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u200e", "").replace("\u200f", "")
    # 长破折号行首
    lines = text.split("\n")

    cues: list[Cue] = []
    i = 0
    idx = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.upper().startswith("WEBVTT") or line.startswith("NOTE") or line.startswith("STYLE"):
            i += 1
            continue
        if "-->" in line:
            mm = list(_TIME_RE.finditer(line))
            if len(mm) >= 2:
                start = _to_sec(mm[0])
                end = _to_sec(mm[1])
            elif len(mm) == 1:
                start = _to_sec(mm[0])
                end = start + 3.0
            else:
                i += 1
                continue
            i += 1
            buf: list[str] = []
            while i < n and lines[i].strip():
                buf.append(_clean(lines[i]))
                i += 1
            en, zh = split_bilingual(buf)
            body = en or zh
            if body:
                idx += 1
                cues.append(Cue(idx, start, end, body, zh=zh))
            continue
        # 纯数字序号行：期待下一行是时间轴
        if line.isdigit():
            if i + 1 < n and "-->" in lines[i + 1]:
                i += 1
                continue
        i += 1

    if not cues:
        # 兜底：按空行分块，每块算一句，平均 3 秒
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        t = 0.0
        for b in blocks:
            en, zh = split_bilingual(b.split("\n"))
            body = en or zh
            if body:
                idx += 1
                cues.append(Cue(idx, t, t + 3.0, body, zh=zh))
                t += 3.0

    pair_split_bilingual(cues)
    return cues


def pair_split_bilingual(cues: list[Cue]) -> None:
    """
    给「中英文分成两条字幕」的情况配对。

    有些双语字幕不是同一条里两行，而是英文一条、紧接着一条时间几乎相同的中文。
    这里把没有中文的英文 cue 与紧邻的中文字幕互相挂上。
    """
    need = [c for c in cues if c.text and not c.zh and not _is_zh_line(c.text)]
    pool = [c for c in cues if not c.en and c.zh]
    if not need or not pool:
        return
    pi = 0
    for c in need:
        while pi < len(pool) and pool[pi].end < c.start - 0.05:
            pi += 1
        if pi >= len(pool):
            break
        cand = pool[pi]
        if cand.start - 0.35 <= c.start <= cand.end + 0.35:
            c.zh = cand.zh
            cand.pair_of = c        # 标记：显示时可跳过这条重复译文
            pi += 1


def bilingual_ratio(cues: list[Cue]) -> tuple[int, int]:
    """统计 (英文条数, 中文条数)，用于给用户提示字幕构成。"""
    en = sum(1 for c in cues if c.en)
    zh = sum(1 for c in cues if not c.en and c.zh)
    return en, zh


def summarize_langs(cues: list[Cue]) -> str:
    en, zh = bilingual_ratio(cues)
    if en and zh:
        return f"英文 {en} 条 / 中文 {zh} 条"
    if zh:
        return f"纯中文 {zh} 条"
    return f"英文 {en} 条"


def cue_translation(cue: Cue) -> str:
    """这条字幕的中文意思；没有就返回空串。"""
    return cue.zh or ""


def find_index(cues: list[Cue], t: float) -> int:
    """二分查找覆盖时间 t（秒）的字幕下标，找不到返回 -1。"""
    lo, hi = 0, len(cues) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        c = cues[mid]
        if t < c.start:
            hi = mid - 1
        elif t > c.end:
            lo = mid + 1
        else:
            return mid
    return -1
