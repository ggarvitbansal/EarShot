"""Score the engine against hand-labelled sentences and print an honest report.

The number that matters for a fact-checker is not accuracy, it is the false
accusation rate: how often we tell a rep they are wrong when they are not. That
column is printed separately and deliberately.
"""
from __future__ import annotations

import json
from pathlib import Path

from .analyze import Analyzer, Knowledge

DATA = Path(__file__).resolve().parent.parent / "data"


def run(verbose: bool = True) -> dict:
    kb = Knowledge.load()
    an = Analyzer(kb)
    cases = json.loads((DATA / "eval_set.json").read_text(encoding="utf-8"))["cases"]
    rows = []
    for c in cases:
        got = an.claims_for({"speaker": "rep", "text": c["text"], "t": 0}, 0)
        verdict = got[0].verdict if got else "none"
        rule = got[0].rule if got else "-"
        rows.append({**c, "got": verdict, "rule": rule, "ok": verdict == c["expect"]})

    judged = [r for r in rows if r["expect"] != "unsupported"]
    correct = sum(1 for r in rows if r["ok"])
    # precision/recall on the "this is a problem" decision (contradicted + off_record)
    flagged_expected = {r["id"] for r in rows if r["expect"] in ("contradicted", "off_record")}
    flagged_got = {r["id"] for r in rows if r["got"] in ("contradicted", "off_record")}
    tp = len(flagged_expected & flagged_got)
    false_accusations = [r for r in rows if r["got"] == "contradicted" and r["expect"] != "contradicted"]

    report = {
        "cases": len(rows),
        "exact_match": correct,
        "exact_match_rate": round(100 * correct / len(rows)),
        "flag_precision": round(100 * tp / len(flagged_got)) if flagged_got else None,
        "flag_recall": round(100 * tp / len(flagged_expected)) if flagged_expected else None,
        "false_accusations": [{"text": r["text"], "expected": r["expect"], "got": r["got"]} for r in false_accusations],
        "misses": [{"text": r["text"], "expected": r["expect"], "got": r["got"]}
                   for r in rows if not r["ok"]],
        "rows": rows,
        "note": "Labelled by hand against IOMETE's public docs, including cases the engine fails.",
    }
    if verbose:
        for r in rows:
            mark = "ok  " if r["ok"] else "MISS"
            print(f"{mark} {r['id']} {r['expect']:13} -> {r['got']:13} [{r['rule'][:18]:18}] {r['text'][:74]}")
        print(f"\nexact match      {correct}/{len(rows)}  ({report['exact_match_rate']}%)")
        print(f"flag precision   {report['flag_precision']}%")
        print(f"flag recall      {report['flag_recall']}%")
        print(f"false accusations {len(false_accusations)}")
        for r in false_accusations:
            print("   !!", r["text"])
    return report


if __name__ == "__main__":
    run()
