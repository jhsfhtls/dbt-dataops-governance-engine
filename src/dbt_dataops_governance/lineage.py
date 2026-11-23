"""Static dbt/SQL lineage graph extractor and pure Mermaid flowchart renderer."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dbt_dataops_governance.auditor.jinja_preprocessor import preprocess_dbt_sql

IGNORED_DIRS = {".git", ".venv", "target", "dbt_packages", "logs", "macros", "__pycache__"}


def _infer_layer(file_path: str) -> str:
    """Infer Medallion layer label from file path and model prefix."""
    norm = file_path.replace("\\", "/").lower()
    stem = Path(norm).stem
    if "/staging/" in norm or stem.startswith("stg_"):
        return "staging"
    if "/core/" in norm or stem.startswith(("dim_", "fct_")):
        return "core"
    if "/marts/" in norm or "/gold/" in norm or stem.startswith("mart_"):
        return "marts"
    return "model"


def _mermaid_id(node_id: str) -> str:
    """Sanitize node id for Mermaid node declarations."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", node_id)


def extract_lineage(target_path: Path | str) -> dict[str, Any]:
    """Extract deterministic ref/source DAG nodes, edges, and Mermaid flowchart."""
    target = Path(target_path)
    if not target.exists():
        raise FileNotFoundError(f"Lineage target path does not exist: {target}")

    sql_files: list[Path]
    if target.is_file():
        sql_files = [target] if target.suffix.lower() == ".sql" else []
    else:
        sql_files = [
            p
            for p in sorted(target.rglob("*.sql"))
            if not any(part in IGNORED_DIRS for part in p.parts)
        ]

    nodes: dict[str, dict[str, str]] = {}
    edges_set: set[tuple[str, str, str]] = set()

    for sql_file in sql_files:
        rel_label = sql_file.name if target.is_file() else sql_file.relative_to(target).as_posix()
        model_id = sql_file.stem
        nodes[model_id] = {
            "id": model_id,
            "kind": "model",
            "layer": _infer_layer(rel_label),
            "file_path": rel_label,
        }

        raw_sql = sql_file.read_text(encoding="utf-8", errors="replace")
        prep = preprocess_dbt_sql(raw_sql, file_path=rel_label)

        for ref_name in prep.refs:
            if ref_name not in nodes:
                nodes[ref_name] = {
                    "id": ref_name,
                    "kind": "ref",
                    "layer": "seed" if ref_name.startswith("raw_") else _infer_layer(ref_name),
                    "file_path": "",
                }
            edges_set.add((ref_name, model_id, "ref"))

        for src_name, tbl_name in prep.sources:
            src_id = f"{src_name}.{tbl_name}"
            if src_id not in nodes:
                nodes[src_id] = {
                    "id": src_id,
                    "kind": "source",
                    "layer": "source",
                    "file_path": "",
                }
            edges_set.add((src_id, model_id, "source"))

    ordered_nodes = [nodes[k] for k in sorted(nodes)]
    ordered_edges = [
        {"source": src, "target": tgt, "relation": rel}
        for src, tgt, rel in sorted(edges_set)
    ]

    mermaid_lines = ["flowchart LR"]
    for node in ordered_nodes:
        nid = _mermaid_id(node["id"])
        mermaid_lines.append(f'    {nid}["{node["id"]} ({node["layer"]})"]')
    for edge in ordered_edges:
        mermaid_lines.append(f"    {_mermaid_id(edge['source'])} --> {_mermaid_id(edge['target'])}")

    return {
        "target_path": str(target.resolve()),
        "total_nodes": len(ordered_nodes),
        "total_edges": len(ordered_edges),
        "nodes": ordered_nodes,
        "edges": ordered_edges,
        "mermaid": "\n".join(mermaid_lines),
    }
