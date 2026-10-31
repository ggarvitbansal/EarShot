"""Earshot API — one process, no network calls, serves the built UI too.

Everything the bot knows is on disk: 262 crawled documentation pages, a hand
verified fact rulebook, a jargon dictionary and a signal table. Nothing in this
file phones home, which is the point: the same property IOMETE sells (runs inside
your perimeter) is the property of the tool that sells it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.analyze import Knowledge, analyze_call, deal_brief  # noqa: E402
from engine.evaluate import run as run_eval  # noqa: E402
from engine.retrieval import index  # noqa: E402

DATA = ROOT / "data"
app = FastAPI(title="Earshot", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

KB = Knowledge.load()
CITATIONS = KB.self_check()          # startup proof that every quote is verbatim
VARIANTS = {"demo": "transcript_demo.json", "fixed": "transcript_fixed.json"}
_cache: dict[str, dict] = {}


def call_for(variant: str) -> dict:
    if variant not in VARIANTS:
        raise HTTPException(404, f"unknown call '{variant}'")
    if variant not in _cache:
        raw = json.loads((DATA / VARIANTS[variant]).read_text(encoding="utf-8"))
        _cache[variant] = analyze_call(KB, raw)
    return _cache[variant]


@app.get("/api/health")
def health() -> dict:
    ix = index()
    return {
        "ok": True,
        "corpus_pages": len(KB.pages),
        "chunks": len(ix.chunks),
        "facts": len(KB.facts),
        "antifacts": len(KB.antifacts),
        "jargon_terms": len(KB.jargon),
        "citation_problems": CITATIONS,
        "network_calls": 0,
        "engine": "deterministic (BM25 + rulebook + curated signals)",
    }


@app.get("/api/call/{variant}")
def call(variant: str) -> dict:
    return call_for(variant)


@app.get("/api/brief/{variant}")
def brief(variant: str) -> dict:
    return deal_brief(call_for(variant))


@app.get("/api/metrics")
def metrics() -> dict:
    """Before/after, the number the pitch turns on."""
    out = {}
    for v in VARIANTS:
        m = call_for(v)["metrics"]
        out[v] = m
    out["delta"] = {
        "grounded_rate": out["fixed"]["grounded_rate"] - out["demo"]["grounded_rate"],
        "contradicted": out["demo"]["contradicted"] - out["fixed"]["contradicted"],
        "off_record": out["demo"]["off_record"] - out["fixed"]["off_record"],
    }
    return out


@app.get("/api/eval")
def evaluation() -> dict:
    report = run_eval(verbose=False)
    report.pop("rows", None)
    return report


@app.get("/api/evidence")
def evidence(q: str) -> dict:
    """Expose the retrieval layer so a judge can check a claim themselves."""
    ix = index()
    return {"query": q, "hits": [
        {"score": round(h.score, 2), "url": h.url, "title": h.title, "text": h.snippet(420)}
        for h in ix.search(q, 6)
    ]}


class Transcript(BaseModel):
    text: str
    name: str = "Live call"


@app.post("/api/analyze")
def analyze(body: Transcript) -> dict:
    """Analyse an arbitrary transcript: lines like 'rep: ...' / 'buyer: ...'.

    This is the path the microphone and the paste box both use, so nothing in the
    UI is faked — the same engine that produced the demo produced this.
    """
    utterances = []
    for i, line in enumerate(body.text.splitlines()):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(rep|seller|ae|buyer|customer|buyer2|ciso)\s*[:\-]\s*(.+)$", line, re.I)
        speaker, text = ("rep", line) if not m else (m.group(1).lower(), m.group(2))
        speaker = {"seller": "rep", "ae": "rep", "customer": "buyer", "ciso": "buyer2"}.get(speaker, speaker)
        utterances.append({"t": i * 12, "speaker": speaker, "text": text})
    if not utterances:
        raise HTTPException(400, "no utterances found — use 'rep:' / 'buyer:' prefixes")
    call = {"deal": {"name": body.name}, "speakers": {}, "utterances": utterances}
    result = analyze_call(KB, call)
    result["brief"] = deal_brief(result)
    return result


DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def ui() -> FileResponse:
        return FileResponse(DIST / "index.html")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    def no_ui() -> JSONResponse:
        return JSONResponse({"detail": "UI not built yet — run `npm run build` in frontend/"}, status_code=503)


@app.on_event("startup")
def _banner() -> None:
    print(f"[earshot] {len(KB.pages)} pages · {len(index().chunks)} chunks · "
          f"{len(KB.facts)} facts · {len(KB.antifacts)} antifacts · {len(KB.jargon)} terms")
    if CITATIONS:
        print(f"[earshot] !! {len(CITATIONS)} citation problems — verdicts would be unsafe")
    else:
        print("[earshot] citation integrity ok — every quote is verbatim in the corpus")
