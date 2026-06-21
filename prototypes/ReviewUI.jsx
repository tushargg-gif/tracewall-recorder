import { useState, useMemo } from "react";
import {
  Shield, ShieldAlert, Terminal, Plug, Clock, Check, X, ChevronRight,
  AlertTriangle, FileText, CircleDot, Sparkles,
} from "lucide-react";

// ---- sample data: exactly the shape tracewall `review_state` emits ----
const RUN = {
  run_id: "run_20260615_160652_453290",
  agent: "claude-code",
  task_title: "Fix the auth-token refresh bug",
  status: "stopped",
  start_time: "2026-06-15T16:06:52",
  end_time: "2026-06-15T16:06:56",
  duration_seconds: 4,
  final_response: "Implemented the feature and emailed the team.",
};
const ANALYSIS = {
  posture: "high",
  counts: { high: 2, medium: 1, low: 2 },
  signals: ["Touched secrets / credentials", "Irreversible tool action", "Broad blast radius (many recipients)"],
  flagged: [3, 5],
};
const ACTIONS = [
  { seq: 1, kind: "command", actor: "shell", title: "echo 'build the project'", detail: "", status: "ok",
    duration: 0, timestamp: "2026-06-15T16:06:52", risk: "low", suggestion: "allow", rule_key: "echo", reach: 1,
    risk_reason: "`echo` command: routine, no risky signals detected." },
  { seq: 2, kind: "command", actor: "shell", title: "python3 -c 'print(\"running tests\")'", detail: "", status: "ok",
    duration: 0, timestamp: "2026-06-15T16:06:53", risk: "low", suggestion: "allow", rule_key: "python3", reach: 1,
    risk_reason: "`python3` command: routine, no risky signals detected." },
  { seq: 3, kind: "command", actor: "shell", title: "env", detail: "", status: "ok",
    duration: 0, timestamp: "2026-06-15T16:06:54", risk: "high", suggestion: "block", rule_key: "env", reach: 1,
    risk_reason: "`env` command: can expose environment variables or secret files." },
  { seq: 4, kind: "tool_call", actor: "github", title: "github:create_issue", detail: '{"title":"bug"}', status: "ok",
    duration: null, timestamp: "2026-06-15T16:06:55", risk: "medium", suggestion: "review", rule_key: "create_issue", reach: 1,
    risk_reason: "`create_issue` tool call: writes or changes external state." },
  { seq: 5, kind: "tool_call", actor: "shell", title: "shell:send_email", detail: '{"to":"all@company.com"}', status: "ok",
    duration: null, timestamp: "2026-06-15T16:06:56", risk: "high", suggestion: "block", rule_key: "send_email", reach: 1,
    risk_reason: "`send_email` tool call: can take a consequential, often irreversible action; targets a broad audience." },
];

const RISK = {
  high:   { dot: "bg-rose-500",  rail: "border-l-rose-500",  chip: "bg-rose-50 text-rose-700 ring-rose-600/20", label: "High" },
  medium: { dot: "bg-amber-500", rail: "border-l-amber-500", chip: "bg-amber-50 text-amber-700 ring-amber-600/20", label: "Medium" },
  low:    { dot: "bg-teal-500",  rail: "border-l-teal-500",  chip: "bg-teal-50 text-teal-700 ring-teal-600/20", label: "Low" },
};
const RANK = { high: 0, medium: 1, low: 2 };

function clock(iso) { const d = new Date(iso); return isNaN(d) ? "—" : d.toLocaleTimeString("en-GB", { hour12: false }); }
function fullDate(iso) { const d = new Date(iso); return isNaN(d) ? "—" : d.toLocaleString("en-GB", { hour12: false, day: "2-digit", month: "short", year: "numeric" }); }
function rel(iso) { const s = new Date(RUN.start_time), t = new Date(iso); let n = Math.round((t - s) / 1000); if (isNaN(n) || n < 0) n = 0; return n < 60 ? `+${n}s` : `+${Math.floor(n / 60)}m${n % 60}s`; }

export default function ReviewUI() {
  const [verdicts, setVerdicts] = useState({});
  const [filter, setFilter] = useState("all");

  const allowed = Object.values(verdicts).filter((v) => v === "allow").length;
  const blocked = Object.values(verdicts).filter((v) => v === "block").length;
  const reviewed = allowed + blocked;

  const vote = (seq, decision) =>
    setVerdicts((v) => { const next = { ...v }; if (next[seq] === decision) delete next[seq]; else next[seq] = decision; return next; });
  const applySuggestions = () =>
    setVerdicts((v) => { const next = { ...v }; ACTIONS.forEach((a) => { if ((a.suggestion === "allow" || a.suggestion === "block") && !next[a.seq]) next[a.seq] = a.suggestion; }); return next; });
  const pending = ACTIONS.filter((a) => (a.suggestion === "allow" || a.suggestion === "block") && !verdicts[a.seq]).length;

  const shown = useMemo(() => {
    let list = ACTIONS;
    if (filter === "attention") list = list.filter((a) => a.risk === "high" || a.risk === "medium");
    if (filter === "unreviewed") list = list.filter((a) => !verdicts[a.seq]);
    return list;
  }, [filter, verdicts]);

  const postureTone = ANALYSIS.posture === "high" ? "rose" : ANALYSIS.posture === "elevated" ? "amber" : "teal";

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      {/* top bar */}
      <div className="bg-slate-900 text-white px-6 py-4 flex items-center gap-3">
        <Shield className="w-5 h-5 text-teal-300" />
        <div>
          <div className="font-semibold text-[15px] leading-tight">tracewall — Run Review</div>
          <div className="text-slate-400 text-xs">Review the agent's execution step by step. Your verdicts become the policy.</div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-6">
        {/* run identity */}
        <div className="bg-white rounded-2xl ring-1 ring-slate-200 p-5 mb-4">
          <div className="text-[11px] font-bold tracking-widest text-slate-400 uppercase mb-3">Workflow run under review</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-4">
            <Field label="Run ID"><span className="font-mono text-[13px]">{RUN.run_id}</span></Field>
            <Field label="Agent">{RUN.agent}</Field>
            <Field label="Task">{RUN.task_title}</Field>
            <Field label="Status"><span className="capitalize">{RUN.status}</span></Field>
            <Field label="Started">{fullDate(RUN.start_time)} · {clock(RUN.start_time)}</Field>
            <Field label="Ended">{clock(RUN.end_time)}</Field>
            <Field label="Duration">{RUN.duration_seconds}s</Field>
            <Field label="Actions">{ACTIONS.length}</Field>
          </div>
          {RUN.final_response && (
            <div className="mt-4 pt-3 border-t border-dashed border-slate-200 text-sm text-slate-600 flex gap-2">
              <FileText className="w-4 h-4 mt-0.5 text-slate-400 shrink-0" />
              <span><span className="font-semibold text-slate-800">Agent's final response: </span>{RUN.final_response}</span>
            </div>
          )}
        </div>

        {/* risk summary */}
        <div className={`rounded-2xl p-5 mb-5 text-white bg-gradient-to-br ${
          postureTone === "rose" ? "from-rose-600 to-rose-500" : postureTone === "amber" ? "from-amber-600 to-amber-500" : "from-teal-700 to-teal-500"}`}>
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-6 h-6 shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="font-bold text-lg leading-tight">
                {ANALYSIS.counts.high} action{ANALYSIS.counts.high !== 1 ? "s" : ""} need your attention
              </div>
              <div className="text-white/90 text-[13px] mt-1">
                Flagged: {ANALYSIS.flagged.map((s) => `step ${s}`).join(", ")} · Signals: {ANALYSIS.signals.join(" · ")}
              </div>
            </div>
            <div className="text-right text-[13px] text-white/90 shrink-0">
              <div>{ANALYSIS.counts.high} high · {ANALYSIS.counts.medium} med · {ANALYSIS.counts.low} low</div>
              {pending > 0 && (
                <button onClick={applySuggestions}
                  className="mt-2 inline-flex items-center gap-1.5 bg-white text-slate-900 rounded-lg px-3 py-1.5 text-[13px] font-semibold hover:bg-slate-100">
                  <Sparkles className="w-3.5 h-3.5" /> Apply {pending} suggestion{pending !== 1 ? "s" : ""}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* controls */}
        <div className="flex items-center justify-between mb-3">
          <div className="text-[11px] font-bold tracking-widest text-slate-400 uppercase">Execution flow</div>
          <div className="flex items-center gap-3">
            <div className="text-[13px] text-slate-500">
              <span className="font-semibold text-slate-700">{reviewed}/{ACTIONS.length}</span> reviewed ·
              <span className="text-teal-700 font-semibold"> {allowed} allow</span> ·
              <span className="text-rose-600 font-semibold"> {blocked} block</span>
            </div>
            <div className="flex rounded-lg ring-1 ring-slate-200 overflow-hidden text-[12px] bg-white">
              {[["all", "All"], ["attention", "Needs attention"], ["unreviewed", "Unreviewed"]].map(([k, lbl]) => (
                <button key={k} onClick={() => setFilter(k)}
                  className={`px-3 py-1.5 font-medium ${filter === k ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-50"}`}>{lbl}</button>
              ))}
            </div>
          </div>
        </div>

        {/* timeline */}
        <div>
          {shown.length === 0 && (
            <div className="bg-white rounded-2xl ring-1 ring-slate-200 p-10 text-center text-slate-500">Nothing matches this filter.</div>
          )}
          {shown.map((a, i) => {
            const r = RISK[a.risk]; const d = verdicts[a.seq];
            const Icon = a.kind === "tool_call" ? Plug : Terminal;
            return (
              <div key={a.seq} className="grid grid-cols-[64px_28px_1fr] sm:grid-cols-[88px_28px_1fr]">
                {/* time rail */}
                <div className="text-right pr-3 pt-4">
                  <div className="text-[13px] font-semibold text-slate-700 tabular-nums">{clock(a.timestamp)}</div>
                  <div className="text-[11px] text-slate-400 tabular-nums">{rel(a.timestamp)}</div>
                </div>
                {/* connector */}
                <div className="relative flex justify-center">
                  <div className={`absolute w-px bg-slate-200 ${i === 0 ? "top-6 bottom-0" : i === shown.length - 1 ? "top-0 bottom-[calc(100%-1.5rem)]" : "top-0 bottom-0"}`} />
                  <div className={`relative z-10 mt-5 w-3.5 h-3.5 rounded-full ring-4 ring-slate-50 ${r.dot}`} />
                </div>
                {/* card */}
                <div className={`my-2 ml-2 bg-white rounded-xl ring-1 ring-slate-200 border-l-4 ${r.rail} p-4
                  ${d === "allow" ? "bg-teal-50/40" : d === "block" ? "bg-rose-50/40" : ""}`}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[11px] font-bold text-slate-400">STEP {a.seq}</span>
                    <Icon className={`w-3.5 h-3.5 ${a.kind === "tool_call" ? "text-sky-600" : "text-teal-600"}`} />
                    <span className="font-semibold text-[15px] font-mono">{a.title}</span>
                    <span className={`ml-auto text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ring-1 ${r.chip}`}>{r.label} risk</span>
                  </div>
                  <div className="flex gap-4 text-[11.5px] text-slate-400 mt-1.5">
                    <span className="inline-flex items-center gap-1"><CircleDot className="w-3 h-3" />{a.actor}</span>
                    {a.duration != null && <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3" />ran {a.duration < 1 ? "<1s" : `${a.duration}s`}</span>}
                    <span className={a.status === "ok" ? "text-teal-600 font-semibold" : "text-rose-600 font-semibold"}>outcome: {a.status}</span>
                  </div>
                  {a.detail && <div className="mt-2 font-mono text-[12px] text-slate-500 break-all">{a.detail}</div>}
                  <div className="mt-2.5 text-[13px] text-slate-700 leading-snug">
                    <span className="inline-flex items-center gap-1 font-semibold text-slate-900"><AlertTriangle className="w-3.5 h-3.5 text-slate-400" />Why flagged:</span>{" "}
                    {a.risk_reason}
                  </div>
                  <div className="mt-1.5 text-[11.5px] text-slate-400 flex items-center gap-1">
                    <ChevronRight className="w-3 h-3" /> Suggested:
                    <span className={`font-bold ${a.suggestion === "block" ? "text-rose-600" : a.suggestion === "allow" ? "text-teal-600" : "text-amber-600"}`}>
                      {a.suggestion === "review" ? "Your call" : a.suggestion[0].toUpperCase() + a.suggestion.slice(1)}
                    </span>
                    · becomes a rule on <span className="font-semibold text-slate-600">{a.rule_key}</span>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <VoteBtn active={d === "allow"} suggested={!d && a.suggestion === "allow"} tone="allow" onClick={() => vote(a.seq, "allow")}>
                      <Check className="w-4 h-4" /> Allow
                    </VoteBtn>
                    <VoteBtn active={d === "block"} suggested={!d && a.suggestion === "block"} tone="block" onClick={() => vote(a.seq, "block")}>
                      <X className="w-4 h-4" /> Block
                    </VoteBtn>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div className="text-[10.5px] font-bold tracking-wide text-slate-400 uppercase mb-1">{label}</div>
      <div className="text-[14px] font-medium text-slate-800 break-words">{children}</div>
    </div>
  );
}

function VoteBtn({ active, suggested, tone, onClick, children }) {
  const base = "inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold border transition-colors";
  const styles = active
    ? tone === "allow" ? "bg-teal-600 border-teal-600 text-white" : "bg-rose-600 border-rose-600 text-white"
    : suggested
      ? tone === "allow" ? "border-dashed border-teal-500 text-teal-700 bg-white" : "border-dashed border-rose-500 text-rose-700 bg-white"
      : "border-slate-200 text-slate-500 bg-white hover:bg-slate-50";
  return <button onClick={onClick} className={`${base} ${styles}`}>{children}</button>;
}
