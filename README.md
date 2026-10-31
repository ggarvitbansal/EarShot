# Earshot

**The neutral third seat in a technical sales call.**

Earshot sits between an IOMETE sales rep and a buyer. It listens to the call and does
three things at once: it checks every factual claim the rep makes against IOMETE's own
documentation, it translates the jargon into language a CFO can follow, and it keeps the
deal state — open questions, risks, and the capabilities that fit this buyer but were
never pitched.

Built for the **IOMETE track at hackCBS**: *Make Complex Tech Easy to Buy.*
The friction we picked is the one nobody covers: **the buyer cannot tell which sentence
in the call is true.** A rep improvises a founding year, a certification, a price; the
buyer writes it down; three weeks later procurement finds out it was wrong. That is the
expensive moment, and it is invisible to every sales tool that only records calls.

---

## The honesty contract

Most "AI sales copilot" demos answer every question confidently. Earshot refuses to.
Every claim gets exactly one of five verdicts, and there is no "probably":

| Verdict | Meaning | Shown as |
|---|---|---|
| **Sourced** | The docs contain this claim. | quote + doc URL |
| **Contradicted** | The docs say something else. | the correct statement + quote + URL |
| **Off record** | Pricing, certifications, roadmap dates, legal terms. | why + what to say instead |
| **No source** | Nothing in the 262-page corpus supports it. | "say you'll confirm in writing" |
| **Promise** | A commitment, not a factual claim. | tracked separately, not judged |

The rule that keeps it credible: **a false accusation is worse than a missed one.**
Entity and capability facts are confirmation-only — if the sentence names the topic but
the expected value is missing, the engine falls through to retrieval instead of declaring
the rep wrong. Only mechanically checkable slots (a year, a port number) can contradict on
their own. On the 30-case labelled set in `data/eval_set.json` that yields **100% flag
precision and zero false accusations**.

## It runs on-device

No API key, no model endpoint, no network call. The corpus is on disk, retrieval is BM25,
verdicts come from a verified rulebook plus the retrieved text. `GET /api/health` returns
`"network_calls": 0`.

This is not a limitation we apologise for. IOMETE sells a sovereign, air-gapped lakehouse;
the tool that sells it should not ship the customer's conversation to a US cloud. Same
property, both ends of the deal.

## What is real, and what is scripted

Judges should be able to tell the difference without asking.

**Real**
- The corpus: 263 documentation URLs crawled from `iomete.com/resources/sitemap.xml`,
  262 with body text, 1.4M characters, chunked into 1,517 passages.
- Retrieval, verdicts, citations, jargon matching, question tracking, risk and
  opportunity detection — all computed at request time by `engine/`.
- Every citation is proved verbatim against the crawled page at startup
  (`Knowledge.self_check`). If a quote ever stops matching, the server says so on boot
  instead of showing a fake source.
- The evaluation harness and its published failures (`engine/evaluate.py`).
- The **Live input** path: paste or dictate your own transcript, same engine, same output.

**Scripted**
- The two demo calls are written transcripts (`data/transcript_demo.json`,
  `transcript_fixed.json`). The replay is a timer revealing one turn at a time — the
  analysis is not pre-computed into the file, it is produced by the same engine that
  handles live input, but the *words* are authored.
- Microphone capture uses the browser's Web Speech API (Chrome/Edge, needs network).
  It only fills the text box; the analysis is identical either way. If the venue Wi-Fi
  dies, replay and typed input both still work.

## Before and after, in one number

Same buyer, same questions, same engine. The only change is that the rep says what the
docs support:

| | Original call | With corrections |
|---|---|---|
| Claims backed by docs | **40%** | **100%** |
| Contradicted claims | **4** | 0 |
| Off-record commitments | **1** | 0 |
| Jargon terms needing translation | 24 | 21 |

That is the product's claim in one table: the bot does not make the rep sound better, it
makes the rep say things that survive a security review.

## Run it

```bash
./run.sh          # Windows: run.bat
# open http://127.0.0.1:8010
```

First run installs the Python environment and builds the UI; after that it is offline.
If you only have the engine, `python -m engine.analyze` prints the full analysis and
`python -m engine.evaluate` prints the accuracy report.

## Layout

```
engine/retrieval.py    chunking + BM25 over the corpus (no dependencies)
engine/analyze.py      the verdict engine: claims, jargon, questions, risks, offers
engine/evaluate.py     labelled accuracy harness
backend/app.py         FastAPI: /api/call /api/brief /api/metrics /api/eval /api/evidence
frontend/src/App.jsx   three-panel UI + replay + brief + live input
data/raw_text.jsonl    crawled documentation (262 pages)
data/facts*.json       verified fact and antifact rulebook
data/jargon.json       75 terms, plain-English, each cited
data/signals.json      off-record categories, deal risks, capability map
data/eval_set.json     30 hand-labelled sentences, including the engine's failures
```

## Known limits

- Retrieval is lexical. A claim phrased in words the docs never use lands in "no source"
  rather than being matched semantically. We chose that failure direction on purpose.
- The rulebook covers what a discovery call actually discusses (company facts,
  architecture, sovereignty, security, integrations). A deep Kubernetes question will
  usually come back "no source" — correct, but not clever.
- Pricing, certifications and roadmap are permanently "off record": the public docs do
  not carry them, so the honest answer is always "in writing".
- Scores are per-call and relative. 100% means every judged sentence had a citable page,
  not that the deal will close.
