"""Deterministic renderer and sync checker for JORNADA_IMPLEMENTACAO.md."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from render_catalog import load_macros_registry, validate_macros_registry  # noqa: E402
from validate_catalog import load_catalog, validate_catalog  # noqa: E402

DEFAULT_PROGRESS_PATH = REPO_ROOT / "state" / "project_progress.json"
DEFAULT_RULES_PATH = REPO_ROOT / "catalog" / "governance_rules.yaml"
DEFAULT_MACROS_PATH = REPO_ROOT / "catalog" / "macros_registry.yaml"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "JORNADA_IMPLEMENTACAO.md"

VALID_PHASE_STATUSES = {"COMPLETED", "IN_PROGRESS", "PENDING"}


def load_json(path: Path) -> dict[str, Any]:
    """Load and parse JSON file using UTF-8."""
    if not path.is_file():
        raise FileNotFoundError(f"Progress JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Progress JSON root must be an object.")
    return data


def validate_progress(data: dict[str, Any]) -> None:
    """Validate structure and phase integrity of state/project_progress.json."""
    required = (
        "schema_version",
        "last_updated",
        "project_name",
        "current_phase_id",
        "overall_status",
        "phases",
        "history",
    )
    for key in required:
        if key not in data:
            raise ValueError(f"Missing required key in project_progress.json: '{key}'")

    phases = data.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError("'phases' must be a non-empty list.")

    seen_ids: set[str] = set()
    for idx, phase in enumerate(phases):
        ctx = f"phases[{idx}]"
        if not isinstance(phase, dict):
            raise ValueError(f"{ctx} must be an object.")
        for field in ("id", "label", "name", "branch", "status", "gate"):
            val = phase.get(field)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(f"{ctx}: '{field}' must be a non-empty string.")
        if phase["id"] in seen_ids:
            raise ValueError(f"{ctx}: duplicate phase id '{phase['id']}'.")
        seen_ids.add(phase["id"])
        if phase["status"] not in VALID_PHASE_STATUSES:
            raise ValueError(f"{ctx}: invalid status '{phase['status']}'.")
        if not isinstance(phase.get("deliverables"), list) or not phase["deliverables"]:
            raise ValueError(f"{ctx}: 'deliverables' must be a non-empty list.")

    if data["current_phase_id"] not in seen_ids:
        raise ValueError(f"current_phase_id '{data['current_phase_id']}' not found in phases.")


def _status_badge(status: str) -> str:
    """Return Portuguese status badge for a phase."""
    mapping = {
        "COMPLETED": "CONCLUIDO",
        "IN_PROGRESS": "EM ANDAMENTO",
        "PENDING": "PENDENTE",
    }
    return mapping.get(status, status)


def render_markdown(
    progress_data: dict[str, Any],
    rules_data: dict[str, Any],
    macros_data: dict[str, Any],
) -> str:
    """Render deterministic JORNADA_IMPLEMENTACAO.md in Brazilian Portuguese."""
    phases = progress_data["phases"]
    history = progress_data["history"]
    total_phases = len(phases)
    completed_count = sum(1 for p in phases if p["status"] == "COMPLETED")
    completion_pct = (completed_count / total_phases) * 100.0

    current_phase = next(p for p in phases if p["id"] == progress_data["current_phase_id"])
    next_phase = next((p for p in phases if p["status"] == "PENDING"), None)
    next_label = f"{next_phase['label']} - {next_phase['name']}" if next_phase else "Todas as fases concluidas"

    total_rules = len(rules_data["rules"])
    total_families = len(rules_data["families"])
    total_macros = len(macros_data["macros"])

    lines: list[str] = [
        '<div align="center">',
        "  <h2>Jornada de Implementacao — dbt-dataops-governance-engine</h2>",
        "  <p><i>Painel Vivo de Evolucao Arquitetural, Regras AST, Scaffolder Medallion & CI/CD</i></p>",
        f"  <p><b>Versao:</b> {progress_data['schema_version']} &nbsp;|&nbsp; "
        f"<b>Ultima Atualizacao:</b> {progress_data['last_updated']} &nbsp;|&nbsp; "
        "<b>Padroes:</b> ADR-001 • ADR-002 • ODCS v3.1 • LGPD</p>",
        "  <hr/>",
        "</div>",
        "<br/>",
        "",
        "# Jornada de Implementacao & Painel Vivo de Governanca",
        "",
        "Este documento e gerado de forma deterministica a partir de "
        "[`state/project_progress.json`](state/project_progress.json), "
        "[`catalog/governance_rules.yaml`](catalog/governance_rules.yaml) e "
        "[`catalog/macros_registry.yaml`](catalog/macros_registry.yaml).",
        "",
        "---",
        "",
        "## 1. Painel de Status Executivo",
        "",
        f"- **Fase Atual:** `{current_phase['label']} - {current_phase['name']}`",
        f"- **Status Geral:** `{progress_data['overall_status']}`",
        f"- **Progresso Estrutural:** **{completed_count} de {total_phases} Fases Concluidas ({completion_pct:.1f}%)**",
        f"- **Proxima Etapa Planejada:** `{next_label}`",
        f"- **Regras de Governanca Catalogadas:** **{total_rules} regras** em **{total_families} familias**",
        f"- **Macros Portaveis Registradas:** **{total_macros} macros cross-warehouse**",
        "",
        "```mermaid",
        "flowchart LR",
    ]

    for idx, phase in enumerate(phases):
        node_id = f"P{idx:02d}"
        badge = _status_badge(phase["status"])
        lines.append(f'    {node_id}["{phase["label"]}: {badge}"]')
    for idx in range(len(phases) - 1):
        lines.append(f"    P{idx:02d} --> P{idx + 1:02d}")

    lines.extend([
        "```",
        "",
        "---",
        "",
        "## 2. Cronograma & Gates das Fases (00 a 08)",
        "",
        "| Fase | Escopo | Branch | Status | Conclusao | Entregaveis Principais | Gate de Aceite |",
        "| :---: | :--- | :--- | :---: | :---: | :--- | :--- |",
    ])

    for phase in phases:
        deliverables_html = "<br/>".join(f"- {item}" for item in phase["deliverables"])
        completed_at = phase.get("completed_at") or "—"
        lines.append(
            f"| **{phase['label']}** | {phase['name']} | `{phase['branch']}` | "
            f"`{_status_badge(phase['status'])}` | `{completed_at}` | {deliverables_html} | {phase['gate']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 3. Historico de Marcos Concluidos",
        "",
        "| Data | Fase | Marco | Resumo |",
        "| :---: | :---: | :--- | :--- |",
    ])

    for entry in history:
        lines.append(
            f"| `{entry['date']}` | **{entry['phase']}** | {entry['milestone']} | {entry['summary']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Verificacao de Sincronia",
        "",
        "```bash",
        "python scripts/render_progress.py --check",
        "python scripts/render_progress.py",
        "```",
        "",
    ])

    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for JORNADA_IMPLEMENTACAO.md rendering and checking."""
    parser = argparse.ArgumentParser(description="Render or check JORNADA_IMPLEMENTACAO.md.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check whether JORNADA_IMPLEMENTACAO.md matches JSON and YAML sources without writing.",
    )
    parser.add_argument("--progress", type=Path, default=DEFAULT_PROGRESS_PATH, help="Path to project_progress.json")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH, help="Path to governance_rules.yaml")
    parser.add_argument("--macros", type=Path, default=DEFAULT_MACROS_PATH, help="Path to macros_registry.yaml")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path to JORNADA_IMPLEMENTACAO.md")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for deterministic progress tracker rendering."""
    args = parse_args(argv)
    try:
        progress_data = load_json(args.progress)
        validate_progress(progress_data)
        rules_data = load_catalog(args.rules)
        validate_catalog(rules_data)
        macros_data = load_macros_registry(args.macros)
        validate_macros_registry(macros_data)
        rendered = render_markdown(progress_data, rules_data, macros_data)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"[ERROR] Progress validation/rendering failed: {exc}", file=sys.stderr)
        return 2

    if args.check:
        if not args.output.is_file():
            print(f"[CHECK FAILED] Output file does not exist: {args.output}", file=sys.stderr)
            return 1
        current = args.output.read_text(encoding="utf-8")
        if current != rendered:
            print(f"[CHECK FAILED] {args.output} is out of sync with progress/catalog state.", file=sys.stderr)
            diff = difflib.unified_diff(
                current.splitlines(),
                rendered.splitlines(),
                fromfile=str(args.output),
                tofile="rendered_progress",
                lineterm="",
                n=3,
            )
            for line in list(diff)[:25]:
                print(line, file=sys.stderr)
            return 1
        print(f"[CHECK PASSED] {args.output} is synchronized with state/project_progress.json.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    print(f"[RENDER SUCCESS] Wrote {args.output}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
