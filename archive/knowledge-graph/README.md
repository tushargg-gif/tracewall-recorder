# Repository Knowledge Graph

A machine- and human-readable map of the AgentProof Recorder codebase: modules,
classes, functions, and the `imports` / `inherits` / `calls` relationships between
them. Generated directly from the Python sources with the standard-library `ast`
module — no third-party dependencies, no network access.

## Regenerate

```bash
python3 tools/knowledge_graph.py          # writes this directory
python3 tools/knowledge_graph.py --print  # also prints a fan-in summary
```

Re-run after changing code under `src/` or `tests/`; the outputs are
deterministic, so a clean diff means the structure is unchanged.

## Artifacts

| File | What it is |
| --- | --- |
| `graph.json` | Full graph: every node (package/module/class/function) and edge (`contains`/`imports`/`inherits`/`calls`), plus summary metrics and per-module import fan-in/out. The canonical source other tools can consume. |
| `index.html` | Self-contained interactive viewer (vis-network via CDN). Open in a browser; toggle between modules / +classes / +functions, and optionally overlay call edges. Nodes are colored by architectural layer. |
| `module_graph.mmd` | Mermaid module import graph, grouped by layer. Renders on GitHub and in most Markdown viewers. |
| `architecture.mmd` | Mermaid layer-level diagram: import edges aggregated between architectural layers, with weights. The 10,000-ft view. |

## Layers

Modules are grouped into layers for color/grouping (see `LAYERS` in
`tools/knowledge_graph.py`):

- **interface** — `cli`, `__main__`, `sidecar`
- **policy** — `contracts`, `policy`, `checks`, `mcp_policy`, `mcp_targets`, `sensitive`
- **capture** — `recorder`, `events`, `store`, `gitutils`, `mcp_stdio`, `paths`
- **verification** — `verifier`, `scoring`, `plugins`
- **enforcement** — `enforcement` (real-time, block-before-harm)
- **reporting** — `reports`
- **orchestration** — `orchestration`

## How the edges are resolved

- `imports` — only repo-internal `agentproof.*` imports are kept; external deps
  (fastapi, httpx, …) are intentionally excluded to keep the graph about *this*
  codebase.
- `inherits` — base classes are linked when the base name resolves to a class
  defined in the repo.
- `calls` — best-effort. A call is linked when the called bare name matches a
  function/method defined in the repo. Names defined in more than three places
  are skipped to avoid noise. Treat `calls` as a strong hint, not ground truth.

## The "block before harm" work (now wired in)

The Reddit feedback asked for *prevention* (block a risky action before it touches
sensitive files) rather than only *post-hoc detection*. That gate now exists and
the graph shows it:

- `agentproof.sensitive` is the single source of truth for sensitive patterns,
  consumed by **both** `verifier` (which flags, `action_taken="flagged"`) and
  `enforcement` (which blocks, `action_taken="blocked"`).
- The **enforcement** layer (`enforcement`) runs commands inside an OS sandbox.
  `recorder` (capture) spawns the agent's process tree through it when a run is
  started with `--enforce` — see the `capture --> enforcement --> policy` edges in
  `architecture.mmd`.
- Decisions are appended to the tamper-evident event chain as `enforcement_decision`,
  so prevention is itself auditable.
