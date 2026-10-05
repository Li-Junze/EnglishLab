# -*- coding: utf-8 -*-
"""SQLite 知识库：词汇表、曝光日志、素材、词典缓存。"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any

from . import config

# 词汇状态
KNOWN = "known"       # 已掌握（在知识库中）
LEARNING = "learning" # 学习中的生词
NEW = "new"           # 刚筛出来、还没处理

# 进入知识库的来源
ORIGIN_BASE = "base"      # 高中 3500 基础词
ORIGIN_USER = "user"      # 用户手动标记
ORIGIN_AUTO = "auto"      # 曝光达标自动纳入

_SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
    word        TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'new',
    origin      TEXT NOT NULL DEFAULT '',
    encounter   INTEGER NOT NULL DEFAULT 0,   -- 遇到次数（封顶，见 settings）
    encounter_capped INTEGER NOT NULL DEFAULT 0,
    freq        INTEGER NOT NULL DEFAULT 0,   -- 最近一个素材中的出现次数
    total_freq  INTEGER NOT NULL DEFAULT 0,   -- 历史累计出现次数
    right_cnt   INTEGER NOT NULL DEFAULT 0,
    wrong_cnt   INTEGER NOT NULL DEFAULT 0,
    phonetic    TEXT NOT NULL DEFAULT '',
    meaning     TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL DEFAULT 0,
    updated_at  REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_words_status ON words(status);

CREATE TABLE IF NOT EXISTS materials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    video_path  TEXT NOT NULL DEFAULT '',
    srt_path    TEXT NOT NULL DEFAULT '',
    word_count  INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exposures (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word        TEXT NOT NULL,
    material_id INTEGER NOT NULL DEFAULT 0,
    t_start     REAL NOT NULL DEFAULT 0,
    t_end       REAL NOT NULL DEFAULT 0,
    sentence    TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_exposures_word ON exposures(word);

CREATE TABLE IF NOT EXISTS dict_cache (
    word        TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    updated_at  REAL NOT NULL DEFAULT 0
);
"""

_conn: sqlite3.Connection | None = None
# 词表版本号：任何会改变"哪些词已知 / 被屏蔽"的写操作都要 +1，
# 让 lexicon 的缓存失效（看视频时需要实时反映新掌握的词）。
_words_version = 0


def words_version() -> int:
    return _words_version


def bump() -> None:
    """手动让词表缓存失效（切换词汇水准等外部改动后用）。"""
    _bump()


def _bump() -> None:
    global _words_version
    _words_version += 1


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(_SCHEMA)
        _conn.commit()
        _migrate(_conn)
    return _conn


def _migrate(c: sqlite3.Connection) -> None:
    """老库缺列时补齐，避免升级后直接崩。"""
    add_cols = {
        "exposures": {"translation": "TEXT NOT NULL DEFAULT ''"},
        "words": {"blocked": "INTEGER NOT NULL DEFAULT 0"},
        "materials": {
            "last_opened": "REAL NOT NULL DEFAULT 0",
            "progress_ms": "INTEGER NOT NULL DEFAULT 0",
        },
    }
    for table, cols in add_cols.items():
        try:
            have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            for name, ddl in cols.items():
                if have and name not in have:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            c.commit()
        except Exception:
            pass
    # 历史遗留：同一视频被重复导入成多条素材，启动时合并一次
    try:
        dedupe_materials()
    except Exception:
        pass


def _now() -> float:
    return time.time()


# ------------------------------------------------------------------ 词操作
def get_word(word: str) -> sqlite3.Row | None:
    c = conn().execute("SELECT * FROM words WHERE word=?", (word.lower(),))
    return c.fetchone()


def ensure_word(word: str, status: str = NEW, origin: str = "") -> sqlite3.Row:
    w = word.lower().strip()
    row = get_word(w)
    if row is None:
        _bump()
        conn().execute(
            "INSERT INTO words (word, status, origin, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (w, status, origin, _now(), _now()),
        )
        conn().commit()
        row = get_word(w)
    return row


def set_status(word: str, status: str, origin: str | None = None) -> None:
    w = word.lower().strip()
    _bump()
    if origin is None:
        conn().execute(
            "UPDATE words SET status=?, updated_at=? WHERE word=?", (status, _now(), w)
        )
    else:
        conn().execute(
            "UPDATE words SET status=?, origin=?, updated_at=? WHERE word=?",
            (status, origin, _now(), w),
        )
    conn().commit()


def mark_known(word: str, origin: str = ORIGIN_USER) -> None:
    """纳入知识库。"""
    ensure_word(word)
    set_status(word, KNOWN, origin)


def unmark_known(word: str) -> None:
    ensure_word(word)
    set_status(word, LEARNING, "")


# ------------------------------------------------------------------ 屏蔽
def set_blocked(word: str, blocked: bool = True) -> None:
    """用户选择"以后不再出现"的词。屏蔽后不再高亮、不再进任何列表。"""
    ensure_word(word)
    _bump()
    conn().execute(
        "UPDATE words SET blocked=?, updated_at=? WHERE word=?",
        (1 if blocked else 0, _now(), word.lower().strip()),
    )
    conn().commit()


def is_blocked(word: str) -> bool:
    row = get_word(word)
    return bool(row and int(row["blocked"]))


def blocked_words() -> set[str]:
    return {r["word"] for r in conn().execute(
        "SELECT word FROM words WHERE blocked=1").fetchall()}


def toggle_blocked(word: str) -> bool:
    """切换屏蔽状态，返回切换后是否处于屏蔽。"""
    nb = not is_blocked(word)
    set_blocked(word, nb)
    return nb


def is_known(word: str) -> bool:
    row = get_word(word)
    return bool(row and row["status"] == KNOWN)


def known_words() -> set[str]:
    c = conn().execute("SELECT word FROM words WHERE status=?", (KNOWN,))
    return {r["word"] for r in c.fetchall()}


def bump_encounter(word: str, n: int = 1) -> int:
    """累加遇到次数，达到上限后停止。返回累加后的值。"""
    cap = int(config.get("encounter_cap", 50))
    w = word.lower().strip()
    ensure_word(w)
    row = get_word(w)
    cur = int(row["encounter"])
    if int(row["encounter_capped"]):
        return cur
    new = cur + n
    if new >= cap:
        new = cap
        conn().execute(
            "UPDATE words SET encounter=?, encounter_capped=1, updated_at=? WHERE word=?",
            (new, _now(), w),
        )
    else:
        conn().execute(
            "UPDATE words SET encounter=?, updated_at=? WHERE word=?", (new, _now(), w)
        )
    conn().commit()

    thr = int(config.get("auto_master_threshold", 5))
    if new >= thr:
        mark_known(w, ORIGIN_AUTO)
    return new


def add_exposure(
    word: str, material_id: int, t_start: float, t_end: float, sentence: str,
    translation: str = "",
) -> None:
    conn().execute(
        "INSERT INTO exposures (word, material_id, t_start, t_end, sentence, translation, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (word.lower(), material_id, t_start, t_end, sentence, translation, _now()),
    )


def exposures(word: str, limit: int = 3) -> list[sqlite3.Row]:
    """这个词最近被记录到的视频原句（同一句只取最早一次）。"""
    return conn().execute(
        "SELECT sentence, translation, MIN(t_start) AS t_start FROM exposures "
        "WHERE word=? GROUP BY sentence ORDER BY t_start LIMIT ?",
        (word.lower(), limit),
    ).fetchall()


def commit() -> None:
    conn().commit()


def set_freq(word: str, freq: int) -> None:
    conn().execute(
        "UPDATE words SET freq=?, total_freq=total_freq+?, updated_at=? WHERE word=?",
        (freq, freq, _now(), word.lower()),
    )


def record_quiz(word: str, ok: bool) -> None:
    col = "right_cnt" if ok else "wrong_cnt"
    conn().execute(
        f"UPDATE words SET {col}={col}+1, updated_at=? WHERE word=?",
        (_now(), word.lower()),
    )
    conn().commit()


def update_info(word: str, phonetic: str = "", meaning: str = "") -> None:
    conn().execute(
        "UPDATE words SET phonetic=?, meaning=?, updated_at=? WHERE word=?",
        (phonetic, meaning, _now(), word.lower()),
    )
    conn().commit()


def blocked_rows(keyword: str = "") -> list[sqlite3.Row]:
    """被用户屏蔽（"不再显示"）的词，可以在词库里恢复。"""
    sql = "SELECT * FROM words WHERE blocked=1"
    args: list[Any] = []
    if keyword:
        sql += " AND word LIKE ?"
        args.append(f"%{keyword.lower()}%")
    sql += " ORDER BY updated_at DESC, word ASC"
    return conn().execute(sql, args).fetchall()


def all_words(status: str | None = None, keyword: str = "") -> list[sqlite3.Row]:
    sql = "SELECT * FROM words WHERE 1=1"
    args: list[Any] = []
    if status:
        sql += " AND status=?"
        args.append(status)
    if keyword:
        sql += " AND word LIKE ?"
        args.append(f"%{keyword.lower()}%")
    sql += " ORDER BY total_freq DESC, word ASC"
    return conn().execute(sql, args).fetchall()


def stats() -> dict:
    c = conn()
    def one(sql, args=()):
        return c.execute(sql, args).fetchone()[0]
    return {
        "known": one("SELECT COUNT(*) FROM words WHERE status=?", (KNOWN,)),
        "learning": one("SELECT COUNT(*) FROM words WHERE status=?", (LEARNING,)),
        "new": one("SELECT COUNT(*) FROM words WHERE status=?", (NEW,)),
        # 其中有多少是"词汇水准自带的基准词"，UI 上要分开说清楚，
        # 否则用户会以为自己真的学了几千个词
        "base": one("SELECT COUNT(*) FROM words WHERE origin=? AND status=?",
                    (ORIGIN_BASE, KNOWN)),
        "materials": one("SELECT COUNT(*) FROM materials"),
    }


# ------------------------------------------------------------------ 素材
def add_material(title: str, video_path: str, srt_path: str, word_count: int) -> int:
    cur = conn().execute(
        "INSERT INTO materials (title, video_path, srt_path, word_count, created_at,"
        " last_opened, progress_ms)"
        " VALUES (?,?,?,?,?,?,0)",
        (title, video_path, srt_path, word_count, _now(), _now()),
    )
    conn().commit()
    return cur.lastrowid


def material(mid: int) -> sqlite3.Row | None:
    return conn().execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()


def materials_list(limit: int = 50) -> list[sqlite3.Row]:
    """最近用过的素材，按最后打开时间倒序。"""
    return conn().execute(
        "SELECT * FROM materials ORDER BY last_opened DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()


def touch_material(mid: int, progress_ms: int = -1) -> None:
    if progress_ms < 0:
        conn().execute(
            "UPDATE materials SET last_opened=? WHERE id=?", (_now(), mid)
        )
    else:
        conn().execute(
            "UPDATE materials SET last_opened=?, progress_ms=? WHERE id=?",
            (_now(), int(progress_ms), mid),
        )
    conn().commit()


def material_mastered(mid: int) -> tuple[int, int]:
    """(已掌握, 总数) —— 该素材筛出的生词里有多少进了知识库。"""
    rows = conn().execute(
        "SELECT w.status FROM words w JOIN exposures e ON e.word = w.word "
        "WHERE e.material_id=? GROUP BY w.word",
        (mid,),
    ).fetchall()
    total = len(rows)
    known = sum(1 for r in rows if r["status"] == KNOWN)
    return known, total


def forget_material(mid: int) -> None:
    conn().execute("DELETE FROM exposures WHERE material_id=?", (mid,))
    conn().execute("DELETE FROM materials WHERE id=?", (mid,))
    conn().commit()


def _norm_path(p: str) -> str:
    return os.path.normcase(os.path.abspath(p)) if p else ""


def find_material(video_path: str, srt_path: str) -> int:
    """按视频/字幕路径找已有素材，找不到返回 0（避免同一素材重复建条目）。"""
    c = conn()
    for col, val in (("video_path", video_path), ("srt_path", srt_path)):
        if val:
            row = c.execute(f"SELECT id FROM materials WHERE {col}=?", (val,)).fetchone()
            if row:
                return row["id"]
    return 0


def update_material(mid: int, title: str, video_path: str, srt_path: str, word_count: int) -> None:
    conn().execute(
        "UPDATE materials SET title=?, video_path=?, srt_path=?, word_count=? WHERE id=?",
        (title, video_path, srt_path, word_count, mid),
    )
    conn().commit()


def dedupe_materials() -> None:
    """把历史遗留的重复素材合并成一条：同一视频/字幕只保留最近打开的行，
    曝光记录全部挂到保留行上，并清掉合并后重复的曝光。"""
    rows = conn().execute(
        "SELECT id, video_path, srt_path FROM materials ORDER BY last_opened DESC, id DESC"
    ).fetchall()
    keeper: dict[str, int] = {}
    dupes: list[tuple[int, int]] = []
    for r in rows:
        key = _norm_path(r["video_path"]) or _norm_path(r["srt_path"])
        if not key:
            continue
        if key in keeper:
            dupes.append((keeper[key], r["id"]))
        else:
            keeper[key] = r["id"]
    if not dupes:
        return
    for dst, src in dupes:
        conn().execute(
            "UPDATE exposures SET material_id=? WHERE material_id=?", (dst, src)
        )
        conn().execute("DELETE FROM materials WHERE id=?", (src,))
    # 合并后同一 (词, 素材, 时间点, 句子) 可能出现多份曝光，去重保留最早一条
    conn().execute(
        "DELETE FROM exposures WHERE id NOT IN ("
        " SELECT MIN(id) FROM exposures GROUP BY word, material_id, t_start, sentence)"
    )
    conn().commit()


# ------------------------------------------------------------------ 词典缓存
def cache_get(word: str) -> dict | None:
    row = conn().execute(
        "SELECT payload FROM dict_cache WHERE word=?", (word.lower(),)
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["payload"])
    except Exception:
        return None


def cache_put(word: str, payload: dict) -> None:
    conn().execute(
        "INSERT INTO dict_cache (word, payload, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(word) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
        (word.lower(), json.dumps(payload, ensure_ascii=False), _now()),
    )
    conn().commit()


def clear_cache() -> None:
    conn().execute("DELETE FROM dict_cache")
    conn().commit()
