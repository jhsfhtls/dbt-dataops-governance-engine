"""Schema and governance completeness validator for catalog/governance_rules.yaml."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = REPO_ROOT / "catalog" / "governance_rules.yaml"

EXPECTED_FAMILY_COUNTS: dict[str, int] = {
    "PERFORMANCE_FINOPS": 7,
    "MODELING_MEDALLION": 6,
    "QUALITY_CONTRACTS": 6,
    "LGPD_PII_SECURITY": 6,
}
FAMILY_PREFIXES: dict[str, str] = {
    "PERFORMANCE_FINOPS": "PERF_",
    "MODELING_MEDALLION": "MOD_",
    "QUALITY_CONTRACTS": "QUAL_",
    "LGPD_PII_SECURITY": "LGPD_",
}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_DIALECTS = {"duckdb", "snowflake", "spark", "bigquery"}
VALID_APPLIES_TO = {"sql", "dbt_model", "dbt_yaml", "odcs_contract"}
RULE_ID_PATTERN = re.compile(r"^(PERF|MOD|QUAL|LGPD)_[0-9]{3}$")
TOTAL_EXPECTED_RULES = 25


def load_catalog(catalog_path: Path) -> dict[str, Any]:
    """Load and parse the YAML rule catalog using UTF-8 encoding."""
    if not catalog_path.is_file():
        raise FileNotFoundError(f"Catalog file not found: {catalog_path}")

    with catalog_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ValueError("Catalog root must be a YAML mapping.")
    return data


def _require_non_empty_str(mapping: dict[str, Any], field: str, context: str) -> list[str]:
    """Return an error list if a field is missing or not a non-empty string."""
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        return [f"{context}: field '{field}' must be a non-empty string."]
    return []


def _validate_families(families: Any) -> tuple[set[str], list[str]]:
    """Validate the top-level family declarations."""
    errors: list[str] = []
    if not isinstance(families, list) or len(families) != len(EXPECTED_FAMILY_COUNTS):
        errors.append(
            f"Expected exactly {len(EXPECTED_FAMILY_COUNTS)} families, "
            f"got {len(families) if isinstance(families, list) else type(families).__name__}."
        )
        return set(), errors

    family_ids: set[str] = set()
    for idx, entry in enumerate(families):
        ctx = f"families[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"{ctx}: must be a mapping.")
            continue
        for field in ("family_id", "name", "description"):
            errors.extend(_require_non_empty_str(entry, field, ctx))
        fid = entry.get("family_id")
        if isinstance(fid, str) and fid:
            if fid in family_ids:
                errors.append(f"{ctx}: duplicate family_id '{fid}'.")
            family_ids.add(fid)

    if family_ids != set(EXPECTED_FAMILY_COUNTS):
        errors.append(
            f"Family IDs mismatch: expected {sorted(EXPECTED_FAMILY_COUNTS)}, "
            f"got {sorted(family_ids)}."
        )
    return family_ids, errors


def _validate_string_list(
    rule: dict[str, Any],
    field: str,
    allowed: set[str] | None,
    ctx: str,
) -> list[str]:
    """Validate a non-empty list of non-empty strings, optionally bounded by an allowlist."""
    value = rule.get(field)
    if not isinstance(value, list) or not value:
        return [f"{ctx}: field '{field}' must be a non-empty list."]

    errors: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{ctx}.{field}[{idx}]: must be a non-empty string.")
            continue
        if allowed is not None and item not in allowed:
            errors.append(
                f"{ctx}.{field}[{idx}]: invalid value '{item}'; allowed={sorted(allowed)}."
            )
    return errors


def _validate_single_rule(
    rule: Any,
    idx: int,
    valid_families: set[str],
    seen_ids: set[str],
) -> list[str]:
    """Validate schema, constraints, and examples for one governance rule."""
    ctx = f"rules[{idx}]"
    if not isinstance(rule, dict):
        return [f"{ctx}: must be a mapping."]

    errors: list[str] = []
    rule_id = rule.get("id")
    if not isinstance(rule_id, str) or not RULE_ID_PATTERN.match(rule_id):
        errors.append(f"{ctx}: invalid or missing rule 'id' ({rule_id!r}).")
    elif rule_id in seen_ids:
        errors.append(f"{ctx}: duplicate rule id '{rule_id}'.")
    else:
        seen_ids.add(rule_id)
        ctx = f"rule[{rule_id}]"

    family = rule.get("family")
    if not isinstance(family, str) or family not in valid_families:
        errors.append(f"{ctx}: unknown family {family!r}.")
    elif isinstance(rule_id, str) and not rule_id.startswith(FAMILY_PREFIXES[family]):
        errors.append(
            f"{ctx}: rule id '{rule_id}' must start with '{FAMILY_PREFIXES[family]}' for family '{family}'."
        )

    severity = rule.get("severity")
    if severity not in VALID_SEVERITIES:
        errors.append(
            f"{ctx}: invalid severity {severity!r}; expected one of {sorted(VALID_SEVERITIES)}."
        )

    for field in ("name", "rationale", "remediation", "bad_example", "good_example"):
        errors.extend(_require_non_empty_str(rule, field, ctx))

    errors.extend(_validate_string_list(rule, "dialects", VALID_DIALECTS, ctx))
    errors.extend(_validate_string_list(rule, "applies_to", VALID_APPLIES_TO, ctx))
    errors.extend(_validate_string_list(rule, "known_false_positives", None, ctx))
    return errors


def validate_catalog(data: dict[str, Any]) -> tuple[Counter[str], Counter[str]]:
    """Validate the full governance rules catalog and return family & severity counts."""
    errors: list[str] = []
    for top_field in ("schema_version", "updated_at"):
        errors.extend(_require_non_empty_str(data, top_field, "root"))

    valid_families, family_errors = _validate_families(data.get("families"))
    errors.extend(family_errors)

    rules = data.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Catalog 'rules' field must be a YAML list.")

    if len(rules) != TOTAL_EXPECTED_RULES:
        errors.append(f"Expected exactly {TOTAL_EXPECTED_RULES} rules, got {len(rules)}.")

    seen_ids: set[str] = set()
    family_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()

    for idx, rule in enumerate(rules):
        errors.extend(_validate_single_rule(rule, idx, valid_families, seen_ids))
        if isinstance(rule, dict):
            if isinstance(rule.get("family"), str):
                family_counts[rule["family"]] += 1
            if isinstance(rule.get("severity"), str):
                severity_counts[rule["severity"]] += 1

    for family_id, expected_count in EXPECTED_FAMILY_COUNTS.items():
        actual = family_counts.get(family_id, 0)
        if actual != expected_count:
            errors.append(
                f"Family '{family_id}' count mismatch: expected {expected_count}, got {actual}."
            )

    if errors:
        formatted = "\n".join(f"  - {err}" for err in errors)
        raise ValueError(f"Governance catalog validation failed ({len(errors)} errors):\n{formatted}")

    return family_counts, severity_counts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for catalog validation."""
    parser = argparse.ArgumentParser(description="Validate catalog/governance_rules.yaml schema.")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="Path to governance_rules.yaml (defaults to repository catalog).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for governance catalog schema validation."""
    args = parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
        family_counts, severity_counts = validate_catalog(catalog)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print("=================================================================")
    print("dbt-dataops-governance-engine | Rule Catalog Schema Validation")
    print("=================================================================")
    print(f"Catalog Path:   {args.catalog}")
    print(f"Schema Version: {catalog['schema_version']} (updated {catalog['updated_at']})")
    print(f"Total Rules:    {sum(family_counts.values())}/{TOTAL_EXPECTED_RULES}")
    print("\nRules by Family:")
    for family_id, expected in EXPECTED_FAMILY_COUNTS.items():
        print(f"  - {family_id:<22} {family_counts[family_id]:>2}/{expected}")
    print("\nRules by Severity:")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        print(f"  - {sev:<10} {severity_counts.get(sev, 0):>2}")
    print("\n[PASS] Governance rule catalog schema validated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
