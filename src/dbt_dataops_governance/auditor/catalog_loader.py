"""Declarative governance rule catalog loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dbt_dataops_governance.auditor.models import RuleMetadata, Severity

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG_PATH = DEFAULT_REPO_ROOT / "catalog" / "governance_rules.yaml"


def load_governance_rules(catalog_path: Path | None = None) -> dict[str, RuleMetadata]:
    """Load all 25 governance rules from catalog/governance_rules.yaml."""
    path = catalog_path or DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Governance rules catalog not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle)

    rules_list = raw.get("rules", [])
    if not isinstance(rules_list, list) or not rules_list:
        raise ValueError(f"Invalid or empty rules catalog: {path}")

    catalog: dict[str, RuleMetadata] = {}
    for entry in rules_list:
        rule_id = str(entry["id"])
        catalog[rule_id] = RuleMetadata(
            rule_id=rule_id,
            name=str(entry["name"]),
            family=str(entry["family"]),
            severity=Severity(str(entry["severity"])),
            dialects=tuple(entry["dialects"]),
            applies_to=tuple(entry["applies_to"]),
            rationale=str(entry["rationale"]),
            remediation=str(entry["remediation"]),
            known_false_positives=tuple(entry.get("known_false_positives", ())),
        )
    return catalog
