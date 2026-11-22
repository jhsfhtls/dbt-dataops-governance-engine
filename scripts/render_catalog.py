"""Deterministic renderer and sync checker for CATALOG.md."""

from __future__ import annotations

import argparse
import difflib
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_catalog import (  # noqa: E402
    EXPECTED_FAMILY_COUNTS,
    VALID_DIALECTS,
    load_catalog,
    validate_catalog,
)

DEFAULT_RULES_PATH = REPO_ROOT / "catalog" / "governance_rules.yaml"
DEFAULT_MACROS_PATH = REPO_ROOT / "catalog" / "macros_registry.yaml"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "CATALOG.md"

VALID_MACRO_STATUSES = {"PLANNED", "IMPLEMENTED", "DEPRECATED"}


def load_macros_registry(macros_path: Path) -> dict[str, Any]:
    """Load and parse catalog/macros_registry.yaml using UTF-8."""
    if not macros_path.is_file():
        raise FileNotFoundError(f"Macros registry file not found: {macros_path}")

    with macros_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValueError("Macros registry root must be a YAML mapping.")
    return data


def validate_macros_registry(data: dict[str, Any]) -> None:
    """Validate schema integrity for catalog/macros_registry.yaml."""
    for field in ("schema_version", "updated_at"):
        val = data.get(field)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"Macros registry missing non-empty '{field}'.")

    macros = data.get("macros")
    if not isinstance(macros, list) or not macros:
        raise ValueError("Macros registry 'macros' must be a non-empty list.")

    seen_ids: set[str] = set()
    for idx, macro in enumerate(macros):
        ctx = f"macros[{idx}]"
        if not isinstance(macro, dict):
            raise ValueError(f"{ctx} must be a mapping.")
        for req in ("macro_id", "name", "category", "signature", "description", "usage_example"):
            val = macro.get(req)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(f"{ctx}: field '{req}' must be a non-empty string.")
        macro_id = macro["macro_id"]
        if macro_id in seen_ids:
            raise ValueError(f"{ctx}: duplicate macro_id '{macro_id}'.")
        seen_ids.add(macro_id)

        status = macro.get("status")
        if status not in VALID_MACRO_STATUSES:
            raise ValueError(f"{ctx}: invalid status '{status}'.")

        dialects = macro.get("supported_dialects")
        if not isinstance(dialects, list) or not dialects or not set(dialects).issubset(VALID_DIALECTS):
            raise ValueError(f"{ctx}: invalid supported_dialects {dialects!r}.")


def render_markdown(
    rules_data: dict[str, Any],
    macros_data: dict[str, Any],
    family_counts: Counter[str],
    severity_counts: Counter[str],
) -> str:
    """Render deterministic CATALOG.md content from validated YAML registries."""
    families = rules_data["families"]
    rules = rules_data["rules"]
    macros = macros_data["macros"]
    total_rules = sum(family_counts.values())

    lines: list[str] = [
        "# Governance Rules & Portable Macros Catalog",
        "",
        "> **Single Source of Truth (SSOT):** Deterministically rendered from "
        "[`catalog/governance_rules.yaml`](catalog/governance_rules.yaml) and "
        "[`catalog/macros_registry.yaml`](catalog/macros_registry.yaml). Do not edit manually.",
        "",
        f"- **Rules Schema Version:** `{rules_data['schema_version']}` (Updated: `{rules_data['updated_at']}`)",
        f"- **Macros Schema Version:** `{macros_data['schema_version']}` (Updated: `{macros_data['updated_at']}`)",
        f"- **Total Governance Rules:** **{total_rules}** across **{len(families)}** families",
        f"- **Severity Breakdown:** `CRITICAL`: **{severity_counts.get('CRITICAL', 0)}** | "
        f"`HIGH`: **{severity_counts.get('HIGH', 0)}** | "
        f"`MEDIUM`: **{severity_counts.get('MEDIUM', 0)}** | "
        f"`LOW`: **{severity_counts.get('LOW', 0)}**",
        f"- **Portable dbt Macros Registered:** **{len(macros)}**",
        "",
        "---",
        "",
        "## 1. Governance Families",
        "",
        "| Family ID | Display Name | Rules | Focus |",
        "| :--- | :--- | :---: | :--- |",
    ]

    for fam in families:
        fid = fam["family_id"]
        lines.append(
            f"| `{fid}` | {fam['name']} | {family_counts[fid]}/{EXPECTED_FAMILY_COUNTS[fid]} | {fam['description']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 2. Governance Rules Summary (25 Rules)",
        "",
        "| Rule ID | Family | Severity | Rule Name | Dialects | Applies To |",
        "| :--- | :--- | :---: | :--- | :--- | :--- |",
    ])

    for rule in rules:
        dialects = ", ".join(f"`{d}`" for d in rule["dialects"])
        applies_to = ", ".join(f"`{a}`" for a in rule["applies_to"])
        lines.append(
            f"| `{rule['id']}` | `{rule['family']}` | `{rule['severity']}` | "
            f"{rule['name']} | {dialects} | {applies_to} |"
        )

    lines.extend(["", "---", "", "## 3. Rule Specifications & False-Positive Guardrails", ""])

    rules_by_family: dict[str, list[dict[str, Any]]] = {fam["family_id"]: [] for fam in families}
    for rule in rules:
        rules_by_family[rule["family"]].append(rule)

    for fam in families:
        fid = fam["family_id"]
        lines.extend([f"### {fam['name']} (`{fid}`)", ""])
        for rule in rules_by_family[fid]:
            lines.extend([
                f"#### `{rule['id']}` — {rule['name']} (`{rule['severity']}`)",
                "",
                f"- **Rationale:** {rule['rationale']}",
                f"- **Remediation:** {rule['remediation']}",
                "- **Known False Positives:**",
            ])
            for fp in rule["known_false_positives"]:
                lines.append(f"  - {fp}")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## 4. Portable Cross-Warehouse dbt Macros",
        "",
        "| Macro | Category | Status | Supported Dialects | Signature | Description |",
        "| :--- | :--- | :---: | :--- | :--- | :--- |",
    ])

    for macro in macros:
        dialects = ", ".join(f"`{d}`" for d in macro["supported_dialects"])
        lines.append(
            f"| `{macro['name']}` | `{macro['category']}` | `{macro['status']}` | "
            f"{dialects} | `{macro['signature']}` | {macro['description']} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 5. Synchronization & Verification",
        "",
        "```bash",
        "python scripts/validate_catalog.py",
        "python scripts/render_catalog.py --check",
        "python scripts/render_catalog.py",
        "```",
        "",
    ])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for CATALOG.md rendering and sync checking."""
    parser = argparse.ArgumentParser(description="Render or check CATALOG.md from YAML registries.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that CATALOG.md matches the rendered YAML catalogs without writing.",
    )
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH, help="Path to governance_rules.yaml")
    parser.add_argument("--macros", type=Path, default=DEFAULT_MACROS_PATH, help="Path to macros_registry.yaml")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path to CATALOG.md")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for deterministic catalog rendering."""
    args = parse_args(argv)
    try:
        rules_data = load_catalog(args.rules)
        family_counts, severity_counts = validate_catalog(rules_data)
        macros_data = load_macros_registry(args.macros)
        validate_macros_registry(macros_data)
        rendered = render_markdown(rules_data, macros_data, family_counts, severity_counts)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        print(f"[ERROR] Catalog validation/rendering failed: {exc}", file=sys.stderr)
        return 2

    if args.check:
        if not args.output.is_file():
            print(f"[CHECK FAILED] Output file does not exist: {args.output}", file=sys.stderr)
            return 1
        current = args.output.read_text(encoding="utf-8")
        if current != rendered:
            print(f"[CHECK FAILED] {args.output} is out of sync with YAML catalogs.", file=sys.stderr)
            diff = difflib.unified_diff(
                current.splitlines(),
                rendered.splitlines(),
                fromfile=str(args.output),
                tofile="rendered_catalog",
                lineterm="",
                n=3,
            )
            for line in list(diff)[:25]:
                print(line, file=sys.stderr)
            return 1
        print(f"[CHECK PASSED] {args.output} is synchronized ({sum(family_counts.values())} rules, {len(macros_data['macros'])} macros).")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    print(f"[RENDER SUCCESS] Wrote {args.output} ({sum(family_counts.values())} rules, {len(macros_data['macros'])} macros).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
