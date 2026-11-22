"""Static YAML rule evaluators for dbt schema files and ODCS v3.1 contracts."""

from __future__ import annotations

import re
from typing import Any

import yaml

from dbt_dataops_governance.auditor.models import AuditFinding, RuleMetadata

PII_YAML_COL_RE = re.compile(
    r"^(cpf|cnpj_cpf|email|telefone|celular|phone|rg|cnh|nome_completo|full_name|ssn|passport|birth_date|full_address)(_masked)?$",
    re.IGNORECASE,
)
PII_MODEL_HINT_RE = re.compile(
    r"(customer|client|user|person|employee|patient|lead|partner)",
    re.IGNORECASE,
)
SECRET_KEY_NAME_RE = re.compile(
    r"^(password|passwd|secret|api_key|api_token|access_key|auth_token|private_key)$",
    re.IGNORECASE,
)


def _make_finding(
    catalog: dict[str, RuleMetadata],
    rule_id: str,
    file_path: str,
    message: str,
) -> AuditFinding:
    """Construct an AuditFinding from catalog metadata for YAML rules."""
    meta = catalog[rule_id]
    return AuditFinding(
        rule_id=rule_id,
        rule_name=meta.name,
        family=meta.family,
        severity=meta.severity,
        file_path=file_path,
        line=1,
        message=message,
        remediation=meta.remediation,
    )


def _extract_test_names(raw_tests: Any) -> set[str]:
    """Normalize dbt data_tests/tests entries into a set of test names."""
    if not isinstance(raw_tests, list):
        return set()
    names: set[str] = set()
    for item in raw_tests:
        if isinstance(item, str):
            names.add(item.split(".")[-1].lower())
        elif isinstance(item, dict):
            for key in item:
                names.add(str(key).split(".")[-1].lower())
    return names


def _get_model_meta(model: dict[str, Any]) -> dict[str, Any]:
    """Return merged meta dict from model.meta and model.config.meta."""
    merged: dict[str, Any] = {}
    if isinstance(model.get("meta"), dict):
        merged.update(model["meta"])
    cfg = model.get("config")
    if isinstance(cfg, dict) and isinstance(cfg.get("meta"), dict):
        merged.update(cfg["meta"])
    return merged


def _has_enforced_contract(model: dict[str, Any]) -> bool:
    """Return True when dbt model enforces contract: {enforced: true}."""
    cfg = model.get("config")
    if isinstance(cfg, dict) and isinstance(cfg.get("contract"), dict):
        if cfg["contract"].get("enforced") is True:
            return True
    direct_contract = model.get("contract")
    if isinstance(direct_contract, dict) and direct_contract.get("enforced") is True:
        return True
    return False


def _scan_yaml_secrets(
    node: Any,
    file_path: str,
    catalog: dict[str, RuleMetadata],
) -> list[AuditFinding]:
    """Recursively check YAML mappings for hardcoded literal secrets (LGPD_004)."""
    findings: list[AuditFinding] = []
    if isinstance(node, dict):
        for key, value in node.items():
            key_str = str(key)
            if SECRET_KEY_NAME_RE.match(key_str) and isinstance(value, str):
                stripped = value.strip()
                if stripped and "env_var(" not in stripped:
                    findings.append(
                        _make_finding(
                            catalog,
                            "LGPD_004",
                            file_path,
                            f"Hardcoded literal credential under YAML key '{key_str}'; use env_var().",
                        )
                    )
                    return findings
            else:
                findings.extend(_scan_yaml_secrets(value, file_path, catalog))
                if findings:
                    return findings
    elif isinstance(node, list):
        for item in node:
            findings.extend(_scan_yaml_secrets(item, file_path, catalog))
            if findings:
                return findings
    return findings


def _evaluate_dbt_model_yaml(
    model: dict[str, Any],
    file_path: str,
    catalog: dict[str, RuleMetadata],
) -> list[AuditFinding]:
    """Evaluate QUAL_001, QUAL_002, QUAL_003, QUAL_006, and LGPD_003 on one dbt model YAML block."""
    findings: list[AuditFinding] = []
    model_name = str(model.get("name", "<unnamed>"))
    columns = model.get("columns") if isinstance(model.get("columns"), list) else []

    # QUAL_001: Primary key unique + not_null test coverage
    model_tests = _extract_test_names(model.get("data_tests") or model.get("tests"))
    has_composite_unique = "unique_combination_of_columns" in model_tests

    has_unique_col = False
    has_not_null_col = False
    has_pk_with_both = False
    undocumented_cols: list[str] = []
    cols_missing_type: list[str] = []
    fk_missing_rel: list[str] = []
    has_pii_col = False

    for col in columns:
        if not isinstance(col, dict):
            continue
        col_name = str(col.get("name", ""))
        col_desc = col.get("description")
        if not isinstance(col_desc, str) or not col_desc.strip():
            undocumented_cols.append(col_name or "<unnamed>")

        if not col.get("data_type"):
            cols_missing_type.append(col_name)

        if PII_YAML_COL_RE.match(col_name):
            has_pii_col = True

        col_tests = _extract_test_names(col.get("data_tests") or col.get("tests"))
        if "unique" in col_tests:
            has_unique_col = True
        if "not_null" in col_tests:
            has_not_null_col = True
        if "unique" in col_tests and "not_null" in col_tests:
            has_pk_with_both = True

        # QUAL_006: Foreign-key columns (*_id, *_sk, *_key) not acting as unique PK
        is_key_col = col_name.lower().endswith(("_id", "_sk", "_key"))
        if is_key_col and "unique" not in col_tests and "relationships" not in col_tests:
            fk_missing_rel.append(col_name)

    if not (has_pk_with_both or (has_composite_unique and has_not_null_col) or (has_unique_col and has_not_null_col)):
        findings.append(
            _make_finding(
                catalog,
                "QUAL_001",
                file_path,
                f"Model '{model_name}' lacks primary key unique + not_null schema tests.",
            )
        )

    # QUAL_002: 100% model and column description coverage
    model_desc = model.get("description")
    if not isinstance(model_desc, str) or not model_desc.strip() or undocumented_cols:
        findings.append(
            _make_finding(
                catalog,
                "QUAL_002",
                file_path,
                f"Model '{model_name}' has incomplete documentation (model description or columns: {undocumented_cols}).",
            )
        )

    # QUAL_003: Public/core/mart models require enforced contract + column data_types
    is_public_layer = model_name.lower().startswith(("dim_", "fct_", "mart_"))
    if is_public_layer and (not _has_enforced_contract(model) or cols_missing_type):
        findings.append(
            _make_finding(
                catalog,
                "QUAL_003",
                file_path,
                f"Public model '{model_name}' must set config.contract.enforced: true and typed columns.",
            )
        )

    # QUAL_006: Foreign keys in fact/mart models require relationships test
    if fk_missing_rel and (model_name.lower().startswith(("fct_", "mart_")) or len(columns) > 1):
        findings.append(
            _make_finding(
                catalog,
                "QUAL_006",
                file_path,
                f"Model '{model_name}' foreign-key column(s) {fk_missing_rel} lack a 'relationships' integrity test.",
            )
        )

    # LGPD_003: Models handling personal attributes require meta.lgpd_tier or meta.pii
    meta = _get_model_meta(model)
    handles_personal_data = has_pii_col or bool(PII_MODEL_HINT_RE.search(model_name))
    if handles_personal_data and "lgpd_tier" not in meta and "pii" not in meta:
        findings.append(
            _make_finding(
                catalog,
                "LGPD_003",
                file_path,
                f"Model '{model_name}' handles personal attributes without meta.lgpd_tier classification.",
            )
        )

    return findings


def evaluate_yaml_document(
    raw_yaml: str,
    file_path: str,
    catalog: dict[str, RuleMetadata],
) -> tuple[list[AuditFinding], str | None]:
    """Parse a dbt schema YAML or ODCS contract YAML and evaluate governance rules."""
    if not raw_yaml.strip():
        return [], None

    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        return [], f"YAML parse error: {exc}"

    if not isinstance(data, dict):
        return [], None

    findings: list[AuditFinding] = []
    findings.extend(_scan_yaml_secrets(data, file_path, catalog))

    # ODCS v3.1 contract check (QUAL_003)
    if "dataContractSpecification" in data:
        spec_ver = str(data.get("dataContractSpecification", ""))
        if not spec_ver.startswith("3.1"):
            findings.append(
                _make_finding(
                    catalog,
                    "QUAL_003",
                    file_path,
                    f"ODCS contract version '{spec_ver}' does not conform to 3.1.x.",
                )
            )
        return findings, None

    models = data.get("models")
    if isinstance(models, list):
        for model in models:
            if isinstance(model, dict):
                findings.extend(_evaluate_dbt_model_yaml(model, file_path, catalog))

    return findings, None
