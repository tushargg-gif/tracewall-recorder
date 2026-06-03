#!/usr/bin/env python3
"""Build a knowledge graph of the AgentProof Recorder repository.

Parses the Python sources with the standard-library ``ast`` module (no third-party
dependencies) and emits a graph of the repo's structure and relationships:

Node kinds
    package   one per top-level source root (``src``, ``tests``)
    module    one per ``.py`` file
    class     one per class definition
    function  one per top-level function or method

Edge kinds
    contains   package -> module, module -> class/function, class -> method
    imports    module -> module (internal ``agentproof.*`` imports only)
    inherits   class -> base class (when the base resolves inside the repo)
    calls      function -> function (best-effort, repo-internal symbols only)

Outputs (written under ``knowledge-graph/``)
    graph.json          full node/edge graph + summary metrics
    module_graph.mmd    Mermaid module-dependency diagram
    architecture.mmd    Mermaid high-level layer diagram
    index.html          self-contained interactive viewer (vis-network via CDN)

Usage
    python tools/knowledge_graph.py            # parse repo, write knowledge-graph/
    python tools/knowledge_graph.py --print    # also print a text summary
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = ["src", "tests"]
OUTPUT_DIR = REPO_ROOT / "knowledge-graph"

# High-level architectural layers, keyed by module short name (without package
# prefix). Used only for the architecture diagram and node grouping; modules not
# listed fall into "other".
LAYERS: dict[str, str] = {
    "cli": "interface",
    "__main__": "interface",
    "sidecar": "interface",
    "contracts": "policy",
    "policy": "policy",
    "mcp_policy": "policy",
    "mcp_targets": "policy",
    "checks": "policy",
    "sensitive": "policy",
    "enforcement": "enforcement",
    "recorder": "capture",
    "events": "capture",
    "store": "capture",
    "gitutils": "capture",
    "mcp_stdio": "capture",
    "paths": "capture",
    "verifier": "verification",
    "scoring": "verification",
    "plugins": "verification",
    "reports": "reporting",
    "orchestration": "orchestration",
}


@dataclass
class Node:
    id: str
    kind: str  # package | module | class | function
    label: str
    module: str | None = None
    layer: str | None = None
    lineno: int | None = None
    loc: int | None = None
    doc: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str
    kind: str  # contains | imports | inherits | calls


class ModuleParser(ast.NodeVisitor):
    """Extract symbols, imports, inheritance, and calls from a single module."""

    def __init__(self, module_id: str, known_modules: set[str]) -> None:
        self.module_id = module_id
        self.known_modules = known_modules
        self.classes: list[dict[str, Any]] = []
        self.functions: list[dict[str, Any]] = []
        self.imports: set[str] = set()
        # function fully-qualified id -> set of called bare names
        self.calls: dict[str, set[str]] = defaultdict(set)
        self._scope: list[str] = [module_id]

    # ---- imports -----------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._record_import(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._record_import(node.module)
        self.generic_visit(node)

    def _record_import(self, dotted: str) -> None:
        if not dotted.startswith("agentproof"):
            return
        # agentproof.verifier -> module id "src/agentproof/verifier.py" style key
        short = dotted.split(".", 1)[1] if "." in dotted else ""
        if short:
            candidate = f"agentproof.{short}"
            if candidate in self.known_modules:
                self.imports.add(candidate)

    # ---- definitions -------------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_id = f"{self.module_id}::{node.name}"
        bases = [self._name_of(base) for base in node.bases]
        self.classes.append(
            {
                "id": class_id,
                "name": node.name,
                "lineno": node.lineno,
                "loc": _loc(node),
                "doc": ast.get_docstring(node),
                "bases": [b for b in bases if b],
            }
        )
        self._scope.append(class_id)
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._record_function(child, parent=class_id, is_method=True)
            else:
                self.visit(child)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node)

    def _handle_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        parent = self._scope[-1]
        # Only treat as a method if directly under a class scope (handled there).
        if parent.count("::") >= 1 and parent != self.module_id:
            return
        self._record_function(node, parent=self.module_id, is_method=False)

    def _record_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent: str,
        is_method: bool,
    ) -> None:
        func_id = f"{parent}::{node.name}" if is_method else f"{self.module_id}::{node.name}"
        self.functions.append(
            {
                "id": func_id,
                "name": node.name,
                "parent": parent,
                "is_method": is_method,
                "lineno": node.lineno,
                "loc": _loc(node),
                "doc": ast.get_docstring(node),
                "async": isinstance(node, ast.AsyncFunctionDef),
            }
        )
        self._scope.append(func_id)
        for called in _collect_calls(node):
            self.calls[func_id].add(called)
        self._scope.pop()

    @staticmethod
    def _name_of(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None


def _loc(node: ast.AST) -> int | None:
    end = getattr(node, "end_lineno", None)
    start = getattr(node, "lineno", None)
    if end is None or start is None:
        return None
    return end - start + 1


def _collect_calls(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def discover_modules() -> dict[str, Path]:
    """Map module id -> file path. Module id mirrors importable dotted path."""
    modules: dict[str, Path] = {}
    for root in SOURCE_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.exists():
            continue
        for py in sorted(root_path.rglob("*.py")):
            rel = py.relative_to(root_path)
            if root == "src":
                dotted = ".".join(rel.with_suffix("").parts)
            else:
                dotted = "tests." + ".".join(rel.with_suffix("").parts)
            modules[dotted] = py
    return modules


def build_graph() -> dict[str, Any]:
    module_paths = discover_modules()
    known_internal = {m for m in module_paths if m.startswith("agentproof")}

    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    # name -> set of function ids that define it, for call resolution
    name_to_func: dict[str, set[str]] = defaultdict(set)
    name_to_class: dict[str, str] = {}
    parsers: dict[str, ModuleParser] = {}

    # package nodes
    for pkg in SOURCE_ROOTS:
        if (REPO_ROOT / pkg).exists():
            nodes[pkg] = Node(id=pkg, kind="package", label=pkg)

    for module_id, path in module_paths.items():
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        parser = ModuleParser(module_id, known_internal)
        parser.visit(tree)
        parsers[module_id] = parser

        short = module_id.split(".")[-1]
        layer = LAYERS.get(short, "tests" if module_id.startswith("tests") else "other")
        nodes[module_id] = Node(
            id=module_id,
            kind="module",
            label=module_id,
            module=module_id,
            layer=layer,
            loc=len(source.splitlines()),
            doc=ast.get_docstring(tree),
            meta={"path": str(path.relative_to(REPO_ROOT))},
        )
        pkg = "src" if module_id.startswith("agentproof") else "tests"
        if pkg in nodes:
            edges.append(Edge(pkg, module_id, "contains"))

        for cls in parser.classes:
            nodes[cls["id"]] = Node(
                id=cls["id"],
                kind="class",
                label=cls["name"],
                module=module_id,
                layer=layer,
                lineno=cls["lineno"],
                loc=cls["loc"],
                doc=cls["doc"],
                meta={"bases": cls["bases"]},
            )
            edges.append(Edge(module_id, cls["id"], "contains"))
            name_to_class[cls["name"]] = cls["id"]

        for func in parser.functions:
            nodes[func["id"]] = Node(
                id=func["id"],
                kind="function",
                label=func["name"],
                module=module_id,
                layer=layer,
                lineno=func["lineno"],
                loc=func["loc"],
                doc=func["doc"],
                meta={"is_method": func["is_method"], "async": func["async"]},
            )
            edges.append(Edge(func["parent"], func["id"], "contains"))
            name_to_func[func["name"]].add(func["id"])

    # import edges
    for module_id, parser in parsers.items():
        for target in parser.imports:
            if target in nodes and target != module_id:
                edges.append(Edge(module_id, target, "imports"))

    # inheritance edges
    for node in list(nodes.values()):
        if node.kind != "class":
            continue
        for base in node.meta.get("bases", []):
            target = name_to_class.get(base)
            if target and target != node.id:
                edges.append(Edge(node.id, target, "inherits"))

    # call edges (best-effort: resolve bare call names to repo-defined functions)
    seen_calls: set[tuple[str, str]] = set()
    for module_id, parser in parsers.items():
        for func_id, called_names in parser.calls.items():
            for name in called_names:
                targets = name_to_func.get(name, set())
                # avoid self-loops and over-linking common names with many defs
                if len(targets) > 3:
                    continue
                for target in targets:
                    if target == func_id:
                        continue
                    key = (func_id, target)
                    if key in seen_calls:
                        continue
                    seen_calls.add(key)
                    edges.append(Edge(func_id, target, "calls"))

    return _serialize(nodes, edges, module_paths)


def _serialize(
    nodes: dict[str, Node],
    edges: list[Edge],
    module_paths: dict[str, Path],
) -> dict[str, Any]:
    kind_counts: dict[str, int] = defaultdict(int)
    for node in nodes.values():
        kind_counts[node.kind] += 1
    edge_counts: dict[str, int] = defaultdict(int)
    for edge in edges:
        edge_counts[edge.kind] += 1

    # fan-in / fan-out on module import edges
    import_in: dict[str, int] = defaultdict(int)
    import_out: dict[str, int] = defaultdict(int)
    for edge in edges:
        if edge.kind == "imports":
            import_out[edge.source] += 1
            import_in[edge.target] += 1
    for node in nodes.values():
        if node.kind == "module":
            node.meta["imports_in"] = import_in.get(node.id, 0)
            node.meta["imports_out"] = import_out.get(node.id, 0)

    return {
        "metadata": {
            "repo": "AgentProof-Recorder",
            "generator": "tools/knowledge_graph.py",
            "module_count": len(module_paths),
            "node_counts": dict(kind_counts),
            "edge_counts": dict(edge_counts),
        },
        "nodes": [vars(n) for n in nodes.values()],
        "edges": [vars(e) for e in edges],
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def render_module_mermaid(graph: dict[str, Any]) -> str:
    lines = ["%% Module import graph - AgentProof Recorder", "graph LR"]
    layer_of = {
        n["id"]: (n.get("layer") or "other")
        for n in graph["nodes"]
        if n["kind"] == "module"
    }
    modules = [n for n in graph["nodes"] if n["kind"] == "module" and n["id"].startswith("agentproof")]
    by_layer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mod in modules:
        by_layer[mod.get("layer") or "other"].append(mod)
    for layer, mods in sorted(by_layer.items()):
        lines.append(f"  subgraph {layer}")
        for mod in sorted(mods, key=lambda m: m["id"]):
            short = mod["id"].split(".")[-1]
            lines.append(f"    {_mid(mod['id'])}[{short}]")
        lines.append("  end")
    for edge in graph["edges"]:
        if edge["kind"] == "imports":
            if edge["source"].startswith("agentproof") and edge["target"].startswith("agentproof"):
                lines.append(f"  {_mid(edge['source'])} --> {_mid(edge['target'])}")
    return "\n".join(lines) + "\n"


def render_architecture_mermaid(graph: dict[str, Any]) -> str:
    """Layer-level diagram: aggregate import edges between layers."""
    layer_of = {
        n["id"]: (n.get("layer") or "other")
        for n in graph["nodes"]
        if n["kind"] == "module"
    }
    pair_weight: dict[tuple[str, str], int] = defaultdict(int)
    for edge in graph["edges"]:
        if edge["kind"] != "imports":
            continue
        src = layer_of.get(edge["source"])
        dst = layer_of.get(edge["target"])
        if src and dst and src != dst:
            pair_weight[(src, dst)] += 1
    lines = ["%% Architectural layer dependencies", "graph TD"]
    layers = sorted({l for pair in pair_weight for l in pair})
    for layer in layers:
        lines.append(f"  {layer}([{layer}])")
    for (src, dst), weight in sorted(pair_weight.items()):
        lines.append(f"  {src} -->|{weight}| {dst}")
    return "\n".join(lines) + "\n"


def _mid(module_id: str) -> str:
    return module_id.replace(".", "_")


def render_html(graph: dict[str, Any]) -> str:
    palette = {
        "interface": "#4f9dff",
        "policy": "#ff6b6b",
        "capture": "#ffd166",
        "verification": "#06d6a0",
        "enforcement": "#ef476f",
        "reporting": "#c77dff",
        "orchestration": "#f78c6b",
        "tests": "#8d99ae",
        "other": "#adb5bd",
    }
    vis_nodes = []
    vis_edges = []
    show_kinds = {"module", "class", "function"}
    for n in graph["nodes"]:
        if n["kind"] not in show_kinds:
            continue
        layer = n.get("layer") or "other"
        color = palette.get(layer, "#adb5bd")
        if n["kind"] == "module":
            size, shape = 26, "dot"
        elif n["kind"] == "class":
            size, shape = 16, "diamond"
        else:
            size, shape = 9, "dot"
        title = f"{n['kind']}: {n['id']}"
        if n.get("doc"):
            title += "\\n" + (n["doc"].splitlines()[0][:120])
        vis_nodes.append(
            {
                "id": n["id"],
                "label": n["label"],
                "group": layer,
                "shape": shape,
                "size": size,
                "color": color,
                "title": title,
                "kind": n["kind"],
            }
        )
    edge_style = {
        "contains": {"color": "#dee2e6", "dashes": False},
        "imports": {"color": "#495057", "dashes": False},
        "inherits": {"color": "#e63946", "dashes": True},
        "calls": {"color": "#ced4da", "dashes": True},
    }
    valid_ids = {n["id"] for n in vis_nodes}
    for e in graph["edges"]:
        if e["source"] not in valid_ids or e["target"] not in valid_ids:
            continue
        style = edge_style.get(e["kind"], {})
        vis_edges.append(
            {
                "from": e["source"],
                "to": e["target"],
                "color": style.get("color", "#ccc"),
                "dashes": style.get("dashes", False),
                "kind": e["kind"],
                "arrows": "to" if e["kind"] != "contains" else "",
            }
        )
    data = json.dumps({"nodes": vis_nodes, "edges": vis_edges})
    meta = json.dumps(graph["metadata"])
    return _HTML_TEMPLATE.replace("__DATA__", data).replace("__META__", meta)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>AgentProof Recorder - Knowledge Graph</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body { margin:0; font-family:-apple-system,Segoe UI,Roboto,sans-serif; background:#0d1117; color:#e6edf3; }
  #bar { padding:10px 16px; background:#161b22; border-bottom:1px solid #30363d; display:flex; gap:14px; align-items:center; flex-wrap:wrap; }
  #bar h1 { font-size:15px; margin:0; font-weight:600; }
  #bar label { font-size:12px; opacity:.85; display:flex; gap:4px; align-items:center; }
  #net { width:100vw; height:calc(100vh - 50px); }
  .legend span { display:inline-block; width:11px; height:11px; border-radius:2px; margin-right:3px; vertical-align:middle; }
  #stats { font-size:12px; opacity:.7; margin-left:auto; }
  select, input { background:#0d1117; color:#e6edf3; border:1px solid #30363d; border-radius:4px; padding:2px 4px; }
</style>
</head>
<body>
<div id="bar">
  <h1>AgentProof Recorder — Knowledge Graph</h1>
  <label>show:
    <select id="kindFilter">
      <option value="all">modules + classes + functions</option>
      <option value="module" selected>modules only</option>
      <option value="structure">modules + classes</option>
    </select>
  </label>
  <label><input type="checkbox" id="showCalls"> call edges</label>
  <span class="legend" id="legend"></span>
  <span id="stats"></span>
</div>
<div id="net"></div>
<script>
const GRAPH = __DATA__;
const META = __META__;
const palette = {interface:"#4f9dff",policy:"#ff6b6b",capture:"#ffd166",verification:"#06d6a0",enforcement:"#ef476f",reporting:"#c77dff",orchestration:"#f78c6b",tests:"#8d99ae",other:"#adb5bd"};
document.getElementById("legend").innerHTML = Object.entries(palette)
  .map(([k,v]) => `<span style="background:${v}"></span>${k}`).join("&nbsp;&nbsp;");
document.getElementById("stats").textContent =
  `${META.module_count} modules · ${META.node_counts.class||0} classes · ${META.node_counts.function||0} functions`;

const container = document.getElementById("net");
let network;
function draw() {
  const kindMode = document.getElementById("kindFilter").value;
  const showCalls = document.getElementById("showCalls").checked;
  const allow = kindMode === "all" ? new Set(["module","class","function"])
    : kindMode === "structure" ? new Set(["module","class"])
    : new Set(["module"]);
  const nodes = GRAPH.nodes.filter(n => allow.has(n.kind));
  const ids = new Set(nodes.map(n => n.id));
  const edges = GRAPH.edges.filter(e => {
    if (!ids.has(e.from) || !ids.has(e.to)) return false;
    if (e.kind === "calls" && !showCalls) return false;
    return true;
  });
  const data = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
  const options = {
    physics: { stabilization: true, barnesHut: { gravitationalConstant: -8000, springLength: 120 } },
    nodes: { font: { color: "#e6edf3", size: 13 }, borderWidth: 0 },
    edges: { smooth: { type: "continuous" }, width: 0.6 },
    interaction: { hover: true, tooltipDelay: 120 },
  };
  network = new vis.Network(container, data, options);
}
document.getElementById("kindFilter").addEventListener("change", draw);
document.getElementById("showCalls").addEventListener("change", draw);
draw();
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Build AgentProof Recorder knowledge graph.")
    ap.add_argument("--print", action="store_true", dest="do_print", help="Print a text summary.")
    ap.add_argument("--out", default=str(OUTPUT_DIR), help="Output directory.")
    args = ap.parse_args()

    graph = build_graph()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "graph.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    (out_dir / "module_graph.mmd").write_text(render_module_mermaid(graph), encoding="utf-8")
    (out_dir / "architecture.mmd").write_text(render_architecture_mermaid(graph), encoding="utf-8")
    (out_dir / "index.html").write_text(render_html(graph), encoding="utf-8")

    meta = graph["metadata"]
    print(f"Knowledge graph written to {out_dir}/")
    print(f"  modules : {meta['module_count']}")
    print(f"  nodes   : {meta['node_counts']}")
    print(f"  edges   : {meta['edge_counts']}")
    if args.do_print:
        _print_summary(graph)
    return 0


def _print_summary(graph: dict[str, Any]) -> None:
    print("\nModule import fan-in (top 8):")
    mods = [n for n in graph["nodes"] if n["kind"] == "module" and n["id"].startswith("agentproof")]
    for n in sorted(mods, key=lambda m: m["meta"].get("imports_in", 0), reverse=True)[:8]:
        mm = n["meta"]
        print(f"  {n['id']:<28} in={mm.get('imports_in',0)} out={mm.get('imports_out',0)} loc={n.get('loc')}")


if __name__ == "__main__":
    raise SystemExit(main())
