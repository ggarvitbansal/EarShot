# Demo script — 3 minutes

Run `./run.sh`, open `http://127.0.0.1:8010`. Set the speed selector to **1×** before you
start talking (4× is for rehearsal only).

---

### 0:00 — The friction (30s, no clicking yet)

> "A rep tells a buyer your platform is self-hosted and air-gapped. The buyer writes it
> down, takes it to a security review, and three weeks later procurement finds out one
> sentence was wrong. Every call-recording tool will happily store that sentence. Nothing
> checks it.
>
> This is Earshot. It sits in the call, on both sides of the table."

### 0:30 — Let the call play

Press **↺** (restart) and leave it running. Let the transcript speak for itself for the
first four exchanges. Stop at the moment the red card appears.

Point at the middle column, don't read it:

> "Every factual claim gets a verdict. Green means the documentation contains it — click
> the link, it's the real page. Red means the docs say the opposite, and it shows what he
> should have said."

Wait for the second red card (*"the control plane runs in our cloud"*):

> "That one would have killed the deal in a bank. The platform operates entirely inside
> the customer's infrastructure — that's on their own getting-started page."

### 1:15 — The amber one (this is the point)

When **SOC 2 Type II** goes amber:

> "This is the one I care about. He wasn't lying — IOMETE probably *does* hold an
> attestation. But it is not in the product documentation, so the bot refuses to confirm
> it and marks it off-record with the line to say instead: send the trust-centre link in
> writing. A confident wrong answer here costs the deal. An honest unknown costs a day."

Same for the price: *"around forty thousand a year"* → off record. **No price appears
anywhere in the docs**, so the bot never makes one up.

### 1:45 — The buyer's side

Point at the right column, scroll the glossary a little:

> "The buyer is a Head of Data Platform at a bank. She has just heard control plane, data
> plane, compaction, Iceberg, snapshot time travel. Each one is translated into a sentence
> a CFO understands, as it's said. That's the clarity problem, measured."

### 2:00 — What was left on the table

Bottom middle panel:

> "Query federation, BI connectors, streaming, dbt — all documented, all fit her stated
> pain, none of them said. That is next call's agenda, generated from what was missing."

### 2:15 — The before/after (the money shot)

Click **With corrections**, press **↺**, set **4×**.

> "Same buyer, same questions. The only change is that the rep says what the docs support."

Let it finish. The ring goes from **40%** to **100%**, and the ledger has no red and no
amber.

> "The bot doesn't make the rep sound better. It makes the rep say things that survive a
> security review."

### 2:45 — The brief

Click **Brief**.

> "This is what both sides leave with: what was corrected, what's open and who owns it,
> what was answered with a link, what's still on the table, and the next step. The buyer
> can hand this to her risk committee on Thursday."

### 3:00 — Close

> "One more thing, and it's the reason this works inside a bank: the whole thing runs on
> this laptop. No API key, no cloud call. `curl /api/health` — zero network calls. IOMETE
> sells a sovereign, air-gapped platform. The tool that sells it doesn't ship your
> conversation to someone else's data centre."

If a judge asks **"is the analysis real?"**:
- Click **Live input**, type: `rep: The platform runs on Delta Lake.` → Analyse → red card.
- Or open `http://127.0.0.1:8010/api/eval` and read the 30-case report, *including the
  miss the engine still makes*.

---

## If something breaks

| Symptom | Fix |
|---|---|
| Blank page | server not running: `cd backend && .venv/Scripts/activate && python -m uvicorn app:app --port 8010` |
| Replay finished too fast | ↺ restart, or click anywhere on the timeline to scrub |
| No internet | nothing needed; only the optional microphone uses the network |
| Judge asks about the corpus | `data/raw_text.jsonl` — 262 pages, one JSON object per line |
