"""Review UX — the execution-flow review with allow/block verdicts.

Renders a recorded run as a readable execution timeline: which workflow, run by
which agent, when, in what order, how long each step took, what each step risks —
and lets a human allow/block each step. Verdicts persist to the run directory and
become the training signal the policy recommender reads.

No third-party dependencies: the local server is Python's stdlib ``http.server``.
HTTP handling is factored into the pure ``handle_api`` for socket-free testing.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
import json

from agentproof import enforce
from agentproof.events import now_iso
from agentproof.flow import action_flow
from agentproof.insight import analyze_action, analyze_run
from agentproof.recorder import paths_for_run, read_json, write_json
from agentproof.sensitive import looks_secret_token

VALID_DECISIONS = {"allow", "block", "clear"}


# --- verdict store ---------------------------------------------------------

def verdicts_file(run_id: str, cwd: Path | None = None) -> Path:
    return paths_for_run(run_id, cwd).run_dir / "verdicts.json"


def load_verdicts(run_id: str, cwd: Path | None = None) -> dict[str, Any]:
    path = verdicts_file(run_id, cwd)
    if not path.exists():
        return {"run_id": run_id, "verdicts": {}}
    data = read_json(path)
    data.setdefault("run_id", run_id)
    data.setdefault("verdicts", {})
    return data


def save_verdicts(run_id: str, data: dict[str, Any], cwd: Path | None = None) -> Path:
    path = verdicts_file(run_id, cwd)
    write_json(path, data)
    return path


def set_verdict(run_id: str, seq: int, decision: str, note: str = "", cwd: Path | None = None) -> dict[str, Any]:
    if decision not in VALID_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(VALID_DECISIONS)}")
    data = load_verdicts(run_id, cwd)
    key = str(int(seq))
    if decision == "clear":
        data["verdicts"].pop(key, None)
    else:
        data["verdicts"][key] = {"decision": decision, "note": note, "updated_at": now_iso()}
    save_verdicts(run_id, data, cwd)
    return data


# --- review state ----------------------------------------------------------

def _rule_key(action: dict[str, Any]) -> str:
    title = str(action.get("title") or "")
    if action.get("kind") == "tool_call":
        return title.split(":", 1)[1] if ":" in title else title
    # mirror the recommender: a secret-reading command becomes a target rule
    text = str(action.get("detail") or title)
    if any(looks_secret_token(tok) for tok in text.split()):
        return "secret files (.env, *.pem, …)"
    return (title.split() or [""])[0]


def _run_meta(run_id: str, cwd: Path | None) -> dict[str, Any]:
    """Identity of the workflow being reviewed: who / what / when."""
    run_file = paths_for_run(run_id, cwd).run_file
    if not run_file.exists():
        return {"run_id": run_id}
    run = read_json(run_file)
    return {
        "run_id": run_id,
        "agent": run.get("agent"),
        "task_id": run.get("task_id"),
        "task_title": run.get("task_title"),
        "status": run.get("status"),
        "start_time": run.get("start_time"),
        "end_time": run.get("end_time"),
        "duration_seconds": run.get("duration_seconds"),
        "final_response": run.get("final_response"),
        "project_root": run.get("project_root"),
    }


def review_state(run_id: str, cwd: Path | None = None) -> dict[str, Any]:
    """Run identity + ordered execution flow + risk analysis + verdicts."""
    flow = action_flow(run_id, cwd)
    actions = flow["actions"]
    verdicts = load_verdicts(run_id, cwd)["verdicts"]
    active_policy = enforce.load_active_policy(paths_for_run(run_id, cwd).agentproof_dir)

    reach: dict[tuple[str, str], int] = {}
    for action in actions:
        reach[(action["kind"], _rule_key(action))] = reach.get((action["kind"], _rule_key(action)), 0) + 1

    covered_blocks = covered_allows = 0
    for action in actions:
        analysis = analyze_action(action)
        action["risk"] = analysis["risk"]
        action["risk_reason"] = analysis["reason"]
        action["risk_tags"] = analysis["tags"]
        action["suggestion"] = analysis["suggestion"]
        action["rule_key"] = _rule_key(action)
        action["reach"] = reach[(action["kind"], _rule_key(action))]
        # how the *current* active policy already treats this action
        coverage = enforce.evaluate_action(_action_for_policy(action), active_policy)
        action["policy"] = coverage
        if coverage["decision"] == "block":
            covered_blocks += 1
        elif coverage["decision"] == "allow":
            covered_allows += 1

    allowed = sum(1 for v in verdicts.values() if v.get("decision") == "allow")
    blocked = sum(1 for v in verdicts.values() if v.get("decision") == "block")
    return {
        "run_id": run_id,
        "run": _run_meta(run_id, cwd),
        "actions": actions,
        "action_count": flow["action_count"],
        "verdicts": verdicts,
        "reviewed": allowed + blocked,
        "allowed": allowed,
        "blocked": blocked,
        "analysis": analyze_run(actions),
        "policy": {
            "rules": active_policy.get("rules", []),
            "rule_count": len(active_policy.get("rules", [])),
            "covers_blocks": covered_blocks,
            "covers_allows": covered_allows,
            "uncovered": flow["action_count"] - covered_blocks - covered_allows,
        },
    }


def _action_for_policy(action: dict[str, Any]) -> dict[str, Any]:
    """Normalize a flow action into what the policy engine evaluates."""
    if action.get("kind") == "tool_call":
        return enforce.action_from_tool(str(action.get("actor") or ""), _rule_key(action))
    return enforce.action_from_command(str(action.get("detail") or action.get("title") or ""))


# --- pure request handler (testable without a socket) ----------------------

def handle_api(method: str, path: str, body: bytes, run_id: str, cwd: Path | None = None) -> tuple[int, str, bytes]:
    if method == "GET" and path in ("/", "/index.html"):
        html = render_review_html(review_state(run_id, cwd), live=True)
        return 200, "text/html; charset=utf-8", html.encode("utf-8")
    if method == "GET" and path == "/api/state":
        return _json(200, review_state(run_id, cwd))
    if method == "POST" and path == "/api/verdict":
        try:
            payload = json.loads(body or b"{}")
            seq = int(payload["seq"])
            decision = str(payload["decision"])
        except (ValueError, KeyError, TypeError) as exc:
            return _json(400, {"error": f"bad request: {exc}"})
        try:
            set_verdict(run_id, seq, decision, str(payload.get("note") or ""), cwd)
        except ValueError as exc:
            return _json(400, {"error": str(exc)})
        return _json(200, review_state(run_id, cwd))
    return _json(404, {"error": "not found"})


def _json(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, "application/json", json.dumps(obj).encode("utf-8")


# --- HTML ------------------------------------------------------------------

def render_review_html(state: dict[str, Any], live: bool = False) -> str:
    data_json = json.dumps(state)
    return _PAGE.replace("__LIVE__", "true" if live else "false").replace("__DATA__", data_json)


_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AgentProof — Run Review</title>
<style>
  :root{ --navy:#0B1437; --ink:#101828; --muted:#5B677A; --faint:#8A97A8; --line:#E5E9F0;
         --bg:#F5F7FA; --card:#FFFFFF; --teal:#0D9488; --high:#E11D48; --med:#D97706; --low:#0D9488; }
  *{box-sizing:border-box} html,body{margin:0}
  body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink);font-size:14px}
  .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  header{background:var(--navy);color:#fff;padding:20px 30px}
  header h1{margin:0;font-size:18px;font-weight:700;letter-spacing:.2px}
  header .sub{color:#9FB0C9;font-size:12.5px;margin-top:3px}
  .wrap{max-width:1060px;margin:22px auto;padding:0 24px}

  /* run identity panel */
  .panel{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-bottom:16px;
    box-shadow:0 1px 2px rgba(16,24,40,.04)}
  .panel h2{margin:0 0 14px;font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:var(--faint)}
  .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px 22px}
  .field .lbl{font-size:11px;font-weight:700;letter-spacing:.4px;text-transform:uppercase;color:var(--faint);margin-bottom:3px}
  .field .val{font-size:14px;font-weight:600;color:var(--ink);word-break:break-word}
  .resp{margin-top:14px;padding-top:12px;border-top:1px dashed var(--line);font-size:13px;color:var(--muted)}
  .resp b{color:var(--ink)}

  /* attention strip */
  .attention{border-radius:12px;padding:13px 16px;margin-bottom:18px;font-size:13.5px;font-weight:600;display:flex;gap:12px;align-items:center}
  .attention.high{background:#FFF1F3;border:1px solid #FECDD3;color:#9F1239}
  .attention.elevated{background:#FFF7ED;border:1px solid #FED7AA;color:#9A3412}
  .attention.low{background:#ECFDF5;border:1px solid #A7F3D0;color:#065F46}
  .attention .grow{flex:1}
  .applybtn{background:var(--navy);color:#fff;border:none;border-radius:8px;padding:8px 13px;font-weight:700;font-size:12.5px;cursor:pointer}
  .applybtn:hover{filter:brightness(1.12)}

  .sectionlabel{font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:var(--faint);margin:6px 2px 12px}
  .counts{float:right;font-weight:600;color:var(--muted);text-transform:none;letter-spacing:0}
  .counts .b{color:var(--high)} .counts .a{color:var(--low)}

  /* execution timeline */
  .step{display:grid;grid-template-columns:84px 30px 1fr;gap:0;align-items:stretch}
  .tcol{text-align:right;padding:14px 12px 0 0}
  .tabs{font-size:13px;font-weight:700;color:var(--ink)} .trel{font-size:11px;color:var(--faint);margin-top:2px}
  .rail{position:relative;display:flex;justify-content:center}
  .rail:before{content:"";position:absolute;top:0;bottom:0;width:2px;background:var(--line)}
  .step:first-child .rail:before{top:24px}
  .step:last-child .rail:before{bottom:calc(100% - 24px)}
  .dot{position:relative;margin-top:18px;width:14px;height:14px;border-radius:50%;background:var(--faint);
    border:3px solid var(--bg);z-index:1}
  .dot.r-high{background:var(--high)} .dot.r-medium{background:var(--med)} .dot.r-low{background:var(--low)}
  .card{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--faint);border-radius:12px;
    padding:13px 16px;margin:8px 0 8px 12px;box-shadow:0 1px 2px rgba(16,24,40,.04)}
  .card.r-high{border-left-color:var(--high)} .card.r-medium{border-left-color:var(--med)} .card.r-low{border-left-color:var(--low)}
  .card.on-allow{background:#F3FdFb} .card.on-block{background:#FFF5F6}
  .chead{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
  .stepno{font-size:11px;font-weight:800;color:var(--faint)}
  .agent{font-size:11px;font-weight:800;color:#fff;background:var(--navy);padding:2px 9px;border-radius:999px}
  .kind{font-size:10px;font-weight:800;letter-spacing:.6px;text-transform:uppercase;color:var(--teal)}
  .kind.tool_call{color:#0284C7}
  .ctitle{font-weight:700;font-size:15px}
  .chip{font-size:9.5px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;padding:2px 8px;border-radius:999px}
  .chip.high{background:#FFE4E6;color:#9F1239} .chip.medium{background:#FEF3C7;color:#92400E} .chip.low{background:#D1FAE5;color:#065F46}
  .cmeta{font-size:11.5px;color:var(--faint);margin-top:5px;display:flex;gap:14px;flex-wrap:wrap}
  .cmeta .ok{color:#0F766E;font-weight:700} .cmeta .bad{color:var(--high);font-weight:700}
  .cdetail{font-size:12px;color:#475569;margin-top:7px;word-break:break-all}
  .why{font-size:12.5px;margin-top:8px;color:#334155;line-height:1.4}
  .why .lab{font-weight:800;color:var(--ink)}
  .conseq{font-size:11.5px;color:var(--faint);margin-top:6px}
  .sug{font-weight:800}.sug.block{color:var(--high)}.sug.allow{color:var(--low)}.sug.review{color:var(--med)}
  .covered{margin-top:9px;font-size:13px;padding:9px 12px;border-radius:9px;display:flex;align-items:center;gap:4px}
  .covered.block{color:#9F1239;background:#FFF1F3;border:1px solid #FECDD3}
  .covered.allow{color:#0F766E;background:#ECFDF5;border:1px solid #A7F3D0}
  .covered .cright{margin-left:auto;font-size:11px;opacity:.7}
  .btns{margin-top:11px;display:flex;gap:9px}
  button.v{border:1.5px solid var(--line);background:#fff;border-radius:8px;padding:7px 16px;font-weight:700;font-size:13px;cursor:pointer;color:var(--muted)}
  button.v.suggest{border-style:dashed}
  button.v.allow.suggest{border-color:var(--low);color:#0F766E} button.v.block.suggest{border-color:var(--high);color:#9F1239}
  button.v.on.allow{background:var(--low);color:#fff;border-color:var(--low)}
  button.v.on.block{background:var(--high);color:#fff;border-color:var(--high)}
  .empty{color:var(--muted);text-align:center;padding:46px;background:#fff;border-radius:13px;border:1px solid var(--line)}
  .foot{color:var(--faint);font-size:12px;text-align:center;margin:20px 0}
</style></head>
<body>
<header><h1>AgentProof — Run Review</h1>
  <div class="sub">Review the agent's execution, step by step. Confirm or overrule each action — your verdicts become the policy.</div>
</header>
<div class="wrap">
  <div class="panel" id="panel"></div>
  <div class="attention" id="attention"></div>
  <div class="sectionlabel">Execution flow <span class="counts" id="counts"></span></div>
  <div id="list"></div>
  <div class="foot" id="foot"></div>
</div>
<script>
const LIVE = __LIVE__;
let STATE = __DATA__;
const RANK = {high:0, medium:1, low:2};
function dF(seq){ const v=STATE.verdicts[String(seq)]; return v?v.decision:null; }
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function pending(){ return STATE.actions.filter(a=>(a.suggestion==='allow'||a.suggestion==='block')&&!dF(a.seq)); }
function fmtClock(iso){ const d=new Date(iso); return isNaN(d)?'—':d.toLocaleTimeString('en-GB',{hour12:false}); }
function fmtFull(iso){ const d=new Date(iso); return isNaN(d)?'—':d.toLocaleString('en-GB',{hour12:false,year:'numeric',month:'short',day:'2-digit'}); }
function rel(iso){ const s=STATE.run&&STATE.run.start_time; if(!iso||!s) return ''; let n=Math.round((new Date(iso)-new Date(s))/1000);
  if(isNaN(n)) return ''; if(n<0)n=0; if(n<60)return '+'+n+'s'; return '+'+Math.floor(n/60)+'m'+(n%60)+'s'; }
function dur(secs){ return (secs==null)?'':(secs<1?'<1s':secs+'s'); }

function renderPanel(){
  const r=STATE.run||{}, an=STATE.analysis||{counts:{high:0,medium:0,low:0},posture:'low'};
  const pchip = `<span class="chip ${an.posture==='high'?'high':an.posture==='elevated'?'medium':'low'}">${an.posture==='elevated'?'elevated':an.posture} risk</span>`;
  const f=(lbl,val,mono)=>`<div class="field"><div class="lbl">${lbl}</div><div class="val ${mono?'mono':''}">${val}</div></div>`;
  let html=`<h2>Workflow run under review</h2><div class="grid">`
    + f('Run ID', esc(r.run_id||STATE.run_id), true)
    + f('Agent', esc(r.agent||'—'))
    + f('Task', esc(r.task_title||r.task_id||'—'))
    + f('Status', esc(r.status||'—'))
    + f('Started', r.start_time?esc(fmtFull(r.start_time)):'—')
    + f('Ended', r.end_time?esc(fmtFull(r.end_time)):'—')
    + f('Duration', (r.duration_seconds!=null)?esc(r.duration_seconds+'s'):'—')
    + f('Actions', STATE.action_count+' &nbsp; '+pchip)
    + `</div>`;
  if(r.final_response) html+=`<div class="resp"><b>Agent's final response:</b> ${esc(r.final_response)}</div>`;
  document.getElementById('panel').innerHTML=html;
}
function renderAttention(){
  const an=STATE.analysis||{posture:'low',signals:[],flagged:[],counts:{}};
  const el=document.getElementById('attention'); el.className='attention '+an.posture;
  const flaggedSteps = (an.flagged||[]);
  const names = STATE.actions.filter(a=>flaggedSteps.includes(a.seq)).map(a=>'step '+a.seq+' ('+esc(a.rule_key)+')');
  let msg = an.posture==='high' ? `<b>Heads up —</b> ${flaggedSteps.length} high-risk action(s): ${names.join(', ')}.`
          : an.posture==='elevated' ? `A few actions are worth a closer look.`
          : `Nothing high-risk detected in this run.`;
  if((an.signals||[]).length) msg += ` &nbsp;Signals: ${an.signals.map(esc).join(' · ')}.`;
  const p=pending().length;
  el.innerHTML = `<div class="grow">${msg}</div>` +
    ((p&&LIVE)?`<button class="applybtn" onclick="applySuggestions()">Apply ${p} suggestion${p>1?'s':''}</button>`:'');
}
function render(){
  if(!STATE.actions.length){ document.getElementById('panel').innerHTML=''; renderPanel();
    document.getElementById('attention').style.display='none';
    document.getElementById('list').innerHTML='<div class="empty">No commands or tool calls were recorded in this run.</div>';
    document.getElementById('counts').textContent=''; return; }
  renderPanel(); renderAttention();
  document.getElementById('counts').innerHTML = `${STATE.reviewed}/${STATE.action_count} reviewed &nbsp; · &nbsp; <span class="a">${STATE.allowed} allow</span> &nbsp; <span class="b">${STATE.blocked} block</span> &nbsp; · &nbsp; ${LIVE?'saving live':'static (read-only)'}`;
  const list=document.getElementById('list'); list.innerHTML='';
  for(const a of STATE.actions){           // execution order, as it happened
    const d=dF(a.seq), sug=a.suggestion;
    const sugLabel = sug==='review'?'Your call':(sug.charAt(0).toUpperCase()+sug.slice(1));
    const reach = a.reach>1?` · also covers ${a.reach} step(s) here`:'';
    const statusCls = a.status==='ok'?'ok':(a.status==='blocked'||a.status==='failed')?'bad':'';
    const step=document.createElement('div'); step.className='step';
    step.innerHTML=`
      <div class="tcol"><div class="tabs">${esc(fmtClock(a.timestamp))}</div><div class="trel">${esc(rel(a.timestamp))}</div></div>
      <div class="rail"><div class="dot r-${a.risk}"></div></div>
      <div class="card r-${a.risk} ${d?('on-'+d):''}">
        <div class="chead">
          <span class="stepno">STEP ${a.seq}</span>
          <span class="agent">${esc(a.source||a.actor)}</span>
          ${a.actor && a.actor!==(a.source||a.actor) ? `<span class="kind">${esc(a.actor)}</span>` : ''}
          <span class="kind ${a.kind}">${a.kind.replace('_',' ')}</span>
          <span class="ctitle">${esc(a.title)}</span>
          <span class="chip ${a.risk}">${a.risk} risk</span>
        </div>
        <div class="cmeta">
          ${a.duration!=null?`<span>ran ${esc(dur(a.duration))}</span>`:''}
          <span class="${statusCls}">outcome: ${esc(a.status)}</span>
        </div>
        ${a.detail?`<div class="cdetail mono">${esc(a.detail)}</div>`:''}
        ${(a.policy&&a.policy.decision!=='none')?`
        <div class="covered ${a.policy.decision}">
          Already <b>${a.policy.decision==='block'?'blocked':'allowed'}</b> by active policy
          <span class="mono"> · ${esc(a.policy.rule_id||'')}</span>
          <span class="cright">no decision needed</span>
        </div>`:`
        <div class="why"><span class="lab">Why flagged:</span> ${esc(a.risk_reason)}</div>
        <div class="conseq">Suggested: <span class="sug ${sug}">${sugLabel}</span> · your decision becomes a rule on <b>${esc(a.rule_key)}</b>${reach}</div>
        <div class="btns">
          <button class="v allow ${d==='allow'?'on':''} ${(!d&&sug==='allow')?'suggest':''}" onclick="vote(${a.seq},'allow')">Allow</button>
          <button class="v block ${d==='block'?'on':''} ${(!d&&sug==='block')?'suggest':''}" onclick="vote(${a.seq},'block')">Block</button>
        </div>`}
      </div>`;
    list.appendChild(step);
  }
}
async function vote(seq, decision){
  const cur=dF(seq), next=cur===decision?'clear':decision;
  if(!LIVE){ if(next==='clear') delete STATE.verdicts[String(seq)];
    else STATE.verdicts[String(seq)]={decision:next,note:'',updated_at:'(static)'};
    recount(); render(); offerDownload(); return; }
  const res=await fetch('/api/verdict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seq,decision:next})});
  STATE=await res.json(); render();
}
async function applySuggestions(){ for(const a of pending().slice()){ await vote(a.seq,a.suggestion); } }
function recount(){ const vs=Object.values(STATE.verdicts);
  STATE.allowed=vs.filter(v=>v.decision==='allow').length; STATE.blocked=vs.filter(v=>v.decision==='block').length;
  STATE.reviewed=STATE.allowed+STATE.blocked; }
function offerDownload(){ const f=document.getElementById('foot');
  const blob=new Blob([JSON.stringify({run_id:STATE.run_id,verdicts:STATE.verdicts},null,2)],{type:'application/json'});
  f.innerHTML='<a download="verdicts.json" href="'+URL.createObjectURL(blob)+'">Download verdicts.json</a>'; }
render();
</script>
</body></html>"""


# --- server ----------------------------------------------------------------

def serve_review(run_id: str, host: str = "127.0.0.1", port: int = 8898, cwd: Path | None = None) -> None:
    base = Path(cwd or Path.cwd())

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, method: str):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            status, ctype, payload = handle_api(method, self.path, body, run_id, base)
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self._respond("GET")

        def do_POST(self):
            self._respond("POST")

        def log_message(self, *args):
            pass

    server = HTTPServer((host, port), Handler)
    print(f"AgentProof review for {run_id} → http://{host}:{port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


def export_review_html(run_id: str, out_path: Path, cwd: Path | None = None) -> Path:
    html = render_review_html(review_state(run_id, cwd), live=False)
    out_path = Path(out_path)
    out_path.write_text(html, encoding="utf-8")
    return out_path


# --- policies page (project-level: every rule in one place) ----------------

def render_policy_html(policy: dict[str, Any]) -> str:
    rules = [{**r, "label": enforce.match_label(r.get("match") or {})} for r in policy.get("rules", [])]
    payload = {"rules": rules, "summary": enforce.policy_summary(policy)}
    return _POLICY_PAGE.replace("__DATA__", json.dumps(payload))


def export_policy_html(policy: dict[str, Any], out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.write_text(render_policy_html(policy), encoding="utf-8")
    return out_path


_POLICY_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AgentProof — Active Policy</title>
<style>
  :root{ --navy:#0B1437; --ink:#101828; --muted:#5B677A; --faint:#8A97A8; --line:#E5E9F0;
         --bg:#F5F7FA; --card:#FFFFFF; --teal:#0D9488; --high:#E11D48; }
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
    font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:14px}
  .mono{font-family:ui-monospace,Menlo,Consolas,monospace}
  header{background:var(--navy);color:#fff;padding:20px 30px}
  header h1{margin:0;font-size:18px;font-weight:700}
  header .sub{color:#9FB0C9;font-size:12.5px;margin-top:3px}
  .wrap{max-width:980px;margin:22px auto;padding:0 24px}
  .stats{display:flex;gap:10px;margin-bottom:18px;flex-wrap:wrap}
  .stat{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;min-width:96px}
  .stat .n{font-size:22px;font-weight:800} .stat .l{font-size:11px;color:var(--faint);text-transform:uppercase;letter-spacing:.4px;font-weight:700}
  .stat.block .n{color:var(--high)} .stat.allow .n{color:var(--teal)}
  .controls{display:flex;gap:8px;margin-bottom:12px}
  .controls input{flex:1;border:1px solid var(--line);border-radius:9px;padding:9px 12px;font-size:13px;background:#fff}
  .controls button{border:1px solid var(--line);background:#fff;border-radius:9px;padding:8px 12px;font-size:12px;font-weight:600;color:var(--muted);cursor:pointer}
  .controls button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
  table{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border:1px solid var(--line);border-radius:13px;overflow:hidden}
  th{text-align:left;font-size:10.5px;letter-spacing:.5px;text-transform:uppercase;color:var(--faint);font-weight:800;padding:11px 14px;background:#FAFBFC;border-bottom:1px solid var(--line)}
  td{padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}
  tr:last-child td{border-bottom:none}
  .pill{font-size:10px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;padding:3px 9px;border-radius:999px}
  .pill.block{background:#FFE4E6;color:#9F1239} .pill.allow{background:#CCFBF1;color:#0F766E}
  .kind{font-size:11px;color:var(--muted)} .reason{color:var(--muted);font-size:12.5px;margin-top:3px}
  .meta{color:var(--faint);font-size:11px;white-space:nowrap}
  .empty{background:#fff;border:1px solid var(--line);border-radius:13px;padding:46px;text-align:center;color:var(--muted)}
</style></head>
<body>
<header><h1>AgentProof — Active Policy</h1>
  <div class="sub">Every rule currently in force. These are enforced on every future run; commands and tool calls are checked against them.</div>
</header>
<div class="wrap">
  <div class="stats" id="stats"></div>
  <div class="controls">
    <input id="q" placeholder="Filter rules by target or reason…" oninput="render()"/>
    <button id="f-all" class="on" onclick="setF('all')">All</button>
    <button id="f-block" onclick="setF('block')">Blocks</button>
    <button id="f-allow" onclick="setF('allow')">Allows</button>
  </div>
  <div id="table"></div>
</div>
<script>
const DATA = __DATA__;
let FILTER = "all";
function setF(f){ FILTER=f; for(const b of document.querySelectorAll('.controls button')) b.classList.remove('on');
  document.getElementById('f-'+f).classList.add('on'); render(); }
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function render(){
  const s=DATA.summary;
  document.getElementById('stats').innerHTML =
    stat(s.rules,'Rules')+stat(s.blocks,'Blocking','block')+stat(s.allows,'Allowing','allow')+stat(s.commands,'Commands')+stat(s.tools,'Tool calls');
  const q=(document.getElementById('q').value||'').toLowerCase();
  let rows=(DATA.rules||[]).filter(r=>{
    if(FILTER!=='all' && r.decision!==FILTER) return false;
    const m=r.match||{}; const t=(m.tool||m.binary||'')+' '+(r.reason||'');
    return !q || t.toLowerCase().includes(q);
  });
  rows.sort((a,b)=> (a.decision!=='block')-(b.decision!=='block') || ((a.label||'')<(b.label||'')?-1:1));
  const el=document.getElementById('table');
  if(!rows.length){ el.innerHTML='<div class="empty">No rules match. Accept recommendations with <span class="mono">agentproof recommend --accept</span>.</div>'; return; }
  let h='<table><thead><tr><th>Decision</th><th>Type</th><th>Target</th><th>Reason</th><th>Origin</th><th>Added</th></tr></thead><tbody>';
  for(const r of rows){ const m=r.match||{};
    h+=`<tr>
      <td><span class="pill ${r.decision}">${esc(r.decision)}</span></td>
      <td class="kind">${esc(m.kind==='tool_call'?'tool call':'command')}</td>
      <td class="mono"><b>${esc(r.label||m.tool||m.binary||'?')}</b></td>
      <td>${esc(r.reason||'')}</td>
      <td class="meta">${esc(r.origin||'')}</td>
      <td class="meta">${esc((r.added_at||'').replace('T',' ').slice(0,16))}</td>
    </tr>`; }
  el.innerHTML=h+'</tbody></table>';
}
function stat(n,l,cls){ return `<div class="stat ${cls||''}"><div class="n">${n}</div><div class="l">${l}</div></div>`; }
render();
</script>
</body></html>"""
