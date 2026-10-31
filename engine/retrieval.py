"""Chunk the crawled IOMETE corpus and build a BM25 index over it.

No third-party dependencies: the whole point is that this runs on a laptop with
no network, no API key and no vector database. Retrieval is lexical (BM25), which
for factual product-doc matching is both good enough and fully inspectable — a
judge can open the exact chunk a verdict came from.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
RAW = DATA / "raw_text.jsonl"
CHUNKS = DATA / "chunks.jsonl"

CHUNK_CHARS = 900
STOP = set("""a an and are as at be been by for from has have how i if in into is it its of on or
that the their them then there these they this to was were what when where which who will with
you your we our can could should would may might must do does did not no yes""".split())


def tokenize(text: str) -> list[str]:
    """Words, plus the pieces of hyphenated compounds.

    "time-travel" must match a question that says "time travel", and semantics
    like "air-gapped" should still match as one token, so both forms are kept.
    """
    raw = re.findall(r"[a-z0-9][a-z0-9\-\.\+#]*", text.lower())
    out: list[str] = []
    for t in raw:
        t = t.rstrip(".")           # sentence-final punctuation is not part of the word
        if t in STOP or len(t) < 2:
            continue
        out.append(t)
        if "-" in t or "." in t:
            out.extend(p for p in re.split(r"[\-\.]", t) if len(p) > 1 and p not in STOP)
    return out


def build_chunks() -> list[dict]:
    """Split each page on blank lines, then pack paragraphs up to CHUNK_CHARS."""
    out: list[dict] = []
    for line in RAW.read_text(encoding="utf-8").splitlines():
        page = json.loads(line)
        text = page.get("text") or ""
        if len(text) < 200:
            continue
        paras = [p.strip() for p in text.split("\n") if p.strip()]
        buf: list[str] = []
        size = 0
        idx = 0
        for p in paras:
            buf.append(p)
            size += len(p)
            if size >= CHUNK_CHARS:
                body = "\n".join(buf)
                out.append({"id": f"{page['url']}#{idx}", "url": page["url"],
                            "title": page["title"], "text": body})
                idx += 1
                buf, size = [], 0
        if buf:
            body = "\n".join(buf)
            if len(body) > 120:
                out.append({"id": f"{page['url']}#{idx}", "url": page["url"],
                            "title": page["title"], "text": body})
    with CHUNKS.open("w", encoding="utf-8") as f:
        for c in out:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return out


@dataclass
class Hit:
    score: float
    id: str
    url: str
    title: str
    text: str

    def snippet(self, chars: int = 320) -> str:
        t = self.text.replace("\n", " ")
        return t[:chars].rsplit(" ", 1)[0] + ("…" if len(t) > chars else "")


class BM25:
    K1 = 1.4
    B = 0.72

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.docs = [tokenize(c["text"] + " " + c["title"]) for c in chunks]
        self.lens = [len(d) for d in self.docs]
        self.avg = sum(self.lens) / max(1, len(self.lens))
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def search(self, query: str, k: int = 5) -> list[Hit]:
        q = tokenize(query)
        if not q:
            return []
        scores = [0.0] * len(self.docs)
        for term in set(q):
            idf = self.idf.get(term)
            if not idf:
                continue
            for i, tf in enumerate(self.tf):
                f = tf.get(term)
                if f:
                    dl = self.lens[i]
                    scores[i] += idf * f * (self.K1 + 1) / (f + self.K1 * (1 - self.B + self.B * dl / self.avg))
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return [Hit(scores[i], c["id"], c["url"], c["title"], c["text"])
                for i in ranked if scores[i] > 0 for c in [self.chunks[i]]]


_INDEX: BM25 | None = None


def index() -> BM25:
    global _INDEX
    if _INDEX is None:
        if not CHUNKS.exists():
            build_chunks()
        chunks = [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines()]
        _INDEX = BM25(chunks)
    return _INDEX


if __name__ == "__main__":
    cs = build_chunks()
    ix = index()
    print(f"{len(cs)} chunks from {len({c['url'] for c in cs})} pages\n")
    for q in ["is it open source", "air gapped deployment", "what does it cost",
              "does it support spark streaming", "fine grained access control masking"]:
        print(f"Q: {q}")
        for h in ix.search(q, 3):
            print(f"  {h.score:5.1f}  {h.title[:52]:52} {h.url}")
        print()
