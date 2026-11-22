"""Integration, multi-dialect, zero-execution, and Client Path Shield tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dbt_dataops_governance.auditor import AuditEngine, ClientPathShieldError

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("dialect", ["duckdb", "snowflake", "spark", "bigquery"])
def test_multi_dialect_static_parsing(dialect: str) -> None:
    """Auditor parses SQL across all 4 supported dialects without errors."""
    engine = AuditEngine()
    findings = engine.audit_sql(
        "SELECT order_id, customer_id FROM {{ ref('stg_demo__orders') }}",
        dialect=dialect,
        file_path="models/core/fct_orders.sql",
    )
    assert any(f.rule_id == "PERF_003" for f in findings)


def test_unsupported_dialect_raises_value_error() -> None:
    """Reject unknown SQL dialects fast."""
    engine = AuditEngine()
    with pytest.raises(ValueError, match="Unsupported dialect"):
        engine.audit_sql("SELECT 1", dialect="oracle")


def test_zero_execution_safety_on_destructive_sql() -> None:
    """Destructive SQL statements are parsed statically and never executed."""
    engine = AuditEngine()
    sql = "DROP TABLE IF EXISTS production_orders; SELECT * FROM raw_orders;"
    findings = engine.audit_sql(sql, dialect="duckdb", file_path="legacy_drop.sql")
    assert any(f.rule_id == "PERF_001" for f in findings)


def test_client_path_shield_blocks_writing_external_report_inside_repo(tmp_path: Path) -> None:
    """Client Path Shield forbids persisting external audit outputs inside public repo."""
    client_dir = tmp_path / "external_client_repo"
    client_dir.mkdir()
    (client_dir / "legacy.sql").write_text("SELECT * FROM raw_clients;", encoding="utf-8")

    engine = AuditEngine(repo_root=REPO_ROOT)
    forbidden_output = REPO_ROOT / "client_audit_leak.md"

    with pytest.raises(ClientPathShieldError, match="Client Path Shield"):
        engine.audit_path(client_dir, output_path=forbidden_output, output_format="markdown")

    assert not forbidden_output.exists()


def test_client_path_shield_blocks_traversal_segments(tmp_path: Path) -> None:
    """Explicit '..' traversal segments in output_path are rejected."""
    client_dir = tmp_path / "external_client_repo"
    client_dir.mkdir()
    (client_dir / "legacy.sql").write_text("SELECT 1 AS ok;", encoding="utf-8")

    engine = AuditEngine(repo_root=REPO_ROOT)
    traversal_output = Path("..") / "escaped_report.md"

    with pytest.raises(ClientPathShieldError, match="Path traversal"):
        engine.audit_path(client_dir, output_path=traversal_output)


def test_audit_path_writes_markdown_and_json_scorecards(tmp_path: Path) -> None:
    """Full directory audit computes Scorecard, risk levels, and writes UTF-8 LF reports."""
    project_dir = tmp_path / "synthetic_dbt_project"
    staging_dir = project_dir / "models" / "staging"
    marts_dir = project_dir / "models" / "marts"
    staging_dir.mkdir(parents=True)
    marts_dir.mkdir(parents=True)

    (staging_dir / "stg_demo__orders.sql").write_text(
        "SELECT TRIM(CAST(order_id AS VARCHAR)) AS order_id, NULLIF(status, '') AS status "
        "FROM {{ source('raw_demo', 'orders') }}",
        encoding="utf-8",
    )
    (marts_dir / "mart_orders.sql").write_text(
        "SELECT * FROM {{ ref('stg_demo__orders') }}",
        encoding="utf-8",
    )
    (marts_dir / "_models.yml").write_text(
        (
            "models:\n"
            "  - name: mart_orders\n"
            "    description: Synthetic orders mart.\n"
            "    config:\n"
            "      contract:\n"
            "        enforced: true\n"
            "    columns:\n"
            "      - name: order_id\n"
            "        description: Order primary key.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
        ),
        encoding="utf-8",
    )

    reports_dir = tmp_path / "reports"
    md_out = reports_dir / "audit.md"
    json_out = reports_dir / "audit.json"

    engine = AuditEngine(repo_root=REPO_ROOT)
    summary_md = engine.audit_path(project_dir, dialect="duckdb", output_path=md_out, output_format="markdown")
    summary_json = engine.audit_path(project_dir, dialect="duckdb", output_path=json_out, output_format="json")

    assert summary_md.files_audited == 3
    assert summary_md.score == 92.0  # 100 - 8 (PERF_001 HIGH)
    assert summary_md.grade == "A"
    assert summary_md.finops_risk_level == "HIGH"
    assert summary_md.lgpd_risk_level == "LOW"

    md_bytes = md_out.read_bytes()
    assert not md_bytes.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in md_bytes
    assert "Governance Score:" in md_out.read_text(encoding="utf-8")

    parsed_json = json.loads(json_out.read_text(encoding="utf-8"))
    assert parsed_json["score"] == summary_json.score == 92.0
    assert parsed_json["findings"][0]["rule_id"] == "PERF_001"
