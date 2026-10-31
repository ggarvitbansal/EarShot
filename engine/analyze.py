"""Earshot analysis engine.

Turns a rolling sales-call transcript into structured, cited insights:

  claims       every factual assertion a rep makes, with a verdict and evidence
  jargon       every product term spoken, with a plain-English translation
  questions    every buyer question, answered-with-citation or left open
  risks        deal-level blockers detected from either side
  offers       documented capabilities that fit this buyer but were never pitched
  metrics      grounded-claim rate, jargon density, open items

Design rules, in order of importance:

1. A verdict is only ever one of four honest states. There is no "probably":
     sourced      the docs contain the claim  -> quoted evidence + URL
     contradicted the docs contradict it      -> the correct statement + URL
     off_record   policy says never answer    -> pricing, certifications, roadmap, legal
     unsupported  no rule fired and retrieval found nothing close
2. Every sourced/contradicted verdict carries a verbatim quote from a page that
   was actually crawled. self_check() proves that at startup; if a citation ever
   stops being verbatim the engine refuses to boot rather than lie.
3. "unsupported" is a first-class outcome, not a failure. An unverifiable claim
   shown as unverifiable is the product.

No third-party packages, no network, no model. Everything is deterministic and
inspectable, which is what makes it safe to run inside a customer's own network.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .retrieval import index, tokenize

DATA = Path(__file__).resolve().parent.parent / "data"

SOURCED_MIN_SCORE = 13.0     # BM25 score below this is not treated as support
SOURCED_MIN_COVERAGE = 0.50  # share of the sentence's distinctive terms present in the hit

ASSERTIVE = re.compile(
    r"\b(is|are|was|were|has|have|supports?|supported|runs?|running|uses?|built|founded|certified|"
    r"provides?|includes?|allows?|lets|locks?|connects?|encrypts?|charges?|costs?|"
    r"works?|comes|deploys?|deployed|guarantee[sd]?|offer[s]?|can|cannot|can't|"
    r"never|always|only|requires?|needs?|stores?|handles?|scales?|ships?)\b", re.I)
ABSOLUTE = re.compile(r"\b(one hundred percent|100 %|100%|fully|completely|entirely|always|never|guaranteed)\b", re.I)
CONTINUATION = re.compile(r"^(that includes|this includes|that means|this means|it also|which means|and that|that is why|in other words|so )", re.I)
PROCESS = re.compile(r"\b(we'?ll|i'?ll|you'?ll|we can set up|next step|poc|two weeks|three weeks|"
                     r"first phase|pilot|we load|you run|let me|we would|i would|send me|send you|i'?m going to)\b", re.I)
QUESTION_START = re.compile(
    r"\b(what|where|how|why|when|who|which|can|could|do|does|did|is|are|would|will|should)\b", re.I)


# ---------------------------------------------------------------- data loading

@dataclass
class Knowledge:
    facts: list[dict]
    antifacts: list[dict]
    jargon: list[dict]
    signals: dict
    pages: dict[str, str]

    @classmethod
    def load(cls) -> "Knowledge":
        def jread(name: str, default):
            p = DATA / name
            if not p.exists():
                return default
            return json.loads(p.read_text(encoding="utf-8"))

        local = jread("facts_local.json", {"facts": [], "antifacts": []})
        curated = jread("facts.json", {"facts": [], "antifacts": []})
        facts = list(local.get("facts", [])) + list(curated.get("facts", []))
        antifacts = list(local.get("antifacts", [])) + list(curated.get("antifacts", []))
        jargon = jread("jargon.json", {"terms": []}).get("terms", [])
        signals = jread("signals.json", {"off_record": [], "risks": [], "opportunities": []})
        pages = {}
        raw = DATA / "raw_text.jsonl"
        if raw.exists():
            for line in raw.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                pages[rec["url"]] = rec.get("text", "")
        ext = DATA / "external.json"          # verified non-doc pages (about-us, track kit)
        if ext.exists():
            pages.update(json.loads(ext.read_text(encoding="utf-8")))
        return cls(facts, antifacts, jargon, signals, pages)

    # -- integrity ---------------------------------------------------------
    def self_check(self) -> list[str]:
        """Every citation must be a verbatim substring of a crawled page."""
        problems: list[str] = []
        for kind, items in (("fact", self.facts), ("antifact", self.antifacts)):
            for it in items:
                url, quote = it.get("source_url", ""), it.get("quote", "")
                text = self.pages.get(url)
                if text is None:
                    problems.append(f"{kind}:{it.get('id')} source_url not in corpus -> {url}")
                elif quote and quote not in text:
                    problems.append(f"{kind}:{it.get('id')} quote not verbatim in {url}")
        for kind in ("off_record", "opportunities"):
            for it in self.signals.get(kind, []):
                url = it.get("source_url")
                if url and url not in self.pages:
                    problems.append(f"signal:{it.get('id')} source_url not in corpus -> {url}")
        for t in self.jargon:
            url, quote = t.get("source_url", ""), t.get("quote", "")
            if url and url not in self.pages:
                problems.append(f"jargon:{t.get('term')} source_url not in corpus -> {url}")
            elif quote and quote not in self.pages.get(url, ""):
                problems.append(f"jargon:{t.get('term')} quote not verbatim")
        return problems


# ---------------------------------------------------------------- primitives

def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 3]


def _terms(text: str) -> set[str]:
    return set(tokenize(text))


def _distinctive(terms: set[str], floor: float = 3.0) -> set[str]:
    """Drop words that appear on hundreds of pages: matching them proves nothing.

    Without this, a long question like "can we time travel to see what the data
    looked like at month end" is dominated by 'data', 'see' and 'like', and the
    sentence that actually answers it scores as unrelated.
    """
    ix = index()
    return {t for t in terms if ix.idf.get(t, 0) >= floor} or terms


def _coverage(needles: set[str], haystack: str) -> float:
    if not needles:
        return 0.0
    return len(needles & _terms(haystack)) / len(needles)


def _is_question(s: str) -> bool:
    s = s.strip()
    return s.endswith("?") or bool(re.match(r"^(what|where|how|why|when|who|which|can|could|do|does|did|"
                                            r"is|are|would|will|should|have|has)\b", s, re.I))


# Nouns that make a sentence a statement about the product rather than small talk.
DOMAIN = set("""
iomete lakehouse warehouse spark iceberg kubernetes k8s cluster namespace catalog table tables
infrastructure perimeter datacenter datacentre gpu cpu memory nodes
compute storage bucket s3 gcs minio parquet query queries sql job jobs pipeline streaming
kafka compaction snapshot partition schema rbac sso saml oidc scim ldap okta entra identity
encryption encrypted kms governance lineage node nodes ide notebook notebooks jupyter jupyterlab
airflow dbt prefect bi tableau superset metabase redash dashboard ingestion ingest cdc etl elt
migration cloud on-prem onprem on-premises air-gapped airgapped sovereign deployment deploy
platform engine hive metastore retention masking pii audit compliance regulator latency
throughput sla tco delta hudi databricks snowflake cloudera proprietary open-source license
founded oracle federate federated internet licensing terabytes terabyte petabytes discount
arrow odbc flight jdbc sdk api pricing price support support team connect connector connectors
""".split())


# Words that appear in almost any sales sentence; on their own they do not make a
# sentence a checkable statement about the product.
GENERIC = set("platform product deployment deploy team support support cloud api sdk price pricing "
              "product solution customer company".split())


@dataclass
class Claim:
    id: str
    utt: int
    speaker: str
    t: int
    text: str
    verdict: str                 # sourced | contradicted | off_record | unsupported | commitment
    rule: str = ""
    severity: str = "info"
    quote: str = ""
    source_url: str = ""
    source_title: str = ""
    correction: str = ""
    say_instead: str = ""
    score: float = 0.0
    coverage: float = 0.0


@dataclass
class Analyzer:
    kb: Knowledge = field(default_factory=Knowledge.load)

    # -- rule tiers --------------------------------------------------------
    def _antifact(self, s: str) -> Claim | None:
        low = s.lower()
        # A denied need is not the wrong claim. "no outbound internet" and
        # "without internet" describe the air-gapped mode, so never read them as
        # an assertion that the product needs internet.
        denied = re.search(r"\b(no|without|never|zero)\s+(outbound\s+|public\s+)?internet", low)
        for a in self.kb.antifacts:
            if denied and a["id"] == "needs_internet_claim":
                continue
            for pat in a.get("wrong_pattern", []):
                if pat in low:
                    return Claim("", 0, "", 0, s, "contradicted", rule=a["id"],
                                 severity=a.get("severity", "block"), quote=a.get("quote", ""),
                                 source_url=a.get("source_url", ""),
                                 correction=a.get("correction", ""),
                                 say_instead=a.get("correction", ""))
        return None

    def _fact(self, s: str) -> Claim | None:
        """Fact rules confirm; they only accuse when the mismatch is mechanical.

        Entity/capability facts are confirmation-only: if the sentence names the
        topic but the expected value is absent, we fall through to retrieval
        instead of declaring the rep wrong. A false "contradicted" badge in front
        of a buyer costs more than a missed one, so only numbered slots (a year,
        a port) are allowed to contradict on their own.
        """
        low = " " + s.lower() + " "
        for f in self.kb.facts:
            triggers = f.get("triggers", [])
            if not any(re.search(rf"(?<![a-z0-9]){re.escape(tr.lower())}(?:s|es)?(?![a-z0-9])", low) for tr in triggers):
                continue
            expect = str(f.get("expect", "")).lower()
            kind = f.get("kind", "entity")
            ok = (bool(re.search(rf"\b{re.escape(expect)}\b", low)) if kind == "number"
                  else expect in low)
            if ok:
                return Claim("", 0, "", 0, s, "sourced", rule=f["id"],
                             severity=f.get("severity", "info"), quote=f.get("quote", ""),
                             source_url=f.get("source_url", ""),
                             say_instead=f.get("statement", ""))
            if kind == "number" and re.search(r"\d", s):
                return Claim("", 0, "", 0, s, "contradicted", rule=f["id"],
                             severity=f.get("severity", "block"), quote=f.get("quote", ""),
                             source_url=f.get("source_url", ""),
                             correction=f"{f.get('statement','')} — stated in IOMETE's own material.",
                             say_instead=f.get("statement", ""))
            return None
        return None

    def _off_record(self, s: str) -> Claim | None:
        low = s.lower()
        for o in self.kb.signals.get("off_record", []):
            if any(p in low for p in o.get("patterns", [])):
                return Claim("", 0, "", 0, s, "off_record", rule=o["id"],
                             severity=o.get("severity", "warn"),
                             correction=o.get("why", ""), say_instead=o.get("action", ""))
        return None

    def _retrieve(self, s: str) -> Claim | None:
        ix = index()
        known = _terms(s) & set(ix.idf)                 # ignore words the corpus never uses
        need = _distinctive(known)                      # and words that appear everywhere
        if len(known) < 2 or not need:
            return None
        hits = ix.search(s, 6)
        if not hits:
            return None
        # Pick the best-scoring page that actually covers the sentence, rather than
        # the best-scoring page overall: a long page about adjacent topics should
        # not beat the page that literally says the thing.
        qualified = [(h, _coverage(need, h.text)) for h in hits]
        qualified = [(h, c) for h, c in qualified if c >= SOURCED_MIN_COVERAGE]
        if not qualified:
            return None
        best, cov = max(qualified, key=lambda p: p[0].score)
        # A near-exact paraphrase of a documented sentence is support even when the
        # verb differs ("runs entirely within your infrastructure" vs "operates
        # entirely within your infrastructure"), so a very high coverage can carry a
        # lower lexical score.
        strong = best.score >= SOURCED_MIN_SCORE or (cov >= 0.75 and best.score >= 8)
        if strong:
            if ABSOLUTE.search(s) and best.score < SOURCED_MIN_SCORE * 1.3 and cov < 0.65:
                return None            # an absolute needs a strong, close source or nothing
            return Claim("", 0, "", 0, s, "sourced", rule="retrieval",
                         quote=_best_quote(s, best.text), source_url=best.url,
                         source_title=best.title, score=round(best.score, 2),
                         coverage=round(cov, 2))
        return None

    # -- one utterance -----------------------------------------------------
    def claims_for(self, utt: dict, utt_id: int) -> list[Claim]:
        if utt["speaker"] not in ("rep",):
            return []
        out: list[Claim] = []
        for s in sentences(utt["text"]):
            if _is_question(s) or len(s.split()) < 4:
                continue
            if CONTINUATION.match(s):
                continue        # a fragment of the previous sentence, not a new claim
            terms = _terms(s)
            on_topic = bool(terms & DOMAIN) or bool(jargon_hits(self.kb, s))
            if not on_topic:
                continue
            if PROCESS.search(s) and not ABSOLUTE.search(s):
                out.append(Claim("", utt_id, "rep", utt["t"], s, "commitment", rule="process"))
                continue
            if not ASSERTIVE.search(s) and not re.search(r"\d", s):
                continue
            c = self._antifact(s) or self._fact(s) or self._off_record(s) or self._retrieve(s)
            if c is None:
                if not (terms & DOMAIN) - GENERIC:
                    continue
                c = Claim("", utt_id, "rep", utt["t"], s, "unsupported", rule="no_source")
            c.utt = utt_id
            c.t = utt["t"]
            out.append(c)
        return out


def _best_quote(claim: str, page_text: str, max_chars: int = 260) -> str:
    """Pick the sentence of the page that best covers the claim, for the evidence chip."""
    need = _terms(claim)
    best, best_cov = "", -1.0
    for s in sentences(page_text.replace("\n", " ")):
        c = _coverage(need, s)
        if 30 < len(s) <= max_chars + 60 and c > best_cov:
            best, best_cov = s, c
    if not best:
        best = page_text.replace("\n", " ")[:max_chars]
    return best[:max_chars]


# ---------------------------------------------------------------- whole call

def jargon_hits(kb: Knowledge, text: str) -> list[dict]:
    low = " " + text.lower() + " "
    found = []
    for t in kb.jargon:
        names = [t["term"]] + list(t.get("aliases", []))
        for n in names:
            n = n.strip().lower()
            if not n:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(n)}(s|es)?(?![a-z0-9])", low):
                found.append(t)
                break
    return found


def analyze_call(kb: Knowledge, call: dict) -> dict:
    an = Analyzer(kb)
    trans = call["utterances"]
    claims: list[Claim] = []
    jargon_events: list[dict] = []
    seen_terms: set[str] = set()

    for i, u in enumerate(trans):
        claims.extend(an.claims_for(u, i))
        for t in jargon_hits(kb, u["text"]):
            if t["term"] not in seen_terms:
                seen_terms.add(t["term"])
                jargon_events.append({"term": t["term"], "plain": t.get("plain", ""),
                                      "why": t.get("why", ""), "source_url": t.get("source_url", ""),
                                      "t": u["t"], "utt": i})

    for n, c in enumerate(claims):
        c.id = f"c{n+1}"

    # ---- questions: answered if the rep's next reply is itself grounded
    questions = []
    for i, u in enumerate(trans):
        if u["speaker"] == "rep" or not _is_question(u["text"]):
            continue
        q = u["text"]
        answered = None
        # the rep's next two turns — but only count a reply that is actually about
        # the question, otherwise "what would a POC look like" gets attributed the
        # first sourced sentence that happens to follow it.
        # A question counts as answered only if the answering sentence cites a page
        # the question itself retrieves. Word overlap alone mis-attributes: "what
        # would a POC look like" was being credited to a later sentence about
        # snapshot time travel simply because it was the next grounded claim.
        def section(url: str) -> str:
            tail = url.split("/resources/", 1)[-1]
            return "/".join(tail.split("/")[:2])

        topic_pages = {section(h.url) for h in index().search(q, 6)}
        replies = [j for j in range(i + 1, min(i + 4, len(trans))) if trans[j]["speaker"] == "rep"][:1]
        for j in replies:
            grounded = [c for c in claims if c.utt == j and c.verdict == "sourced"]
            on_topic = [c for c in grounded if section(c.source_url) in topic_pages]
            if on_topic:
                g = on_topic[0]
                answered = {"url": g.source_url, "title": g.source_title or "",
                            "quote": g.quote, "by_claim": g.text}
                break
        questions.append({
            "id": f"q{len(questions)+1}", "utt": i, "t": u["t"], "speaker": u["speaker"],
            "text": q, "status": "answered" if answered else "open",
            "owner": "" if answered else ("security team" if re.search(r"security|soc|pen|compliance|audit|data live", q, re.I)
                                          else "account team"),
            "evidence": answered,
        })

    # ---- risks (whole call, both sides)
    blob = " ".join(u["text"] for u in trans).lower()
    risks = []
    for r in kb.signals.get("risks", []):
        if "__derived__" in r.get("patterns", []):
            bad = [c for c in claims if c.verdict in ("contradicted", "off_record")]
            if bad:
                risks.append({"id": r["id"], "tag": r["tag"], "severity": r.get("severity"),
                              "why": r.get("why"), "owner": r.get("owner"),
                              "evidence": [c.text for c in bad][:3]})
            continue
        hit = [p for p in r.get("patterns", []) if p in blob]
        if hit:
            risks.append({"id": r["id"], "tag": r["tag"], "severity": r.get("severity", "medium"),
                          "why": r.get("why", ""), "owner": r.get("owner", ""), "evidence": hit[:3]})

    # ---- offers: documented capability that fits, never pitched
    pitched = blob
    offers = []
    for o in kb.signals.get("opportunities", []):
        if any(p in pitched for p in o.get("patterns", [])):
            continue                       # the buyer/rep already went here
        offers.append({"id": o["id"], "tag": o["tag"], "capability": o["capability"],
                       "pitch": o["pitch"], "source_url": o.get("source_url", "")})
    matched = [o for o in kb.signals.get("opportunities", [])
               if any(p in pitched for p in o.get("patterns", []))]

    # ---- metrics
    counts = {v: sum(1 for c in claims if c.verdict == v)
              for v in ("sourced", "contradicted", "off_record", "unsupported", "commitment")}
    judged = counts["sourced"] + counts["contradicted"] + counts["off_record"] + counts["unsupported"]
    words = sum(len(u["text"].split()) for u in trans)
    metrics = {
        "claims": judged,
        "sourced": counts["sourced"],
        "contradicted": counts["contradicted"],
        "off_record": counts["off_record"],
        "unsupported": counts["unsupported"],
        "commitments": counts["commitment"],
        "grounded_rate": round(100 * counts["sourced"] / judged) if judged else 0,
        "problem_rate": round(100 * (counts["contradicted"] + counts["off_record"]) / judged) if judged else 0,
        "jargon_terms": len(jargon_events),
        "jargon_density": round(100 * len(jargon_events) / max(1, words), 2),
        "open_questions": sum(1 for q in questions if q["status"] == "open"),
        "words": words,
    }

    return {
        "deal": call.get("deal", {}),
        "speakers": call.get("speakers", {}),
        "utterances": trans,
        "claims": [asdict(c) for c in claims],
        "jargon": jargon_events,
        "questions": questions,
        "risks": risks,
        "offers": offers,
        "matched_offers": [{"id": o["id"], "tag": o["tag"], "capability": o["capability"],
                            "pitch": o["pitch"], "source_url": o.get("source_url", "")} for o in matched],
        "metrics": metrics,
    }


def deal_brief(result: dict) -> dict:
    """The one-pager both sides leave the call with."""
    m = result["metrics"]
    bad = [c for c in result["claims"] if c["verdict"] in ("contradicted", "off_record")]
    return {
        "headline": f"{m['grounded_rate']}% of the claims made in this call are backed by IOMETE documentation.",
        "corrected": [{"said": c["text"], "verdict": c["verdict"], "fix": c["say_instead"] or c["correction"],
                       "source": c["source_url"] or None} for c in bad],
        "unverified": [{"said": c["text"]} for c in result["claims"] if c["verdict"] == "unsupported"],
        "open_questions": [{"question": q["text"], "owner": q["owner"]} for q in result["questions"] if q["status"] == "open"],
        "answered_questions": [{"question": q["text"], "source": (q["evidence"] or {}).get("url")}
                               for q in result["questions"] if q["status"] == "answered"],
        "risks": [{"risk": r["tag"], "severity": r["severity"], "owner": r["owner"]} for r in result["risks"]],
        "never_pitched": [{"capability": o["capability"], "why_now": o["pitch"], "source": o["source_url"]}
                          for o in result["offers"]],
        "buyer_glossary": [{"term": j["term"], "plain": j["plain"]} for j in result["jargon"]],
        "next_step": _next_step(result),
    }


def _next_step(result: dict) -> str:
    m = result["metrics"]
    if m["contradicted"]:
        return "Send a short correction in writing today for the claims flagged in red, before the buyer repeats them internally."
    if any(r["id"] == "security_gate" for r in result["risks"]):
        return "Send the trust-centre link and current attestation, and confirm the pen-test date. Security gates everything downstream."
    if m["open_questions"]:
        return "Answer the open questions in writing, then ask for a 45-minute technical session with the platform team."
    return "Send the one-pager and propose the technical session."


if __name__ == "__main__":
    kb = Knowledge.load()
    problems = kb.self_check()
    print(f"knowledge: {len(kb.facts)} facts, {len(kb.antifacts)} antifacts, "
          f"{len(kb.jargon)} jargon terms, {len(kb.pages)} pages")
    if problems:
        print(f"\n!! {len(problems)} citation problems")
        for p in problems[:20]:
            print("  ", p)
    else:
        print("citation check: all quotes verbatim ✓")
    call = json.loads((DATA / "transcript_demo.json").read_text(encoding="utf-8"))
    r = analyze_call(kb, call)
    print("\n--- claims")
    for c in r["claims"]:
        print(f"  {c['verdict']:13} {c['rule'][:16]:16} {c['text'][:86]}")
        if c["source_url"]:
            print(f"                -> {c['source_url']}")
    print("\n--- metrics", json.dumps(r["metrics"]))
    print("--- questions")
    for q in r["questions"]:
        print(f"  {q['status']:9} {q['owner']:9} {q['text'][:80]}")
    print("--- risks", [x["tag"] for x in r["risks"]])
    print("--- never pitched", [x["capability"] for x in r["offers"]])
    print("--- jargon", [j["term"] for j in r["jargon"]])
