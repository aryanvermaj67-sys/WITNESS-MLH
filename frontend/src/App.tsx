import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import * as api from "./api";
import type {
  BackupAnswer, DemoQuestion, DocumentInfo, EvalResult, FinalLabel, FinalVerdict, Health, JudgeVerdict, Label, Passage,
  PipelineResult, ReplayEntry, TrustScore, Claim,
} from "./types";

// ---------------------------------------------------------------------------------------------
// Shared bits
// ---------------------------------------------------------------------------------------------
type Verdict = "supported" | "unsupported" | "contradicted" | "review";
type Tab = "ask" | "grade" | "results" | "eval";
type Row = { claim: Claim; v: FinalVerdict };

const ORDER: Verdict[] = ["supported", "unsupported", "contradicted", "review"];
const toVerdict = (l: FinalLabel | Label): Verdict => (l === "needs_review" ? "review" : l);

const verdicts: Record<Verdict, { label: string; icon: string; meaning: string }> = {
  supported: { label: "Supported", icon: "✓", meaning: "The sources say it" },
  unsupported: { label: "Unsupported", icon: "?", meaning: "Not found in the sources, not necessarily false" },
  contradicted: { label: "Contradicted", icon: "×", meaning: "The sources say the opposite" },
  review: { label: "Needs review", icon: "!", meaning: "The two judges disagree" },
};

function store(key: string, value?: string): string | null {
  try {
    if (value !== undefined) localStorage.setItem(key, value);
    return localStorage.getItem(key);
  } catch {
    return null; // private window or blocked storage: the app works without it
  }
}

function rowsOf(r: PipelineResult | null): Row[] {
  if (!r) return [];
  return r.claims.flatMap((claim) => {
    const v = r.verdicts.find((x) => x.claim_id === claim.id);
    return v ? [{ claim, v }] : [];
  });
}

// "gemma-4-26b-a4b-it (Gemini API)" -> "gemma-4-26b-a4b-it": the health text carries a long explanation in brackets
const modelName = (s: string | undefined, fallback: string) => (s ? s.replace(/\s*\(.*?\)\s*/g, "").replace(/^.*\//, "").trim() : fallback);

const firstToInspect =(rows: Row[]) => (rows.find((r) => r.v.label !== "supported") ?? rows[0])?.claim.id ?? null;

function Icon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
    play: <path d="m8 5 11 7-11 7V5Z" />,
    shield: <path d="M12 3 4.5 6v5.5c0 4.6 3.2 7.8 7.5 9.5 4.3-1.7 7.5-4.9 7.5-9.5V6L12 3Z" />,
    file: <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5M9 13h6M9 17h5" /></>,
    arrow: <><path d="M5 12h14M14 7l5 5-5 5" /></>,
    spark: <><path d="m12 3 1.2 4.2L17 9l-3.8 1.8L12 15l-1.2-4.2L7 9l3.8-1.8L12 3Z" /><path d="m18 15 .7 2.3L21 18l-2.3.7L18 21l-.7-2.3L15 18l2.3-.7L18 15Z" /></>,
    chevron: <path d="m8 10 4 4 4-4" />,
  };
  return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}

function LabelBadge({ verdict, compact = false }: { verdict: Verdict; compact?: boolean }) {
  const v = verdicts[verdict];
  return <span className={`label-badge ${verdict} ${compact ? "compact" : ""}`}><b aria-hidden="true">{v.icon}</b>{v.label}</span>;
}

function Toggle({ on, label, onToggle }: { on: boolean; label: string; onToggle: () => void }) {
  return <button className="toggle-wrap" onClick={onToggle} aria-pressed={on}><span className={`toggle ${on ? "on" : ""}`}><i /></span><span>{label}</span></button>;
}

// ---------------------------------------------------------------------------------------------
// Top bar, banners, tabs
// ---------------------------------------------------------------------------------------------
function TopBar({ health, down, mode, projector, setMode, setProjector }: {
  health: Health | null; down: boolean; mode: "live" | "replay"; projector: boolean;
  setMode: (m: "live" | "replay") => void; setProjector: (v: boolean) => void;
}) {
  const state = (ok: boolean | undefined): boolean | null => (down ? false : ok ?? null);
  const pills: { name: string; ok: boolean | null; tip: string }[] = [
    { name: "Backend", ok: down ? false : health ? health.status === "ok" : null, tip: down ? "Backend not reachable" : "WITNESS server" },
    { name: "LM Studio", ok: state(health?.lmstudio), tip: health?.models.writer ?? "Local answer writer" },
    { name: "Gemini", ok: state(health?.gemini_key), tip: health ? `${health.models.judge_1} (Gemini API key ${health.gemini_key ? "set" : "missing"})` : "Gemini API" },
    { name: "NLI", ok: state(health?.nli_loaded), tip: health?.models.judge_2 ?? "Local NLI judge" },
  ];
  return <header className="topbar">
    <div className="brand"><span className="brand-mark"><Icon name="shield" /></span><strong>WITNESS</strong><span className="tagline">Every claim, with proof</span></div>
    <div className="health" aria-label="Service health">
      {pills.map((p) => <span key={p.name} className="health-pill" title={p.tip}><i className={p.ok === null ? "unknown" : p.ok ? "" : "down"} />{p.name}</span>)}
    </div>
    <div className="top-actions">
      <div className="segment" aria-label="Data mode">
        <button className={mode === "live" ? "active" : ""} onClick={() => setMode("live")}>Live</button>
        <button className={mode === "replay" ? "active" : ""} onClick={() => setMode("replay")}>Replay</button>
      </div>
      <Toggle on={projector} label="Projector" onToggle={() => setProjector(!projector)} />
    </div>
  </header>;
}

function Banners({ replay, errors }: { replay: boolean; errors: string[] }) {
  return <div className="banners">
    {errors.length > 0 && <div className="banner error"><b>Attention needed</b><span>{errors.join(" ")}</span></div>}
    {replay && <div className="banner replay"><b>Replay mode</b><span>Viewing saved output. This is not a live result.</span></div>}
  </div>;
}

function WorkspaceTabs({ active, setActive, showEval }: { active: Tab; setActive: (v: Tab) => void; showEval: boolean }) {
  const tabs: Tab[] = showEval ? ["ask", "grade", "results", "eval"] : ["ask", "grade", "results"];
  const name = (t: Tab) => (t === "grade" ? "Grade any AI" : t === "eval" ? "Evaluation" : t[0].toUpperCase() + t.slice(1));
  return <nav className="tabs" aria-label="Workspace">{tabs.map((x) => <button key={x} className={active === x ? "active" : ""} onClick={() => setActive(x)}>{name(x)}</button>)}</nav>;
}

// ---------------------------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------------------------
function SourcePicker({ documents, selected, uploading, error, onSelect, onUpload, onRemove }: {
  documents: DocumentInfo[]; selected: string | null; uploading: boolean; error: string | null;
  onSelect: (id: string | null) => void; onUpload: (f: File) => void; onRemove: (id: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const doc = documents.find((d) => d.id === selected);
  return <div className="source-row">
    <label htmlFor="source">Check against</label>
    <select id="source" value={selected ?? ""} onChange={(e) => onSelect(e.target.value || null)}>
      <option value="">Event handbook</option>
      {documents.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
    </select>
    <input ref={input} type="file" accept="application/pdf,.pdf" hidden aria-label="Upload a PDF"
      onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onUpload(f); }} />
    <button className="secondary" disabled={uploading} onClick={() => input.current?.click()}>{uploading ? <><span className="spinner" />Reading PDF…</> : "Upload a PDF"}</button>
    {doc && <button className="secondary" onClick={() => onRemove(doc.id)}>Remove</button>}
    <small>{doc ? `${doc.pages} pages · ${doc.passages} passages · kept in memory only, never saved` : "Or check against your own PDF."}</small>
    {error && <span className="source-error" role="alert">{error}</span>}
  </div>;
}

function AskPanel({ questions, running, onRun, source, ownDocument }: { questions: DemoQuestion[]; running: boolean; onRun: (q: string) => void; source: ReactNode; ownDocument: boolean }) {
  const [value, setValue] = useState("");
  const submit = () => value.trim() && !running && onRun(value.trim());
  return <section className="input-panel">
    <label htmlFor="question">{ownDocument ? "Ask about your PDF" : "Ask about this event"}</label>
    <div className="question-row">
      <input id="question" value={value} placeholder={ownDocument ? "Type a question about your document" : "Type a question about the event rules"} maxLength={500} onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} />
      <button className="primary" disabled={running || !value.trim()} onClick={submit}>{running ? <><span className="spinner" />Checking…</> : <><Icon name="search" />Run check</>}</button>
    </div>
    {!ownDocument && questions.length > 0 && <div className="chips"><span>Try:</span>{questions.map((q) => <button key={q.id} onClick={() => setValue(q.question)}>{q.question}</button>)}</div>}
    {source}
  </section>;
}

function GradePanel({ backups, running, onRun, source }: { backups: BackupAnswer[]; running: boolean; onRun: (q: string, a: string) => void; source: ReactNode }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const ready = question.trim() && answer.trim() && !running;
  return <section className="input-panel grade-panel">
    <div className="panel-head"><div><span className="eyebrow">Independent verification</span><h2>Grade any AI answer</h2></div>
      <select aria-label="Load backup answer" value="" onChange={(e) => { const b = backups.find((x) => x.id === e.target.value); if (b) { setQuestion(b.question); setAnswer(b.answer); } }}>
        <option value="">Load backup answer…</option>
        {backups.map((b) => <option key={b.id} value={b.id}>{b.question.slice(0, 60)}{b.is_example ? " (example)" : ""}</option>)}
      </select></div>
    {source}
    <label htmlFor="grade-question">Original question</label>
    <input id="grade-question" value={question} maxLength={500} placeholder="The question the AI was asked" onChange={(e) => setQuestion(e.target.value)} />
    <label htmlFor="pasted-answer">AI answer to check</label>
    <textarea id="pasted-answer" maxLength={4000} value={answer} placeholder="Paste the answer from ChatGPT or any other AI" onChange={(e) => setAnswer(e.target.value)} />
    <div className="input-footer"><span className="counter">{answer.length.toLocaleString()} / 4,000</span>
      <button className="primary" disabled={!ready} onClick={() => ready && onRun(question.trim(), answer.trim())}><Icon name="shield" />Grade answer</button></div>
  </section>;
}

function LoadingSteps({ grading, startedAt, now, models }: { grading: boolean; startedAt: number; now: number; models: Health["models"] | undefined }) {
  // [name, estimated seconds]: estimates only, the server does not report progress
  const plan: [string, number][] = [["Finding evidence", 0.5], ...(grading ? [] : [["Writing answer", 6] as [string, number]]),
    [`Checking with ${modelName(models?.judge_1, "Gemma")}`, 12], ["Double-checking with NLI", 2], ["Combining", 1]];
  const elapsed = Math.max(0, (now - startedAt) / 1000);
  let end = 0;
  const found = plan.findIndex(([, s]) => (end += s) > elapsed);
  const cur = found === -1 ? plan.length - 1 : found; // past the estimate: stay on the last step
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0"), ss = String(Math.floor(elapsed % 60)).padStart(2, "0");
  return <section className="loading-card"><div className="loader-orbit"><span /></div>
    <span className="eyebrow">Estimated progress · {mm}:{ss} elapsed</span>
    <h2>{grading ? "Checking the pasted answer" : "Building an answer you can verify"}</h2>
    <p>Evidence stays readable while both judges work independently.</p>
    <ol>{plan.map(([name], i) => <li key={name} className={i < cur ? "done" : i === cur ? "current" : ""}><span>{i < cur ? "✓" : i + 1}</span><b>{name}</b><small>{i < cur ? "Estimated complete" : i === cur ? "In progress" : "Waiting"}</small></li>)}</ol>
    <p className="estimate-note">Steps are estimates until confirmed by the server.</p></section>;
}

// ---------------------------------------------------------------------------------------------
// Result
// ---------------------------------------------------------------------------------------------
function TrustBar({ trust }: { trust: TrustScore }) {
  const counts = [trust.supported, trust.unsupported, trust.contradicted, trust.needs_review];
  return <section className="trust"><div className="trust-value"><strong>{trust.percent_supported}%</strong><span>supported</span></div>
    <div className="trust-detail"><div className="trust-label"><b>Answer trust</b><span>{trust.total} claims checked</span></div>
      <div className="trust-segments">{counts.map((n, i) => <i key={i} className={ORDER[i]} style={{ flex: n || 0.12 }} />)}</div>
      <div className="trust-counts">{ORDER.map((v, i) => <span key={v}><LabelBadge verdict={v} compact /><b>{counts[i]}</b></span>)}</div></div></section>;
}

function AnswerView({ result, rows, selected, onSelect, plain = false }: { result: PipelineResult; rows: Row[]; selected: string | null; onSelect: (id: string) => void; plain?: boolean }) {
  const text = result.answer_text;
  const parts: ReactNode[] = [];
  let pos = 0;
  if (!plain) {
    rows.forEach(({ claim, v }, i) => {
      if (claim.start > pos) parts.push(<span key={`t${i}`}>{text.slice(pos, claim.start)}</span>);
      const verdict = toVerdict(v.label);
      parts.push(<button key={claim.id} className={`claim ${verdict} ${selected === claim.id ? "selected" : ""}`} onClick={() => onSelect(claim.id)}
        aria-label={`Claim ${i + 1}, ${verdicts[verdict].label}: ${claim.text}`}><small>{i + 1}</small>{claim.text}<b aria-hidden="true">{verdicts[verdict].icon}</b></button>);
      pos = claim.end;
    });
    if (pos < text.length) parts.push(<span key="tail">{text.slice(pos)}</span>);
  }
  return <section className="answer-block"><div className="section-title"><div><span className="eyebrow">Answer</span><h2>{result.answer_source === "pasted" ? "The pasted answer" : result.passages.some((p) => /\.pdf$/i.test(p.doc)) ? "What your document says" : "What the rules say"}</h2></div><span className="keyboard-tip">Keys 1–9 select claims</span></div>
    <div className={`answer-copy ${plain ? "plain" : ""}`} aria-label="AI answer">{plain ? text : parts}</div></section>;
}

function Legend() {
  return <section className="legend"><h3>How to read this answer</h3><div>{ORDER.map((v) => <span key={v}><LabelBadge verdict={v} compact /><small>{verdicts[v].meaning}</small></span>)}</div></section>;
}

function JudgeCard({ number, title, subtitle, verdict }: { number: 1 | 2; title: string; subtitle: string; verdict: JudgeVerdict | null }) {
  const conf = verdict?.confidence;
  return <article className="judge-card"><div className="judge-head"><div><b>Judge {number} · {title}</b><small>{subtitle}</small></div>
    {verdict ? <LabelBadge verdict={toVerdict(verdict.label)} compact /> : <span className="no-verdict">No verdict</span>}</div>
    <p>{verdict ? verdict.explanation || "No explanation given." : "This judge did not return a usable response."}</p>
    {number === 2 && conf != null && <div className="confidence"><span><b>{verdict?.label === "unsupported" ? "Strongest signal" : "Confidence"}</b><code>{Math.round(conf * 100)}%</code></span><i><b style={{ width: `${conf * 100}%` }} /></i></div>}</article>;
}

function EvidenceList({ passages, evidenceIds }: { passages: Passage[]; evidenceIds: string[] }) {
  const ids = new Set(evidenceIds);
  const withEvidence = passages.filter((p) => p.sentences.some((s) => ids.has(s.id)));
  const others = passages.filter((p) => !withEvidence.includes(p));
  return <section className="evidence"><div className="section-title"><div><span className="eyebrow">Source documents</span><h3>Exact evidence</h3></div><span className="passage-count">{passages.length} passages</span></div>
    {withEvidence.length === 0 && <div className="no-evidence"><Icon name="search" /><div><b>No matching source sentence</b><span>The retrieved documents do not mention this claim.</span></div></div>}
    {withEvidence.map((p) => <article key={p.id} className="passage open"><div className="passage-head"><span><Icon name="file" /><b>{p.doc} · {p.id}</b></span><Icon name="chevron" /></div>
      <p>{p.sentences.map((s) => ids.has(s.id) ? <span key={s.id} className="source-sentence"><code>{s.id}</code>{s.text} </span> : <span key={s.id}>{s.text} </span>)}</p></article>)}
    {others.map((p) => <details key={p.id} className="passage"><summary><span><Icon name="file" /><b>{p.doc} · {p.id}</b></span><small>{p.sentences.length} sentences</small></summary><p>{p.text}</p></details>)}
  </section>;
}

function ProofPanel({ row, passages, models }: { row: Row | undefined; passages: Passage[]; models: Health["models"] | undefined }) {
  return <aside className="proof-panel"><div className="proof-title"><div><span className="eyebrow">Verification details</span><h2>Proof panel</h2></div><span className="panel-live"><i />Linked to answer</span></div>
    {!row ? <div className="proof-empty"><span><Icon name="search" /></span><h3>Select a claim to see its proof</h3><p>Choose any highlighted sentence in the answer. Its exact evidence and both independent verdicts will appear here.</p><kbd>1</kbd><span> through </span><kbd>9</kbd><small> also select claims</small></div> : (() => {
      const { claim, v } = row; const verdict = toVerdict(v.label);
      const agree = v.single_judge ? "single" : v.label === "needs_review" ? "review" : "agree";
      return <><section className="selected-claim"><span className="eyebrow">Selected claim · <code>{claim.id}</code></span><blockquote>“{claim.text}”</blockquote><LabelBadge verdict={verdict} /></section>
        <div className={`agreement ${agree}`}><span>{agree === "single" ? "1/2" : agree === "review" ? "!" : "✓"}</span><div><b>{agree === "single" ? "Only one judge answered" : agree === "review" ? "Judges disagree, needs human review" : "Both judges agree"}</b><small>{v.explanation}</small></div></div>
        <div className="judges"><JudgeCard number={1} title={modelName(models?.judge_1, "Gemma")} subtitle="Gemini API" verdict={v.gemma} /><JudgeCard number={2} title="NLI" subtitle="DeBERTa-v3-small · local" verdict={v.nli} /></div>
        <EvidenceList passages={passages} evidenceIds={v.evidence_ids} /></>;
    })()}
  </aside>;
}

function FixedAnswer({ text, onCite }: { text: string; onCite: (id: string) => void }) {
  const pieces = text.split(/(\[p\d+\.s\d+\])/);
  return <section className="fixed-answer"><div className="fixed-icon"><Icon name="spark" /></div><div><span className="eyebrow">Cleaned answer</span><h3>Supported claims only</h3>
    <p>{text ? pieces.map((p, i) => { const m = /^\[(p\d+\.s\d+)\]$/.exec(p); return m ? <button key={i} className="citation" onClick={() => onCite(m[1])}>{m[1]}</button> : <span key={i}>{p}</span>; }) : "No supported claims to keep."}</p></div></section>;
}

function BeforeAfter({ result, rows }: { result: PipelineResult; rows: Row[] }) {
  return <section className="before-after"><article><span className="eyebrow">Before</span><h3>Plain AI answer</h3><AnswerView result={result} rows={rows} selected={null} onSelect={() => {}} plain /></article>
    <article><span className="eyebrow">After</span><h3>With WITNESS</h3><AnswerView result={result} rows={rows} selected={null} onSelect={() => {}} /></article></section>;
}

function ResultBlock({ result, rows, selected, setSelected, fixed, setFixed, compare, setCompare }: {
  result: PipelineResult; rows: Row[]; selected: string | null; setSelected: (id: string | null) => void;
  fixed: boolean; setFixed: (v: boolean) => void; compare: boolean; setCompare: (v: boolean) => void;
}) {
  const t = result.timings;
  const secs = (n: number | undefined) => (n === undefined ? "-" : `${n.toFixed(1)}s`);
  const cite = (id: string) => { const hit = rows.find((r) => r.v.evidence_ids.includes(id)); if (hit) setSelected(hit.claim.id); };
  return <>
    <TrustBar trust={result.trust} />
    <AnswerView result={result} rows={rows} selected={selected} onSelect={setSelected} />
    <Legend />
    <div className="result-actions">
      <button className={`secondary ${fixed ? "active" : ""}`} onClick={() => setFixed(!fixed)}><Icon name="spark" />Fix it <kbd>F</kbd></button>
      <button className={`secondary ${compare ? "active" : ""}`} onClick={() => setCompare(!compare)}>Before / After <kbd>B</kbd></button>
    </div>
    {fixed && <FixedAnswer text={result.fixed_answer} onCite={cite} />}
    {compare && <BeforeAfter result={result} rows={rows} />}
    <footer className="timings"><code>retrieve {secs(t.retrieve)}</code><code>generate {secs(t.generate)}</code><code>gemma {secs(t.judge_gemma)}</code><code>nli {secs(t.judge_nli)}</code><code>total {secs(t.total)}</code></footer>
  </>;
}

// ---------------------------------------------------------------------------------------------
// Other states
// ---------------------------------------------------------------------------------------------
function EmptyState({ question, onDemo }: { question?: string; onDemo: () => void }) {
  return <section className="empty-state"><span className="empty-icon"><Icon name="shield" /></span><span className="eyebrow">Evidence-first answers</span><h1>Know which claims you can trust.</h1>
    <p>WITNESS checks every sentence of an AI answer against your source documents (the event handbook, or a PDF you upload), then shows the exact proof behind each verdict.</p>
    <div className="steps"><div><b>1</b><span><strong>Ask</strong><small>Pose a rules question</small></span></div><Icon name="arrow" /><div><b>2</b><span><strong>Check</strong><small>Two judges verify</small></span></div><Icon name="arrow" /><div><b>3</b><span><strong>Proof</strong><small>Inspect exact evidence</small></span></div></div>
    {question && <button className="primary large" onClick={onDemo}>Try a demo question<Icon name="arrow" /></button>}</section>;
}

function ErrorState({ offline, detail, onReplay, onRetry, onGrade }: { offline: boolean; detail: string; onReplay: () => void; onRetry: () => void; onGrade: () => void }) {
  return <section className="error-state"><span className="error-symbol">{offline ? "↯" : "!"}</span><span className="eyebrow">{offline ? "Connection unavailable" : "Answer not generated"}</span>
    <h1>{offline ? "The backend can’t be reached." : "We couldn’t generate an answer."}</h1>
    <p>{offline ? "Your workspace is intact. Continue with a saved replay, or retry when the service is available." : "There are no claims to grade, and no partial result is shown. You can try again, or grade an answer you paste yourself."}</p>
    <div><button className="primary" onClick={offline ? onReplay : onRetry}>{offline ? "Switch to replay" : "Try again"}</button><button className="secondary" onClick={offline ? onRetry : onGrade}>{offline ? "Retry connection" : "Grade a pasted answer"}</button></div>
    <small>Technical detail · {detail}</small></section>;
}

function ReplayPicker({ entries, loaded, onPick }: { entries: ReplayEntry[]; loaded: boolean; onPick: (key: string) => void }) {
  return <section className="replay-picker"><span className="eyebrow">Saved output</span><h2>Choose a recorded check</h2>
    <p>Replays are saved results. They do not contact any model.</p>
    {!loaded ? <p>Loading saved checks…</p> : entries.length === 0 ? <p>No saved checks were found.</p> :
      <div>{entries.map((e) => <button key={e.key} onClick={() => onPick(e.key)}><span className="replay-play"><Icon name="play" /></span>
        <span><b>{e.question}</b><small>{e.answer_source === "pasted" ? "Graded pasted answer" : "Generated answer"} · saved {e.saved_at.slice(0, 10)}</small></span><code>{e.key.slice(-6)}</code><Icon name="arrow" /></button>)}</div>}</section>;
}

function EvalView({ data }: { data: EvalResult }) {
  const names = { gemma: "Gemma only", nli: "NLI only", combined: "WITNESS (both judges)" } as const;
  const rows = (["gemma", "nli", "combined"] as const).flatMap((j) => data.rows.filter((r) => r.judge === j && r.label === "overall"));
  return <section className="eval-view">{data.is_example && <div className="example-ribbon">EXAMPLE DATA, not real results</div>}
    <span className="eyebrow">Evaluation snapshot · {data.n_claims} claims</span><h1>How accurate are the judges?</h1><p>{data.note}</p>
    <div className="eval-bars">{rows.map((r) => <article key={r.judge}><div><b>{names[r.judge]}</b><span><strong>{Math.round(r.accuracy * 100)}%</strong><code>{r.correct}/{r.n}</code></span></div><i><b className={r.judge === "combined" ? "combined" : ""} style={{ width: `${r.accuracy * 100}%` }} /></i></article>)}</div>
    <div className="eval-note"><Icon name="shield" /><div><b>Our own numbers only</b><span>Measured on our own labelled claims about this event, never copied from other papers.</span></div></div></section>;
}

// ---------------------------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------------------------
export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);
  const [questions, setQuestions] = useState<DemoQuestion[]>([]);
  const [backups, setBackups] = useState<BackupAnswer[]>([]);
  const [evalData, setEvalData] = useState<EvalResult | null>(null);
  const [replayIndex, setReplayIndex] = useState<ReplayEntry[]>([]);
  const [replayLoaded, setReplayLoaded] = useState(false);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [mode, setModeState] = useState<"live" | "replay">(store("witness.mode") === "replay" ? "replay" : "live");
  const [projector, setProjectorState] = useState(store("witness.projector") === "1");
  const [tab, setTab] = useState<Tab>("ask");
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [grading, setGrading] = useState(false);
  const [startedAt, setStartedAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [selected, setSelected] = useState<string | null>(null);
  const [fixed, setFixed] = useState(false);
  const [compare, setCompare] = useState(false);

  const setMode = (m: "live" | "replay") => { setModeState(m); store("witness.mode", m); };
  const setProjector = (v: boolean) => { setProjectorState(v); store("witness.projector", v ? "1" : "0"); };

  // data that never changes during a session
  useEffect(() => {
    api.getDemoQuestions().then((r) => r.ok && setQuestions(r.data));
    api.getBackupAnswers().then((r) => r.ok && setBackups(r.data));
    api.getEval().then((r) => r.ok && setEvalData(r.data)); // a 404 simply hides the Evaluation tab
    api.getDocuments().then((r) => r.ok && setDocuments(r.data)); // uploads survive a page reload (they live in the server)
  }, []);

  // service health, refreshed every 15 s
  useEffect(() => {
    const load = () => api.getHealth().then((r) => { setDown(!r.ok); if (r.ok) setHealth(r.data); });
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  // saved checks when Replay is on
  const loadReplayIndex = useCallback(() => {
    api.getReplayIndex().then((r) => { if (r.ok) setReplayIndex(r.data); setReplayLoaded(true); });
  }, []);
  useEffect(() => { if (mode === "replay") loadReplayIndex(); }, [mode, loadReplayIndex]);

  // elapsed-time ticker for the loading card
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [running]);

  const rows = useMemo(() => rowsOf(result), [result]);
  const selectedRow = rows.find((r) => r.claim.id === selected);

  const show = (res: PipelineResult) => {
    setResult(res); setRequestError(null); setFixed(false); setCompare(false);
    setSelected(firstToInspect(rowsOf(res))); setTab("results");
  };

  const run = async (question: string, answer?: string) => {
    setRunning(true); setGrading(!!answer); setStartedAt(Date.now()); setNow(Date.now()); setRequestError(null);
    const r = await api.check(question, answer, selectedDoc);
    setRunning(false);
    if (r.ok) {
      show(r.data);
      if (selectedDoc && r.data.errors.some((e) => e.includes("no longer loaded"))) {  // the server forgot the PDF (restart)
        setSelectedDoc(null);
        api.getDocuments().then((d) => d.ok && setDocuments(d.data));
      }
    } else { setResult(null); setRequestError(r.error); setTab(answer ? "grade" : "ask"); }
  };

  // switching the source starts fresh, so an old result is never read as belonging to the new document
  const chooseSource = (id: string | null) => { setSelectedDoc(id); setResult(null); setRequestError(null); setUploadError(null); };

  const upload = async (file: File) => {
    setUploading(true); setUploadError(null);
    const r = await api.uploadDocument(file);
    setUploading(false);
    if (r.ok) { setDocuments((d) => [r.data, ...d.filter((x) => x.id !== r.data.id)]); chooseSource(r.data.id); }
    else setUploadError(r.error);
  };

  const removeDocument = async (id: string) => {
    await api.deleteDocument(id);
    setDocuments((d) => d.filter((x) => x.id !== id));
    chooseSource(null);
  };

  const pickReplay = async (key: string) => {
    const r = await api.getReplay(key);
    if (r.ok) show(r.data); else setRequestError(r.error);
  };

  const goReplay = () => { setRequestError(null); setMode("replay"); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement).tagName)) return;
      if (/^[1-9]$/.test(e.key) && rows[+e.key - 1]) setSelected(rows[+e.key - 1].claim.id);
      const k = e.key.toLowerCase();
      if (k === "f") setFixed((v) => !v);
      if (k === "b") setCompare((v) => !v);
      if (k === "p") setProjectorState((v) => { store("witness.projector", v ? "0" : "1"); return !v; });
      if (k === "r") setModeState((v) => { const n = v === "live" ? "replay" : "live"; store("witness.mode", n); return n; });
      if (e.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows]);

  const replay = mode === "replay";
  const failed = !!result && result.claims.length === 0;
  const hasResult = !!result && !failed && !requestError;
  const showProof = tab === "results" && hasResult;
  const banners = result && !requestError ? result.errors : [];

  const status = () => {
    if (running) return <LoadingSteps grading={grading} startedAt={startedAt} now={now} models={health?.models} />;
    if (requestError) return <ErrorState offline detail={requestError} onReplay={goReplay} onRetry={() => setRequestError(null)} onGrade={() => setTab("grade")} />;
    return null;
  };

  const source = <SourcePicker documents={documents} selected={selectedDoc} uploading={uploading} error={uploadError}
    onSelect={chooseSource} onUpload={upload} onRemove={removeDocument} />;
  const ownDocument = selectedDoc !== null;

  const content = () => {
    if (tab === "eval" && evalData) return <EvalView data={evalData} />;
    if ((tab === "ask" || tab === "grade") && replay) return <ReplayPicker entries={replayIndex} loaded={replayLoaded} onPick={pickReplay} />;
    if (tab === "ask") return <><AskPanel questions={questions} running={running} onRun={run} source={source} ownDocument={ownDocument} />{status() ?? <EmptyState question={ownDocument ? undefined : questions[0]?.question} onDemo={() => run(questions[0].question)} />}</>;
    if (tab === "grade") return <><GradePanel backups={backups} running={running} onRun={run} source={source} />{status()}</>;
    // results tab
    const s = status();
    if (s) return s;
    if (!result) return <EmptyState question={questions[0]?.question} onDemo={() => { setTab("ask"); run(questions[0].question); }} />;
    if (failed) return <ErrorState offline={false} detail={result.errors.join(" ") || "No claims were produced."} onReplay={goReplay} onRetry={() => setTab("ask")} onGrade={() => setTab("grade")} />;
    return <ResultBlock result={result} rows={rows} selected={selected} setSelected={setSelected} fixed={fixed} setFixed={setFixed} compare={compare} setCompare={setCompare} />;
  };

  return <div className={`app ${projector ? "projector" : ""}`}>
    <TopBar health={health} down={down} mode={mode} projector={projector} setMode={setMode} setProjector={setProjector} />
    <Banners replay={replay || result?.mode === "replay"} errors={banners} />
    <main className={`layout ${showProof ? "with-proof" : ""}`}>
      <div className="left-workspace"><WorkspaceTabs active={tab} setActive={setTab} showEval={!!evalData} />{content()}</div>
      {showProof && result && <ProofPanel row={selectedRow} passages={result.passages} models={health?.models} />}
    </main>
  </div>;
}
