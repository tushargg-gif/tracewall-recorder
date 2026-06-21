import * as vscode from "vscode";
import { execFile } from "child_process";

// --- run the tracewall CLI in the workspace -------------------------------

function workspaceCwd(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

function cli(args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    const cwd = workspaceCwd();
    if (!cwd) {
      reject(new Error("Open a folder in VS Code first."));
      return;
    }
    const bin =
      vscode.workspace.getConfiguration("tracewall").get<string>("cliPath") ||
      "tracewall";
    execFile(bin, args, { cwd, maxBuffer: 16 * 1024 * 1024 }, (err, stdout, stderr) => {
      if (err) {
        reject(new Error(stderr?.trim() || err.message));
        return;
      }
      resolve(stdout);
    });
  });
}

// --- review panel ----------------------------------------------------------

let reviewPanel: vscode.WebviewPanel | undefined;

async function openReview(context: vscode.ExtensionContext) {
  if (!reviewPanel) {
    reviewPanel = vscode.window.createWebviewPanel(
      "tracewallReview",
      "tracewall — Review",
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true }
    );
    reviewPanel.onDidDispose(() => (reviewPanel = undefined));
    reviewPanel.webview.onDidReceiveMessage(async (msg) => {
      try {
        if (msg.type === "verdict") {
          await cli(["verdict", "--seq", String(msg.seq), "--decision", msg.decision]);
        } else if (msg.type === "recommend") {
          await cli(["recommend", "--accept"]);
          vscode.window.showInformationMessage("tracewall: policy updated from your reviews.");
        }
        await refreshReview();
      } catch (e: any) {
        vscode.window.showErrorMessage("tracewall: " + e.message);
      }
    });
  }
  reviewPanel.reveal(vscode.ViewColumn.Beside);
  await refreshReview();
}

async function refreshReview() {
  if (!reviewPanel) return;
  try {
    const state = JSON.parse(await cli(["review", "--json"]));
    reviewPanel.webview.html = reviewHtml(state);
  } catch (e: any) {
    reviewPanel.webview.html = messageHtml(
      "Nothing to review yet",
      e.message +
        "\n\nRun `tracewall init` and `tracewall install-hook` in this folder, then use Claude Code so actions are captured."
    );
  }
}

// --- policy panel ----------------------------------------------------------

async function openPolicies() {
  const panel = vscode.window.createWebviewPanel(
    "tracewallPolicy",
    "tracewall — Active Policy",
    vscode.ViewColumn.Beside,
    { enableScripts: true }
  );
  try {
    const data = JSON.parse(await cli(["policy", "--json"]));
    panel.webview.html = policyHtml(data);
  } catch (e: any) {
    panel.webview.html = messageHtml("No policy yet", e.message);
  }
}

// --- commands --------------------------------------------------------------

async function installHook() {
  try {
    const out = await cli(["install-hook"]);
    vscode.window.showInformationMessage("tracewall: " + out.split("\n")[0]);
  } catch (e: any) {
    vscode.window.showErrorMessage("tracewall: " + e.message);
  }
}

export function activate(context: vscode.ExtensionContext) {
  context.subscriptions.push(
    vscode.commands.registerCommand("tracewall.openReview", () => openReview(context)),
    vscode.commands.registerCommand("tracewall.openPolicies", () => openPolicies()),
    vscode.commands.registerCommand("tracewall.installHook", () => installHook()),
    vscode.commands.registerCommand("tracewall.recommendAccept", async () => {
      try {
        await cli(["recommend", "--accept"]);
        vscode.window.showInformationMessage("tracewall: policy updated from your reviews.");
        await refreshReview();
      } catch (e: any) {
        vscode.window.showErrorMessage("tracewall: " + e.message);
      }
    })
  );

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  status.text = "$(shield) tracewall";
  status.tooltip = "Review your agent's actions";
  status.command = "tracewall.openReview";
  status.show();
  context.subscriptions.push(status);
}

export function deactivate() {}

// --- HTML rendering --------------------------------------------------------

function nonce(): string {
  let t = "";
  const c = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 24; i++) t += c.charAt(Math.floor(Math.random() * c.length));
  return t;
}

function shell(body: string, script: string): string {
  const n = nonce();
  return `<!doctype html><html><head><meta charset="utf-8"/>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${n}';"/>
<style>
  body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);padding:14px;font-size:13px}
  .hd{font-weight:700;font-size:15px;margin-bottom:2px}
  .sub{opacity:.7;font-size:12px;margin-bottom:14px}
  .bar{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
  button{font-family:inherit;font-size:12px;border:1px solid var(--vscode-button-border,transparent);
    background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground);
    border-radius:5px;padding:5px 10px;cursor:pointer}
  button.primary{background:var(--vscode-button-background);color:var(--vscode-button-foreground)}
  .row{border:1px solid var(--vscode-panel-border);border-left:4px solid var(--vscode-panel-border);
    border-radius:7px;padding:10px 12px;margin-bottom:8px}
  .row.high{border-left-color:#e11d48}.row.medium{border-left-color:#d97706}.row.low{border-left-color:#0d9488}
  .top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .agent{font-size:10px;font-weight:700;background:var(--vscode-badge-background);color:var(--vscode-badge-foreground);padding:1px 7px;border-radius:9px}
  .ttl{font-family:var(--vscode-editor-font-family);font-weight:600}
  .chip{font-size:10px;text-transform:uppercase;letter-spacing:.4px;padding:1px 7px;border-radius:9px;margin-left:auto}
  .chip.high{background:#4a0d1d;color:#fda4af}.chip.medium{background:#4a300d;color:#fcd34d}.chip.low{background:#0d3a36;color:#5eead4}
  .why{opacity:.8;font-size:12px;margin-top:6px}
  .covered{margin-top:7px;font-size:12px;opacity:.85}
  .covered.block{color:#fda4af}.covered.allow{color:#5eead4}
  .va{margin-top:8px;display:flex;gap:7px}
  .va button.on-allow{background:#0d9488;color:#fff}.va button.on-block{background:#e11d48;color:#fff}
  table{width:100%;border-collapse:collapse}
  th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--vscode-panel-border);font-size:12px}
  th{opacity:.6;text-transform:uppercase;font-size:10px;letter-spacing:.4px}
  .mono{font-family:var(--vscode-editor-font-family)}
  .pill{font-size:10px;text-transform:uppercase;padding:1px 7px;border-radius:9px}
  .pill.block{background:#4a0d1d;color:#fda4af}.pill.allow{background:#0d3a36;color:#5eead4}
  .empty{opacity:.7;text-align:center;padding:30px;white-space:pre-wrap}
</style></head><body>${body}<script nonce="${n}">${script}</script></body></html>`;
}

function messageHtml(title: string, detail: string): string {
  return shell(
    `<div class="hd">${esc(title)}</div><div class="empty">${esc(detail)}</div>`,
    ""
  );
}

function reviewHtml(state: any): string {
  const body = `
    <div class="hd">Run review</div>
    <div class="sub" id="sub"></div>
    <div class="bar">
      <button class="primary" onclick="send({type:'recommend'})">Learn policy from my reviews</button>
      <button onclick="send({type:'refresh'})">Refresh</button>
    </div>
    <div id="list"></div>`;
  const script = `
    const vscode = acquireVsCodeApi();
    const STATE = ${json(state)};
    function send(m){ vscode.postMessage(m); }
    function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
    function vote(seq,d){ const cur=(STATE.verdicts[seq]||{}).decision; send({type:'verdict',seq,decision: cur===d?'clear':d}); }
    const r = STATE.run||{};
    document.getElementById('sub').textContent =
      (r.run_id||'') + '  ·  agent: ' + (r.agent||'—') + '  ·  ' + STATE.action_count + ' actions  ·  posture: ' + ((STATE.analysis||{}).posture||'low');
    const list = document.getElementById('list');
    if(!STATE.actions.length){ list.innerHTML='<div class="empty">No actions recorded in this run yet.</div>'; }
    for(const a of (STATE.actions||[])){
      const d=(STATE.verdicts[a.seq]||{}).decision;
      const covered = a.policy && a.policy.decision!=='none';
      const el=document.createElement('div'); el.className='row '+a.risk;
      let inner = '<div class="top"><span class="agent">'+esc(a.actor)+'</span>'+
        '<span class="ttl">'+esc(a.title)+'</span><span class="chip '+a.risk+'">'+a.risk+'</span></div>';
      if(covered){
        inner += '<div class="covered '+a.policy.decision+'">Already '+(a.policy.decision==='block'?'blocked':'allowed')+
          ' by policy · '+esc(a.policy.rule_id||'')+'</div>';
      } else {
        inner += '<div class="why">'+esc(a.risk_reason||'')+'</div>'+
          '<div class="va"><button class="'+(d==='allow'?'on-allow':'')+'" onclick="vote('+a.seq+',\\'allow\\')">Allow</button>'+
          '<button class="'+(d==='block'?'on-block':'')+'" onclick="vote('+a.seq+',\\'block\\')">Block</button></div>';
      }
      el.innerHTML=inner; list.appendChild(el);
    }
    window.addEventListener('message',e=>{ if(e.data&&e.data.type==='refresh'){} });`;
  return shell(body, script);
}

function policyHtml(data: any): string {
  const body = `<div class="hd">Active policy</div>
    <div class="sub" id="sub"></div>
    <table><thead><tr><th>Decision</th><th>Type</th><th>Target</th><th>Reason</th></tr></thead>
    <tbody id="rows"></tbody></table>`;
  const script = `
    const DATA = ${json(data)};
    function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
    function label(m){ if(!m) return '?'; if(m.kind==='tool_call') return m.tool||'tool';
      if(m.touches_secret) return 'secret files (.env, *.pem, …)'; return m.binary||m.arg_glob||'command'; }
    const s=DATA.summary||{};
    document.getElementById('sub').textContent = (s.rules||0)+' rules · '+(s.blocks||0)+' block · '+(s.allows||0)+' allow';
    const rows=document.getElementById('rows');
    for(const r of (DATA.rules||[])){
      const tr=document.createElement('tr');
      tr.innerHTML='<td><span class="pill '+r.decision+'">'+esc(r.decision)+'</span></td>'+
        '<td>'+(r.match&&r.match.kind==='tool_call'?'tool call':'command')+'</td>'+
        '<td class="mono">'+esc(label(r.match))+'</td>'+
        '<td>'+esc(r.reason||'')+'</td>';
      rows.appendChild(tr);
    }`;
  return shell(body, script);
}

function esc(s: string): string {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" } as any)[c]
  );
}

function json(obj: any): string {
  // safe to embed inside a <script> block
  return JSON.stringify(obj).replace(/</g, "\\u003c");
}
