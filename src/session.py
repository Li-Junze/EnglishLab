# -*- coding: utf-8 -*-
"""一次学习会话的状态：素材、字幕、生词列表与进度。"""
from __future__ import annotations

import os
from typing import Callable

from . import config, db, lexicon, srt


class Session:
    def __init__(self):
        self.material_id: int = 0
        self.title: str = ""
        self.video_path: str = ""
        self.srt_path: str = ""
        self.cues: list[srt.Cue] = []
        self.pool: list[dict] = []        # 全量候选生词（不限量，看视频时全部高亮/捕捉）
        self.words: list[dict] = []       # 学词列表（pool 的前 N 个）
        self.index: int = 0
        self.quiz_done: bool = False
        self.on_change: Callable[[], None] | None = None
        self.en_count: int = 0
        self.zh_count: int = 0
        self._study: set[str] = set()

    # ---------------------------------------------------------------- 载入
    def load(self, srt_path: str, video_path: str = "", reuse_material: int = 0) -> dict:
        import os
        self.srt_path = srt_path
        self.video_path = video_path
        self.cues = srt.parse(srt_path)
        self.title = os.path.splitext(os.path.basename(video_path or srt_path))[0]

        # 双语字幕里自带的中文对照（不再联网翻译，只原样展示）
        self.en_count, self.zh_count = srt.bilingual_ratio(self.cues)

        # 生词只从英文字幕里筛，避免中文行里夹杂的英文把词表搞脏
        texts = [c.en for c in self.cues if c.en] or [c.text for c in self.cues]
        cands = lexicon.candidates_from_texts(texts)
        ranked = lexicon.rank(cands)

        # pool = 全部候选；words = 进入"学词"环节的那一批
        limit = int(config.get("max_new_words", 100))
        self.pool = [
            {
                "word": w,
                "freq": it.get("freq", 0),
                "spread": it.get("spread", 0),
                "forms": sorted(it.get("forms", set())),
                "status": "",
            }
            for w, it in ranked
        ]
        study = self.pool[:limit]
        for w, it in ranked[:limit]:
            db.ensure_word(w, db.NEW)
            db.set_freq(w, it.get("freq", 0))
        db.commit()

        self.words = [
            {
                "word": it["word"],
                "freq": it["freq"],
                "spread": it["spread"],
                "status": db.get_word(it["word"])["status"],
            }
            for it in study
        ]
        self._sync_study()

        if reuse_material:
            self.material_id = reuse_material
        else:
            # 同一视频/字幕重复导入时复用旧条目，不新建（历史列表不出现重复）
            existing = db.find_material(video_path, srt_path)
            if existing:
                self.material_id = existing
                db.update_material(
                    existing, self.title, video_path, srt_path, len(self.pool)
                )
            else:
                self.material_id = db.add_material(
                    self.title, video_path, srt_path, len(self.pool)
                )
        db.touch_material(self.material_id)

        # 记录曝光上下文（每词最多 3 条，覆盖整个 pool）
        self._record_exposures()
        self._refresh_statuses()

        self.index = 0
        self.quiz_done = False
        return {
            "cues": len(self.cues),
            "candidates": len(self.words),
            "pool": len(self.pool),
            "duration": self.cues[-1].end if self.cues else 0,
            "en_cues": self.en_count,
            "zh_cues": self.zh_count,
            "reused": bool(reuse_material),
        }

    def reapply_filter(self) -> dict:
        """改了词汇水准或弹出规则后，用新标准重筛当前素材。

        已经加入过学习列表的词尽量保留（用户手动加的不会因为改档位而丢失）。
        """
        if not self.cues:
            return {"pool": 0, "candidates": 0}
        texts = [c.en for c in self.cues if c.en] or [c.text for c in self.cues]
        cands = lexicon.candidates_from_texts(texts)
        ranked = lexicon.rank(cands)
        limit = int(config.get("max_new_words", 100))

        prev = {it["word"]: it for it in self.pool}
        self.pool = []
        for w, it in ranked:
            old = prev.get(w)
            row = db.get_word(w)
            self.pool.append(
                {
                    "word": w,
                    "freq": it.get("freq", 0),
                    "spread": it.get("spread", 0),
                    "forms": sorted(it.get("forms", set())),
                    "status": old["status"] if old else (row["status"] if row else db.NEW),
                }
            )
        for w, it in ranked[:limit]:
            db.ensure_word(w, db.NEW)

        kept_pool = {it["word"] for it in self.pool}
        carried = [
            w
            for w in self.words
            if w["word"] not in kept_pool and w["status"] != db.KNOWN
        ]
        self.words = [
            {
                "word": it["word"],
                "freq": it["freq"],
                "spread": it["spread"],
                "status": it["status"],
            }
            for it in self.pool[:limit]
        ]
        self.words.extend(carried)
        db.commit()
        self._sync_study()
        self._emit()
        return {"pool": len(self.pool), "candidates": len(self.words)}

    def _record_exposures(self, per_word: int = 3):
        wanted = {it["word"] for it in self.pool}
        if not wanted:
            return
        # 同一个素材重复打开时先清掉旧曝光，避免句子重复堆积
        db.conn().execute("DELETE FROM exposures WHERE material_id=?", (self.material_id,))
        kept: dict[str, int] = {}
        for c in self.cues:
            if not c.en:
                continue
            for tok in lexicon.tokenize(c.en):
                lm = lexicon.lemma(lexicon.normalize(tok).lower())
                if lm in wanted and kept.get(lm, 0) < per_word:
                    kept[lm] = kept.get(lm, 0) + 1
                    db.add_exposure(lm, self.material_id, c.start, c.end, c.en, c.zh)
        db.commit()

    def _refresh_statuses(self):
        """把 db 里的最新状态同步回内存（看视频过程中会不断变）。"""
        for it in self.pool:
            row = db.get_word(it["word"])
            it["status"] = row["status"] if row else db.NEW
        for w in self.words:
            row = db.get_word(w["word"])
            if row:
                w["status"] = row["status"]
        self._sync_study()

    def _sync_study(self):
        self._study = {w["word"] for w in self.words}

    # ------------------------------------------------------------ 复习旧素材
    def load_material(self, mid: int) -> dict:
        row = db.material(mid)
        if not row:
            return {}
        srt_path = row["srt_path"]
        video_path = row["video_path"]
        if not os.path.exists(srt_path):
            return {}
        if video_path and not os.path.exists(video_path):
            video_path = ""
        return self.load(srt_path, video_path, reuse_material=mid)

    def save_progress(self, ms: int):
        if self.material_id:
            db.touch_material(self.material_id, ms)

    # ------------------------------------------------------------ 生词维护
    def add_to_study(self, word: str) -> bool:
        """把捕捉到的词加进学词列表（看视频时点"加入"）。"""
        w = (word or "").lower().strip()
        if not w or w in self._study:
            return False
        db.ensure_word(w, db.NEW)
        row = db.get_word(w)
        self.words.append(
            {
                "word": w,
                "freq": int(row["freq"]) if row else 1,
                "spread": 1,
                "status": row["status"] if row else db.NEW,
            }
        )
        self._study.add(w)
        db.commit()
        self._emit()
        return True

    def block_word(self, word: str):
        """以后不再出现这个词。"""
        w = (word or "").lower().strip()
        if not w:
            return
        db.set_blocked(w, True)
        self.pool = [it for it in self.pool if it["word"] != w]
        self.words = [it for it in self.words if it["word"] != w]
        self._sync_study()
        self._emit()

    # ------------------------------------------------------------ 字幕
    def cue_text(self, idx: int) -> tuple[str, str]:
        """返回该条字幕的 (英文, 中文)。"""
        if idx < 0 or idx >= len(self.cues):
            return "", ""
        c = self.cues[idx]
        return c.en, c.zh

    # ---------------------------------------------------------------- 学词
    @property
    def current(self) -> dict | None:
        if 0 <= self.index < len(self.words):
            return self.words[self.index]
        return None

    def mark_current(self, known: bool) -> None:
        item = self.current
        if not item:
            return
        w = item["word"]
        if known:
            db.mark_known(w, db.ORIGIN_USER)
            item["status"] = db.KNOWN
        else:
            db.bump_encounter(w, 1)
            row = db.get_word(w)
            item["status"] = row["status"]
        self._emit()

    def advance(self, step: int = 1) -> None:
        self.index = max(0, min(len(self.words) - 1, self.index + step))
        self._emit()

    def goto(self, i: int) -> None:
        self.index = max(0, min(len(self.words) - 1, i))
        self._emit()

    def _emit(self):
        if self.on_change:
            self.on_change()

    # ---------------------------------------------------------------- 看视频
    def words_in_cue(self, idx: int) -> list[str]:
        """当前这句话里需要弹出的词，规则由 vocab.popup_mode() 决定：
        - 按知识库（默认）：知识库外的词全部返回，看得懂的不打扰；
        - 按词频：只看指定词频区间内的词，可在右侧面板现场拖动调整。
        """
        if idx < 0 or idx >= len(self.cues):
            return []
        text = self.cues[idx].en or self.cues[idx].text
        return lexicon.unknown_in_text(text)

    def status_of(self, word: str) -> str:
        row = db.get_word(word)
        return row["status"] if row else db.NEW

    def is_blocked(self, word: str) -> bool:
        return db.is_blocked(word)

    def in_study(self, word: str) -> bool:
        return word in self._study

    def active_words(self) -> list[str]:
        """仍处于学习状态（未掌握）的词。"""
        return [w["word"] for w in self.words if w["status"] != db.KNOWN]

    # ---------------------------------------------------------------- 测验
    def quiz_words(self) -> list[str]:
        pool = [w["word"] for w in self.words]
        size = int(config.get("quiz_size", 20))
        return pool[:size]
