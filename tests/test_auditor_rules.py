"""Positive, negative, and false-positive guardrail tests for all 25 governance rules."""

from __future__ import annotations

import pytest

from dbt_dataops_governance.auditor import AuditEngine

ENGINE = AuditEngine()

POSITIVE_AND_NEGATIVE_CASES: list[tuple[str, str, str, str, str]] = [
    # --- PERFORMANCE_FINOPS (7) ---
    (
        "PERF_001",
        "sql",
        "models/marts/mart_orders_summary.sql",
        "SELECT * FROM {{ ref('fct_orders') }}",
        "SELECT order_id, customer_id, order_total_usd FROM {{ ref('fct_orders') }}",
    ),
    (
        "PERF_002",
        "sql",
        "models/core/fct_orders.sql",
        (
            "SELECT o.order_id, c.segment "
            "FROM {{ ref('stg_demo__orders') }} AS o "
            "CROSS JOIN {{ ref('stg_demo__customers') }} AS c"
        ),
        (
            "SELECT o.order_id, c.segment "
            "FROM {{ ref('stg_demo__orders') }} AS o "
            "INNER JOIN {{ ref('stg_demo__customers') }} AS c "
            "ON o.customer_id = c.customer_id"
        ),
    ),
    (
        "PERF_003",
        "sql",
        "models/core/fct_orders.sql",
        (
            "{{ config(materialized='incremental', unique_key='order_id') }}\n"
            "SELECT order_id, updated_at FROM {{ ref('stg_demo__orders') }}"
        ),
        (
            "{{ config(materialized='incremental', unique_key='order_id') }}\n"
            "SELECT order_id, updated_at FROM {{ ref('stg_demo__orders') }}\n"
            "{% if is_incremental() %}\n"
            "WHERE updated_at >= (SELECT MAX(updated_at) FROM {{ this }})\n"
            "{% endif %}"
        ),
    ),
    (
        "PERF_004",
        "sql",
        "models/core/fct_orders.sql",
        (
            "SELECT order_id FROM {{ ref('stg_demo__orders') }} "
            "WHERE EXTRACT(YEAR FROM order_created_at) = 2026"
        ),
        (
            "SELECT order_id FROM {{ ref('stg_demo__orders') }} "
            "WHERE order_created_at >= TIMESTAMP '2026-01-01 00:00:00' "
            "AND order_created_at < TIMESTAMP '2027-01-01 00:00:00'"
        ),
    ),
    (
        "PERF_005",
        "sql",
        "models/marts/mart_customer_metrics.sql",
        (
            "SELECT c.customer_id, "
            "(SELECT COUNT(*) FROM {{ ref('stg_demo__orders') }} o WHERE o.customer_id = c.customer_id) AS cnt, "
            "(SELECT SUM(o.order_total_usd) FROM {{ ref('stg_demo__orders') }} o WHERE o.customer_id = c.customer_id) AS total "
            "FROM {{ ref('stg_demo__customers') }} AS c"
        ),
        (
            "WITH metrics AS ("
            "SELECT customer_id, COUNT(*) AS cnt, SUM(order_total_usd) AS total "
            "FROM {{ ref('stg_demo__orders') }} GROUP BY customer_id"
            ") "
            "SELECT c.customer_id, COALESCE(m.cnt, 0) AS cnt, COALESCE(m.total, 0) AS total "
            "FROM {{ ref('stg_demo__customers') }} AS c "
            "LEFT JOIN metrics AS m ON c.customer_id = m.customer_id"
        ),
    ),
    (
        "PERF_006",
        "sql",
        "models/core/fct_orders.sql",
        (
            "WITH sorted_orders AS ("
            "SELECT order_id, order_created_at FROM {{ ref('stg_demo__orders') }} ORDER BY order_created_at DESC"
            ") SELECT order_id FROM sorted_orders"
        ),
        (
            "WITH ranked_orders AS ("
            "SELECT order_id, ROW_NUMBER() OVER (ORDER BY order_created_at DESC) AS rn "
            "FROM {{ ref('stg_demo__orders') }}"
            ") SELECT order_id FROM ranked_orders"
        ),
    ),
    (
        "PERF_007",
        "sql",
        "models/core/fct_orders.sql",
        "SELECT DISTINCT order_id, customer_id FROM {{ ref('stg_demo__orders') }}",
        (
            "SELECT order_id, customer_id FROM {{ ref('stg_demo__orders') }} "
            "UNION ALL "
            "SELECT order_id, customer_id FROM {{ ref('stg_demo__orders_archive') }}"
        ),
    ),
    # --- MODELING_MEDALLION (6) ---
    (
        "MOD_001",
        "sql",
        "models/core/fct_orders.sql",
        "{{ config(materialized='table') }}\nSELECT order_id FROM analytics_prod.raw_demo.orders",
        "{{ config(materialized='table') }}\nSELECT order_id FROM {{ ref('stg_demo__orders') }}",
    ),
    (
        "MOD_002",
        "sql",
        "models/core/fct_orders.sql",
        "{{ config(materialized='table') }}\nSELECT order_id FROM {{ source('raw_demo', 'orders') }}",
        "{{ config(materialized='table') }}\nSELECT order_id FROM {{ ref('stg_demo__orders') }}",
    ),
    (
        "MOD_003",
        "sql",
        "models/staging/stg_demo__orders.sql",
        (
            "SELECT o.customer_id, COUNT(*) AS cnt "
            "FROM {{ source('raw_demo', 'orders') }} AS o "
            "INNER JOIN {{ source('raw_demo', 'customers') }} AS c ON o.customer_id = c.customer_id "
            "GROUP BY o.customer_id"
        ),
        (
            "SELECT TRIM(CAST(order_id AS VARCHAR)) AS order_id, "
            "NULLIF(TRIM(status), '') AS status "
            "FROM {{ source('raw_demo', 'orders') }}"
        ),
    ),
    (
        "MOD_004",
        "sql",
        "models/core/orders_clean.sql",
        "{{ config(materialized='table') }}\nSELECT order_id FROM {{ ref('stg_demo__orders') }}",
        "models/core/fct_orders.sql::__OVERRIDE_PATH__::{{ config(materialized='table') }}\nSELECT order_id FROM {{ ref('stg_demo__orders') }}",
    ),
    (
        "MOD_005",
        "sql",
        "models/core/fct_orders.sql",
        (
            "SELECT customer_id FROM ("
            "SELECT customer_id FROM ("
            "SELECT customer_id FROM ("
            "SELECT customer_id FROM {{ ref('stg_demo__orders') }}"
            ") s1) s2) s3"
        ),
        (
            "WITH base_orders AS (SELECT customer_id FROM {{ ref('stg_demo__orders') }}) "
            "SELECT customer_id FROM base_orders"
        ),
    ),
    (
        "MOD_006",
        "sql",
        "models/staging/stg_demo__merchants.sql",
        "SELECT CAST(postal_code AS BIGINT) AS postal_code, TRIM(name) AS merchant_name FROM {{ source('raw_demo', 'merchants') }}",
        "SELECT LPAD(TRIM(CAST(postal_code AS VARCHAR)), 8, '0') AS postal_code FROM {{ source('raw_demo', 'merchants') }}",
    ),
    # --- QUALITY_CONTRACTS (6) ---
    (
        "QUAL_001",
        "yaml",
        "models/core/_models.yml",
        (
            "models:\n"
            "  - name: fct_orders\n"
            "    description: Orders fact table.\n"
            "    columns:\n"
            "      - name: order_id\n"
            "        description: Order key.\n"
        ),
        (
            "models:\n"
            "  - name: fct_orders\n"
            "    description: Orders fact table.\n"
            "    config:\n"
            "      contract:\n"
            "        enforced: true\n"
            "    columns:\n"
            "      - name: order_id\n"
            "        description: Order key.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
        ),
    ),
    (
        "QUAL_002",
        "yaml",
        "models/core/_models.yml",
        (
            "models:\n"
            "  - name: dim_products\n"
            "    columns:\n"
            "      - name: product_id\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
        ),
        (
            "models:\n"
            "  - name: dim_products\n"
            "    description: Product catalog dimension.\n"
            "    config:\n"
            "      contract:\n"
            "        enforced: true\n"
            "    columns:\n"
            "      - name: product_id\n"
            "        description: Unique product identifier.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
        ),
    ),
    (
        "QUAL_003",
        "yaml",
        "models/marts/_models.yml",
        (
            "models:\n"
            "  - name: mart_revenue_daily\n"
            "    description: Daily revenue mart.\n"
            "    columns:\n"
            "      - name: revenue_id\n"
            "        description: Primary key.\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
        ),
        (
            "models:\n"
            "  - name: mart_revenue_daily\n"
            "    description: Daily revenue mart.\n"
            "    config:\n"
            "      contract:\n"
            "        enforced: true\n"
            "    columns:\n"
            "      - name: revenue_id\n"
            "        description: Primary key.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
        ),
    ),
    (
        "QUAL_004",
        "sql",
        "models/staging/stg_demo__customers.sql",
        "SELECT customer_id, country_code FROM {{ source('raw_demo', 'customers') }}",
        "SELECT customer_id, NULLIF(TRIM(country_code), 'N/A') AS country_code FROM {{ source('raw_demo', 'customers') }}",
    ),
    (
        "QUAL_005",
        "sql",
        "models/core/fct_orders.sql",
        "SELECT order_id, discount_usd / gross_amount_usd AS discount_rate FROM {{ ref('stg_demo__orders') }}",
        "SELECT order_id, discount_usd / NULLIF(gross_amount_usd, 0) AS discount_rate FROM {{ ref('stg_demo__orders') }}",
    ),
    (
        "QUAL_006",
        "yaml",
        "models/core/_models.yml",
        (
            "models:\n"
            "  - name: fct_orders\n"
            "    description: Orders fact table.\n"
            "    config:\n"
            "      contract:\n"
            "        enforced: true\n"
            "    columns:\n"
            "      - name: order_id\n"
            "        description: Order key.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
            "      - name: customer_id\n"
            "        description: Foreign key.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - not_null\n"
        ),
        (
            "models:\n"
            "  - name: fct_orders\n"
            "    description: Orders fact table.\n"
            "    config:\n"
            "      contract:\n"
            "        enforced: true\n"
            "      meta:\n"
            "        lgpd_tier: PSEUDONYMIZED_PII\n"
            "    columns:\n"
            "      - name: order_id\n"
            "        description: Order key.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
            "      - name: customer_id\n"
            "        description: Foreign key.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - not_null\n"
            "          - relationships:\n"
            "              to: ref('dim_customers')\n"
            "              field: customer_id\n"
        ),
    ),
    # --- LGPD_PII_SECURITY (6) ---
    (
        "LGPD_001",
        "sql",
        "models/core/dim_customers.sql",
        "SELECT customer_id, cpf, email FROM {{ ref('stg_demo__customers') }}",
        (
            "SELECT customer_id, "
            "{{ mask_lgpd_pii('cpf', mode='cpf') }} AS cpf_masked, "
            "{{ mask_lgpd_pii('email', mode='email') }} AS email_masked "
            "FROM {{ ref('stg_demo__customers') }}"
        ),
    ),
    (
        "LGPD_002",
        "sql",
        "models/core/fct_lead_conversions.sql",
        (
            "SELECT c.customer_id, COUNT(l.lead_id) AS lead_cnt "
            "FROM {{ ref('stg_demo__customers') }} AS c "
            "INNER JOIN {{ ref('stg_demo__leads') }} AS l ON c.email = l.email "
            "GROUP BY c.customer_id"
        ),
        (
            "SELECT c.customer_surrogate_key, COUNT(l.lead_id) AS lead_cnt "
            "FROM {{ ref('stg_demo__customers') }} AS c "
            "INNER JOIN {{ ref('stg_demo__leads') }} AS l "
            "ON c.customer_surrogate_key = l.customer_surrogate_key "
            "GROUP BY c.customer_surrogate_key"
        ),
    ),
    (
        "LGPD_003",
        "yaml",
        "models/core/_models.yml",
        (
            "models:\n"
            "  - name: dim_customers\n"
            "    description: Customer dimension.\n"
            "    config:\n"
            "      contract:\n"
            "        enforced: true\n"
            "    columns:\n"
            "      - name: customer_id\n"
            "        description: Customer surrogate key.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
        ),
        (
            "models:\n"
            "  - name: dim_customers\n"
            "    description: Customer dimension.\n"
            "    config:\n"
            "      contract:\n"
            "        enforced: true\n"
            "      meta:\n"
            "        lgpd_tier: PSEUDONYMIZED_PII\n"
            "    columns:\n"
            "      - name: customer_id\n"
            "        description: Customer surrogate key.\n"
            "        data_type: varchar\n"
            "        data_tests:\n"
            "          - unique\n"
            "          - not_null\n"
        ),
    ),
    (
        "LGPD_004",
        "sql",
        "scratch_secret.sql",
        "CREATE SECRET ext_storage (TYPE S3, KEY_ID 'example_key_id', SECRET 'example_literal_secret');",
        "SELECT order_id FROM {{ ref('stg_demo__orders') }}",
    ),
    (
        "LGPD_005",
        "sql",
        "models/core/fct_orders.sql",
        "EXECUTE IMMEDIATE 'DELETE FROM analytics.audit_log WHERE actor = ' || '{{ var(\"actor\") }}';",
        "SELECT order_id FROM {{ ref('stg_demo__orders') }} WHERE actor_hash = {{ adapter.quote(var('actor_hash')) }}",
    ),
    (
        "LGPD_006",
        "sql",
        "models/marts/mart_customer_contacts.sql",
        "SELECT customer_id, full_name, email, cpf FROM {{ ref('dim_customers') }}",
        (
            "SELECT customer_segment, COUNT(DISTINCT customer_surrogate_key) AS active_customers "
            "FROM {{ ref('dim_customers') }} GROUP BY customer_segment"
        ),
    ),
]


def test_all_25_catalog_rules_are_covered_by_tests() -> None:
    """Ensure test suite exercises every single rule defined in governance_rules.yaml."""
    tested_ids = {case[0] for case in POSITIVE_AND_NEGATIVE_CASES}
    catalog_ids = set(ENGINE.rules.keys())
    assert tested_ids == catalog_ids
    assert len(tested_ids) == 25


@pytest.mark.parametrize(
    ("rule_id", "kind", "file_path", "bad_input", "good_input"),
    POSITIVE_AND_NEGATIVE_CASES,
    ids=[case[0] for case in POSITIVE_AND_NEGATIVE_CASES],
)
def test_rule_positive_and_negative(
    rule_id: str,
    kind: str,
    file_path: str,
    bad_input: str,
    good_input: str,
) -> None:
    """Each of the 25 rules fires on bad input and stays silent on good input."""
    good_path = file_path
    clean_good_input = good_input
    if "::OVERRIDE_PATH::" in good_input or "__OVERRIDE_PATH__" in good_input:
        parts = good_input.split("::__OVERRIDE_PATH__::", 1)
        good_path = parts[0]
        clean_good_input = parts[1]

    if kind == "sql":
        bad_findings = ENGINE.audit_sql(bad_input, dialect="duckdb", file_path=file_path)
        good_findings = ENGINE.audit_sql(clean_good_input, dialect="duckdb", file_path=good_path)
    else:
        bad_findings = ENGINE.audit_yaml(bad_input, file_path=file_path)
        good_findings = ENGINE.audit_yaml(clean_good_input, file_path=good_path)

    bad_ids = {f.rule_id for f in bad_findings}
    good_ids = {f.rule_id for f in good_findings}

    assert rule_id in bad_ids, f"Expected {rule_id} to trigger on bad input; got {bad_ids}"
    assert rule_id not in good_ids, f"Did not expect {rule_id} on good input; got {good_ids}"


def test_known_false_positive_guardrails() -> None:
    """Verify documented false-positive exclusions do not emit spurious violations."""
    # COUNT(*) must not trigger PERF_001; non-zero literal division must not trigger QUAL_005
    sql_agg = (
        "SELECT customer_segment, COUNT(*) AS total_rows, SUM(discount_usd) / 100.0 AS pct "
        "FROM {{ ref('dim_customers') }} GROUP BY customer_segment"
    )
    ids_agg = {f.rule_id for f in ENGINE.audit_sql(sql_agg, file_path="models/marts/mart_seg.sql")}
    assert "PERF_001" not in ids_agg
    assert "QUAL_005" not in ids_agg

    # Snapshot materialized='table' fct_ model must not trigger PERF_003
    sql_snapshot = (
        "{{ config(materialized='table') }}\n"
        "SELECT order_id, order_total_usd FROM {{ ref('stg_demo__orders') }}"
    )
    ids_snap = {f.rule_id for f in ENGINE.audit_sql(sql_snapshot, file_path="models/core/fct_small.sql")}
    assert "PERF_003" not in ids_snap

    # COUNT(DISTINCT customer_id) must not trigger PERF_007
    sql_cnt_dist = "SELECT COUNT(DISTINCT customer_id) AS uniq_customers FROM {{ ref('dim_customers') }}"
    ids_dist = {f.rule_id for f in ENGINE.audit_sql(sql_cnt_dist, file_path="models/marts/mart_kpi.sql")}
    assert "PERF_007" not in ids_dist

    # env_var in YAML must not trigger LGPD_004
    yaml_env = 'profiles:\n  prod:\n    password: "{{ env_var(\'WAREHOUSE_PASSWORD\') }}"\n'
    ids_yaml = {f.rule_id for f in ENGINE.audit_yaml(yaml_env, file_path="profiles_example.yml")}
    assert "LGPD_004" not in ids_yaml
