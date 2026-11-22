"""Multi-cloud SQL transpiler round-trip corpus and limitation detection tests."""

from __future__ import annotations

import pytest

from dbt_dataops_governance.transpiler import MultiCloudTranspiler

TRANSPILER = MultiCloudTranspiler()

DIRECTED_PAIRS = [
    ("duckdb", "spark"),
    ("duckdb", "snowflake"),
    ("spark", "snowflake"),
    ("spark", "duckdb"),
    ("snowflake", "duckdb"),
    ("snowflake", "spark"),
]

ROUNDTRIP_CORPUS: list[tuple[str, str]] = [
    (
        "cte_aggregation",
        (
            "WITH base_orders AS ("
            "SELECT order_id, customer_id, COALESCE(order_total_usd, 0) AS amount_usd "
            "FROM stg_orders WHERE order_status = 'PAID'"
            ") "
            "SELECT customer_id, COUNT(*) AS order_cnt, SUM(amount_usd) AS total_usd "
            "FROM base_orders GROUP BY customer_id HAVING COUNT(*) >= 1"
        ),
    ),
    (
        "window_ranking",
        (
            "SELECT order_id, customer_id, "
            "ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC) AS rn "
            "FROM stg_orders"
        ),
    ),
    (
        "case_nullif_join",
        (
            "SELECT o.order_id, "
            "CASE WHEN o.amount_usd > 100 THEN 'HIGH' ELSE 'STD' END AS tier, "
            "o.discount_usd / NULLIF(o.amount_usd, 0) AS discount_rate "
            "FROM stg_orders AS o "
            "INNER JOIN dim_customers AS c ON o.customer_id = c.customer_id"
        ),
    ),
    (
        "date_trunc_rollup",
        (
            "SELECT DATE_TRUNC('month', order_date) AS order_month, "
            "COUNT(DISTINCT customer_id) AS active_customers "
            "FROM fct_orders GROUP BY DATE_TRUNC('month', order_date)"
        ),
    ),
    (
        "ilike_predicate",
        "SELECT customer_id, country_code FROM dim_customers WHERE country_code ILIKE '%br%'",
    ),
]


@pytest.mark.parametrize(("source_dialect", "target_dialect"), DIRECTED_PAIRS)
@pytest.mark.parametrize(("corpus_name", "sql"), ROUNDTRIP_CORPUS, ids=[c[0] for c in ROUNDTRIP_CORPUS])
def test_roundtrip_corpus_across_all_cloud_pairs(
    corpus_name: str,
    sql: str,
    source_dialect: str,
    target_dialect: str,
) -> None:
    """Validate structural AST equivalence across all 6 DuckDB/Spark/Snowflake pairs."""
    result = TRANSPILER.transpile(
        sql,
        source_dialect=source_dialect,
        target_dialect=target_dialect,
        check_roundtrip=True,
    )
    assert result.roundtrip_equivalent is True, (
        f"Round-trip failed for {corpus_name} ({source_dialect} <-> {target_dialect}): {result.warnings}"
    )


def test_databricks_alias_maps_to_spark_and_preserves_dbt_jinja() -> None:
    """Databricks alias resolves to spark while keeping config, ref, and mask macros intact."""
    dbt_sql = (
        "{{ config(materialized='table') }}\n\n"
        "SELECT\n"
        "    o.order_id,\n"
        "    {{ mask_lgpd_pii('email', mode='email') }} AS email_masked\n"
        "FROM {{ ref('stg_demo__orders') }} AS o\n"
        "INNER JOIN {{ source('raw_demo', 'customers') }} AS c\n"
        "    ON o.customer_id = c.customer_id"
    )
    result = TRANSPILER.transpile(dbt_sql, source_dialect="duckdb", target_dialect="databricks")

    assert result.target_dialect == "spark"
    assert result.dbt_jinja_preserved is True
    assert "{{ config(materialized='table') }}" in result.transpiled_sql
    assert "{{ ref('stg_demo__orders') }}" in result.transpiled_sql
    assert "{{ source('raw_demo', 'customers') }}" in result.transpiled_sql
    assert "{{ mask_lgpd_pii('email', mode='email') }}" in result.transpiled_sql


def test_detects_documented_transpilation_limitations() -> None:
    """Detect QUALIFY, semi-structured FLATTEN, MERGE, and Spark CAST ANSI caveats."""
    qualify_res = TRANSPILER.transpile(
        "SELECT order_id FROM orders QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC) = 1",
        source_dialect="snowflake",
        target_dialect="spark",
    )
    assert any(lim.code == "LIM_QUALIFY" for lim in qualify_res.limitations)

    semi_res = TRANSPILER.transpile(
        "SELECT f.value FROM raw_events, LATERAL FLATTEN(INPUT => raw_events.payload) AS f",
        source_dialect="snowflake",
        target_dialect="duckdb",
    )
    assert any(lim.code == "LIM_SEMI_STRUCTURED" for lim in semi_res.limitations)

    cast_res = TRANSPILER.transpile(
        "SELECT CAST(order_id AS VARCHAR) AS order_id FROM orders",
        source_dialect="duckdb",
        target_dialect="spark",
    )
    assert any(lim.code == "LIM_SPARK_CAST_ANSI" for lim in cast_res.limitations)

    merge_res = TRANSPILER.transpile(
        "MERGE INTO tgt USING src ON tgt.id = src.id WHEN MATCHED THEN UPDATE SET tgt.val = src.val",
        source_dialect="snowflake",
        target_dialect="spark",
    )
    assert any(lim.code == "LIM_MERGE_SEMANTICS" for lim in merge_res.limitations)


def test_transpiler_rejects_unsupported_dialect_and_empty_sql() -> None:
    """Guard clauses reject unknown dialects and empty SQL fast."""
    with pytest.raises(ValueError, match="Unsupported dialect"):
        TRANSPILER.transpile("SELECT 1", source_dialect="duckdb", target_dialect="oracle")

    with pytest.raises(ValueError, match="must not be empty"):
        TRANSPILER.transpile("   ", source_dialect="duckdb", target_dialect="snowflake")
