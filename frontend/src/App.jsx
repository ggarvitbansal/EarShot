import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/* ------------------------------------------------------------------ helpers */

const VERDICT = {
  sourced:      { label: "Sourced",      glyph: "✓", cls: "v-sourced",      note: "documentation backs this" },
  contradicted: { label: "Contradicted", glyph: "✕", cls: "v-contradicted", note: "the docs say otherwise" },
  off_record:   { label: "Off record",   glyph: "⛔", cls: "v-offrecord",   note: "never answer this on a call" },
  unsupported:  { label: "No source",    glyph: "?", cls: "v-unsupported",  note: "not in public docs" },
  commitment:   { label: "Promise",      glyph: "→", cls: "v-commitment",   note: "a commitment, not a claim" },
};

const pct = (n) => `${Math.round(n)}%`;
const slug = (url) => {
  if (!url) return "";
  const m = url.match(/resources\/(.+?)(#|$)/);
  if (m) return m[1].replace(/\/$/, "");
  return url.replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0];
};

function Ring({ value, size = 76, stroke = 7 }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const tone = value > 80 ? "green" : value > 50 ? "amber" : "red";
  return (
    <svg width={size} height={size} className={`ring ring-${tone}`} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={r} className="ring-track" strokeWidth={stroke} fill="none" />
      <circle
        cx={size / 2} cy={size / 2} r={r} className="ring-fill" strokeWidth={stroke} fill="none"
        strokeDasharray={c}
        strokeDashoffset={c - (Math.max(0, Math.min(100, value)) / 100) * c}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}

/* --------------------------------------------------------------------- app */

export default function App() {
  const [variant, setVariant] = useState("demo");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [view, setView] = useState("call");
  const [brief, setBrief] = useState(null);
  const [liveOpen, setLiveOpen] = useState(false);
  const transcriptRef = useRef(null);

  useEffect(() => {
    let dead = false;
    setData(null); setError(null); setIdx(0); setPlaying(true); setBrief(null);
    fetch(`/api/call/${variant}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((json) => { if (!dead) setData(json); })
      .catch((e) => { if (!dead) setError(e.message); });
    return () => { dead = true; };
  }, [variant]);

  useEffect(() => {
    if (view !== "brief" || !data || brief) return;
    fetch(`/api/brief/${variant}`).then((r) => r.json()).then(setBrief).catch(() => {});
  }, [view, variant, data, brief]);

  const total = data?.utterances.length ?? 0;

  useEffect(() => {
    if (!playing || !total) return;
    if (idx >= total) { setPlaying(false); return; }
    const t = setTimeout(() => setIdx((i) => Math.min(total, i + 1)), 1700 / speed);
    return () => clearTimeout(t);
  }, [playing, idx, total, speed]);

  useEffect(() => {
    const el = transcriptRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [idx]);

  const shown = useMemo(() => {
    if (!data) return null;
    const claims = data.claims.filter((c) => c.utt < idx);
    const u = { sourced: 0, contradicted: 0, off_record: 0, unsupported: 0, commitment: 0 };
    claims.forEach((c) => { u[c.verdict] = (u[c.verdict] || 0) + 1; });
    const judged = u.sourced + u.contradicted + u.off_record + u.unsupported;
    return {
      claims, counts: u, judged,
      grounded: judged ? (100 * u.sourced) / judged : 0,
      jargon: data.jargon.filter((j) => j.utt < idx),
      questions: data.questions.filter((q) => q.utt < idx),
    };
  }, [data, idx]);

  const restart = useCallback(() => { setIdx(0); setPlaying(true); }, []);

  if (error) return (
    <div className="shell">
      <div className="fatal">
        API not reachable ({error}).<br />
        Start it with <code>uvicorn app:app --port 8010</code> inside <code>backend/</code>.
      </div>
    </div>
  );
  if (!data || !shown) return <div className="shell"><div className="boot"><span className="spinner" /> indexing 262 documentation pages…</div></div>;

  const { deal, speakers, utterances, risks, offers, metrics } = data;
  const finished = idx >= total;

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <Mark />
          <div>
            <h1>Earshot</h1>
            <p>the neutral third seat in the deal</p>
          </div>
        </div>

        <div className="dealname">
          <span className="live" data-on={!finished} />
          <div>
            <strong>{deal.name}</strong>
            <small>{deal.industry} · {deal.buyer_role}</small>
          </div>
        </div>

        <div className="scoreblock">
          <Ring value={view === "brief" ? metrics.grounded_rate : shown.grounded} />
          <div className="scoretext">
            <b>{pct(view === "brief" ? metrics.grounded_rate : shown.grounded)}</b>
            <small>of claims backed<br />by documentation</small>
          </div>
        </div>

        <div className="controls">
          <div className="seg">
            <button className={variant === "demo" ? "on" : ""} onClick={() => setVariant("demo")}>Original call</button>
            <button className={variant === "fixed" ? "on" : ""} onClick={() => setVariant("fixed")}>With corrections</button>
          </div>
          <div className="seg">
            <button className={view === "call" ? "on" : ""} onClick={() => setView("call")}>Live</button>
            <button className={view === "brief" ? "on" : ""} onClick={() => setView("brief")}>Brief</button>
          </div>
          <button className="ghost" onClick={() => setLiveOpen(true)} title="Analyse your own transcript">Live input</button>
        </div>
      </header>

      {view === "call" && (
        <>
          <Timeline
            claims={data.claims}
            shownClaims={shown.claims}
            total={total}
            idx={idx}
            onScrub={(n) => { setPlaying(false); setIdx(n); }}
          />

          <div className="board">
            <section className="col transcript">
              <div className="colhead">
                <h2>Conversation</h2>
                <div className="replay">
                  <button className="mini" onClick={() => setPlaying((p) => !p)}>{playing ? "❚❚" : "▶"}</button>
                  <button className="mini" onClick={restart}>↺</button>
                  <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
                    <option value={1}>1×</option>
                    <option value={2}>2×</option>
                    <option value={4}>4×</option>
                  </select>
                  <span className="clock">{utterances[Math.max(0, idx - 1)]?.t ?? 0}s</span>
                </div>
              </div>
              <div className="stream" ref={transcriptRef}>
                {utterances.slice(0, idx).map((u, i) => {
                  const sp = speakers[u.speaker] || { name: u.speaker, role: "" };
                  return (
                    <div key={i} className={`bubble ${u.speaker === "rep" ? "rep" : "buyer"} fresh`}>
                      <div className="who">{sp.name}<em>{sp.role}</em></div>
                      <p>{u.text}</p>
                    </div>
                  );
                })}
                {!finished && <div className="typing"><i /><i /><i /></div>}
              </div>
            </section>

            <section className="col ledger">
              <div className="colhead">
                <h2>Claims ledger</h2>
                <span className="sub">every factual claim, checked against the docs</span>
              </div>
              <div className="cards">
                {shown.claims.length === 0 && <div className="empty">waiting for the first claim…</div>}
                {shown.claims.slice().reverse().map((c) => <ClaimCard key={c.id} c={c} />)}
              </div>
            </section>

            <section className="col buyerlane">
              <div className="colhead">
                <h2>Buyer lane</h2>
                <span className="sub">what the words actually mean</span>
              </div>

              <div className="density">
                <div className="bar">
                  <div className="fill" style={{ width: `${Math.min(100, shown.jargon.length * 3.4)}%` }} />
                  <span className="target" style={{ left: "34%" }} title="a buyer-safe call runs under 2 unexplained terms per 100 words" />
                </div>
                <div className="densrow">
                  <span><b>{shown.jargon.length}</b> terms need translating</span>
                  <span className="muted">{metrics.jargon_density}/100 words · target &lt;2</span>
                </div>
              </div>

              <div className="glossary">
                {shown.jargon.slice().reverse().map((j, i) => (
                  <div key={j.term + i} className="term fresh">
                    <div className="termname">{j.term}</div>
                    <div className="plain">{j.plain}</div>
                    {j.why && <div className="why">{j.why}</div>}
                  </div>
                ))}
              </div>

              <div className="questions">
                <h3>Questions asked</h3>
                {shown.questions.length === 0 && <div className="empty sm">none yet</div>}
                {shown.questions.map((q) => (
                  <div key={q.id} className={`q ${q.status}`}>
                    <span className="qmark">{q.status === "answered" ? "✓" : "!"}</span>
                    <div>
                      <p>{q.text}</p>
                      {q.status === "answered" && q.evidence
                        ? <a href={q.evidence.url} target="_blank" rel="noreferrer" className="cite">{slug(q.evidence.url)} ↗</a>
                        : <small className="owner">open · owner: IOMETE {q.owner}</small>}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <DealStrip
            risks={risks}
            offers={offers}
            next={brief?.next_step || fallbackNext(shown)}
            grounded={shown.grounded}
          />
        </>
      )}

      {view === "brief" && <Brief brief={brief} data={data} />}
      {liveOpen && <LiveInput onClose={() => setLiveOpen(false)} />}
    </div>
  );
}

function fallbackNext(shown) {
  if (shown.counts.contradicted) return "Send a written correction today for the claims flagged in red, before the buyer repeats them internally.";
  if (shown.counts.off_record) return "Send the trust-centre link and the current attestation in writing. Security gates everything downstream.";
  return "Send the one-pager and propose the 45-minute technical session.";
}

/* ----------------------------------------------------------------- widgets */

function ClaimCard({ c }) {
  const v = VERDICT[c.verdict] || VERDICT.unsupported;
  return (
    <article className={`card ${v.cls} fresh`}>
      <div className="cardtop">
        <span className="pill">{v.glyph} {v.label}</span>
        <span className="rule">{c.rule.replace(/_/g, " ")}</span>
      </div>
      <p className="said">“{c.text}”</p>

      {c.verdict === "contradicted" && (
        <div className="sayinstead">
          <span>Should have been</span>
          <p>{c.correction || c.say_instead}</p>
        </div>
      )}
      {c.verdict === "off_record" && (
        <div className="sayinstead">
          <span>Why it is off record</span>
          <p>{c.correction}</p>
          {c.say_instead && <p className="action">→ {c.say_instead}</p>}
        </div>
      )}
      {(c.verdict === "sourced" || c.verdict === "contradicted") && c.source_url && (
        <div className="evidence">
          <blockquote>{c.quote}</blockquote>
          <a href={c.source_url} target="_blank" rel="noreferrer" className="cite">{slug(c.source_url)} ↗</a>
        </div>
      )}
      {c.verdict === "unsupported" && (
        <div className="note">Nothing in the corpus supports this. Say “let me confirm and send it in writing.”</div>
      )}
    </article>
  );
}

function Timeline({ claims, shownClaims, total, idx, onScrub }) {
  const shownIds = new Set(shownClaims.map((c) => c.id));
  const maxT = Math.max(300, ...claims.map((c) => c.t));
  const ratio = idx / Math.max(1, total);
  const seek = (e) => {
    const box = e.currentTarget.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width));
    onScrub(Math.round(f * total));
  };
  return (
    <div className="timeline" onClick={seek} title="click to jump anywhere in the call">
      <div className="tl-progress" style={{ width: `${ratio * 100}%` }} />
      <div className="tl-playhead" style={{ left: `${ratio * 100}%` }} />
      {claims.map((c) => (
        <span
          key={c.id}
          className={`tl-dot ${VERDICT[c.verdict]?.cls || ""} ${shownIds.has(c.id) ? "" : "dim"}`}
          style={{ left: `${Math.min(98, (c.t / maxT) * 100)}%` }}
          title={`${VERDICT[c.verdict]?.label}: ${c.text}`}
        />
      ))}
      <span className="tl-axis">0s</span>
      <span className="tl-hint">each dot is a claim · click to scrub</span>
      <span className="tl-axis end">{Math.round(maxT)}s</span>
    </div>
  );
}

function DealStrip({ risks, offers, next, grounded }) {
  return (
    <div className="strip">
      <div className="panel">
        <h3>Deal risks</h3>
        {risks.length === 0 && <div className="empty sm">none detected</div>}
        {risks.map((r) => (
          <div key={r.id} className={`risk sev-${r.severity}`}>
            <span className="tag">{r.severity}</span>
            <div>
              <b>{r.tag}</b>
              <small>{r.why}</small>
            </div>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3>Documented, never pitched</h3>
        <p className="hint">capabilities that fit this buyer's pain and went unsaid</p>
        {offers.length === 0 && <div className="empty sm">nothing left on the table</div>}
        {offers.slice(0, 4).map((o) => (
          <div key={o.id} className="offer">
            <b>{o.capability}</b>
            <small>{o.pitch}</small>
            {o.source_url && <a href={o.source_url} target="_blank" rel="noreferrer" className="cite">{slug(o.source_url)} ↗</a>}
          </div>
        ))}
      </div>
      <div className="panel next">
        <h3>Next best action</h3>
        <p>{next}</p>
        <div className="nextscore">
          <Ring value={grounded} size={56} stroke={5} />
          <small>of what was said on this call is checkable. That is the number the buyer repeats internally.</small>
        </div>
      </div>
    </div>
  );
}

function Brief({ brief, data }) {
  if (!brief) return <div className="boot"><span className="spinner" /> writing the brief…</div>;
  return (
    <div className="briefwrap">
      <div className="brief">
        <div className="bhead">
          <div>
            <h1>Mutual action plan</h1>
            <p>{data.deal.name} · prepared by Earshot · every line is sourced or marked as an unknown</p>
          </div>
          <div className="stamp">no cloud calls<br />made to build this</div>
        </div>
        <p className="headline">{brief.headline}</p>

        {brief.corrected.length > 0 && (
          <section>
            <h2>Corrected before the buyer repeats it</h2>
            {brief.corrected.map((c, i) => (
              <div className="brow bad" key={i}>
                <div className="bsaid">{c.said}</div>
                <div className="bfix">{c.fix}</div>
                {c.source && <a href={c.source} target="_blank" rel="noreferrer" className="cite">{slug(c.source)} ↗</a>}
              </div>
            ))}
          </section>
        )}

        {brief.open_questions.length > 0 && (
          <section>
            <h2>Open, with an owner</h2>
            {brief.open_questions.map((q, i) => (
              <div className="brow" key={i}>
                <div className="bsaid">{q.question}</div>
                <div className="bowner">{q.owner}</div>
              </div>
            ))}
          </section>
        )}

        {brief.answered_questions.length > 0 && (
          <section>
            <h2>Answered, with the page</h2>
            {brief.answered_questions.map((q, i) => (
              <div className="brow" key={i}>
                <div className="bsaid">{q.question}</div>
                {q.source && <a href={q.source} target="_blank" rel="noreferrer" className="cite">{slug(q.source)} ↗</a>}
              </div>
            ))}
          </section>
        )}

        <section>
          <h2>Still on the table</h2>
          {brief.never_pitched.map((o, i) => (
            <div className="brow" key={i}>
              <div className="bsaid">{o.capability}</div>
              <div className="bfix">{o.why_now}</div>
            </div>
          ))}
        </section>

        <section className="bnext">
          <h2>Next step</h2>
          <p>{brief.next_step}</p>
        </section>
      </div>
    </div>
  );
}

function LiveInput({ onClose }) {
  const [text, setText] = useState(
    "rep: The platform runs on Apache Spark and the tables are Delta Lake.\n" +
    "buyer: And where does our data sit?\n" +
    "rep: We're SOC 2 Type II certified and it's about forty thousand a year."
  );
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);

  const run = () => {
    setBusy(true);
    fetch("/api/analyze", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, name: "Live call" }),
    }).then((r) => r.json()).then(setResult).catch(() => setResult({ error: true })).finally(() => setBusy(false));
  };

  const mic = () => {
    if (listening) { recRef.current?.stop(); setListening(false); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert("No speech recognition in this browser. Type or paste instead — the engine is identical."); return; }
    const rec = new SR();
    rec.continuous = true; rec.interimResults = false; rec.lang = "en-IN";
    rec.onresult = (e) => {
      const said = e.results[e.results.length - 1][0].transcript.trim();
      setText((t) => `${t}\nrep: ${said}`);
    };
    rec.onend = () => setListening(false);
    rec.start(); recRef.current = rec; setListening(true);
  };

  return (
    <div className="modal" onClick={onClose}>
      <div className="modalbox" onClick={(e) => e.stopPropagation()}>
        <div className="modalhead">
          <h2>Live input</h2>
          <button className="ghost" onClick={onClose}>close</button>
        </div>
        <p className="hint">One turn per line, prefixed <code>rep:</code> or <code>buyer:</code>. Voice is optional and only fills this box.</p>
        <textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} />
        <div className="modalrow">
          <button className="primary" onClick={run} disabled={busy}>{busy ? "analysing…" : "Analyse"}</button>
          <button className="ghost" onClick={mic}>{listening ? "◼ stop listening" : "🎙 use microphone"}</button>
        </div>
        {result && !result.error && (
          <div className="mini-result">
            <p className="hint">
              grounded {result.metrics.grounded_rate}% · {result.metrics.contradicted} contradicted ·
              {" "}{result.metrics.off_record} off record · {result.metrics.unsupported} unsourced
            </p>
            {result.claims.map((c, i) => (
              <div className={`card ${VERDICT[c.verdict]?.cls}`} key={i}>
                <div className="cardtop">
                  <span className="pill">{VERDICT[c.verdict]?.glyph} {VERDICT[c.verdict]?.label}</span>
                </div>
                <p className="said">“{c.text}”</p>
                {c.correction && <div className="sayinstead"><p>{c.correction}</p></div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Mark() {
  return (
    <svg className="mark" viewBox="0 0 40 40" width="38" height="38">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#7DD3FC" />
          <stop offset="100%" stopColor="#34D399" />
        </linearGradient>
      </defs>
      <path d="M4 20c5-8 10-12 16-12s11 4 16 12c-5 8-10 12-16 12S9 28 4 20Z" fill="none" stroke="url(#g)" strokeWidth="2.2" />
      <circle cx="20" cy="20" r="5.2" fill="url(#g)" opacity="0.9" />
      <circle cx="20" cy="20" r="1.8" fill="#05080C" />
    </svg>
  );
}
