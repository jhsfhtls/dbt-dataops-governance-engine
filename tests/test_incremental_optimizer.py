"""Incremental conversion optimizer and AuditEngine parity tests."""

from __future__ import annotations

import pytest

from dbt_dataops_governance.auditor import AuditEngine
from dbt_dataops_governance.transpiler import IncrementalOptimizer

OPTIMIZER = IncrementalOptimizer()
AUDITOR = AuditEngine()


@pytest.mark.parametrize(
    ("dialect", "expected_strategy", "expected_snippet"),
    [
        ("duckdb", "delete+insert", "INTERVAL '3 days'"),
        ("snowflake", "merge", "DATEADD('day', -3"),
        ("databricks", "merge", "INTERVAL 3 DAYS"),
        ("bigquery", "merge", "TIMESTAMP_SUB("),
    ],
)
def test_suggests_dialect_optimal_incremental_strategy(
    dialect: str,
    expected_strategy: str,
    expected_snippet: str,
) -> None:
    """Full-refresh model receives dialect-appropriate incremental config and watermark."""
    full_refresh_sql = (
        "{{ config(materialized='table') }}\n"
        "SELECT\n"
        "    order_id,\n"
        "    customer_id,\n"
        "    order_total_usd,\n"
        "    updated_at\n"
        "FROM {{ ref('stg_demo__orders') }}"
    )
    suggestion = OPTIMIZER.suggest(
        full_refresh_sql,
        model_name="fct_orders",
        target_dialect=dialect,
        lookback_days=3,
    )

    assert suggestion.already_incremental is False
    assert suggestion.recommended_strategy == expected_strategy
    assert suggestion.unique_key == "order_id"
    assert suggestion.watermark_column == "updated_at"
    assert suggestion.confidence == "HIGH"
    assert expected_snippet in suggestion.suggested_sql
    assert "{% if is_incremental() %}" in suggestion.suggested_sql

    # Generated SQL must satisfy AuditEngine without triggering PERF_003 or PERF_004
    audit_dialect = "spark" if dialect == "databricks" else dialect
    findings = AUDITOR.audit_sql(
        suggestion.suggested_sql,
        dialect=audit_dialect,
        file_path="models/core/fct_orders.sql",
    )
    finding_ids = {f.rule_id for f in findings}
    assert "PERF_003" not in finding_ids
    assert "PERF_004" not in finding_ids


def test_injects_and_before_group_by_when_where_already_exists() -> None:
    """When query already has WHERE and GROUP BY, incremental block uses AND before GROUP BY."""
    sql = (
        "SELECT\n"
        "    order_id,\n"
        "    customer_id,\n"
        "    updated_at,\n"
        "    SUM(order_total_usd) AS net_usd\n"
        "FROM {{ ref('stg_demo__orders') }}\n"
        "WHERE order_status = 'PAID'\n"
        "GROUP BY order_id, customer_id, updated_at"
    )
    suggestion = OPTIMIZER.suggest(sql, model_name="fct_paid_orders", target_dialect="duckdb")

    assert "AND updated_at >=" in suggestion.suggested_sql
    and_pos = suggestion.suggested_sql.index("AND updated_at >=")
    group_pos = suggestion.suggested_sql.index("GROUP BY")
    assert and_pos < group_pos
    assert any("GROUP BY" in w for w in suggestion.warnings)


def test_already_incremental_model_is_idempotent() -> None:
    """Models already carrying incremental config + is_incremental() are left unchanged."""
    inc_sql = (
        "{{ config(materialized='incremental', unique_key='order_id') }}\n"
        "SELECT order_id, updated_at FROM {{ ref('stg_demo__orders') }}\n"
        "{% if is_incremental() %}\n"
        "WHERE updated_at >= (SELECT MAX(updated_at) FROM {{ this }})\n"
        "{% endif %}"
    )
    suggestion = OPTIMIZER.suggest(inc_sql, model_name="fct_orders", target_dialect="duckdb")
    assert suggestion.already_incremental is True
    assert suggestion.suggested_sql == inc_sql


def test_low_confidence_fallback_when_no_key_or_watermark() -> None:
    """Emit LOW confidence and explicit warnings if PK and watermark cannot be inferred."""
    sql = "SELECT category_name, metric_value FROM {{ ref('stg_demo__metrics') }}"
    suggestion = OPTIMIZER.suggest(sql, model_name="fct_metrics", target_dialect="duckdb")

    assert suggestion.confidence == "LOW"
    assert suggestion.unique_key == "record_id"
    assert suggestion.watermark_column == "updated_at"
    assert len(suggestion.warnings) >= 2
