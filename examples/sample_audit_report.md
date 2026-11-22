# dbt DataOps Governance Audit Report

## Executive Scorecard

- **Target Audited:** `examples/legacy_sql_sample.sql`
- **SQL Dialect:** `duckdb`
- **Files Audited:** `1`
- **Governance Score:** **50.0 / 100.0** (Grade **F**)
- **FinOps Risk Level:** `CRITICAL`
- **LGPD / Security Risk Level:** `CRITICAL`
- **Total Findings:** **6**

### Severity Breakdown

| Severity | Count |
| :--- | :---: |
| `CRITICAL` | 2 |
| `HIGH` | 1 |
| `MEDIUM` | 3 |
| `LOW` | 0 |

### Family Breakdown

| Family | Count |
| :--- | :---: |
| `PERFORMANCE_FINOPS` | 4 |
| `MODELING_MEDALLION` | 0 |
| `QUALITY_CONTRACTS` | 1 |
| `LGPD_PII_SECURITY` | 1 |

## Findings

| Rule ID | Severity | File | Line | Message | Remediation |
| :--- | :---: | :--- | :---: | :--- | :--- |
| `PERF_001` | `HIGH` | `examples/legacy_sql_sample.sql` | 2 | Avoid SELECT * in core/mart or final models; enumerate explicit columns. | Enumerate all required columns explicitly in the `SELECT` projection list and pair them with typed casts and documentation. |
| `PERF_007` | `MEDIUM` | `examples/legacy_sql_sample.sql` | 2 | SELECT DISTINCT or UNION (without ALL) triggers full deduplication shuffles. | Deduplicate upstream relations via `QUALIFY ROW_NUMBER() OVER (...) = 1`, fix join keys to avoid fan-out, and replace `UNION` with `UNION ALL` for disjoint branches. |
| `QUAL_005` | `MEDIUM` | `examples/legacy_sql_sample.sql` | 4 | Unprotected division 'o.discount_usd / o.gross_amount_usd' lacks NULLIF(denominator, 0). | Wrap dynamic denominator expressions with `NULLIF(denominator, 0)` (or `SAFE_DIVIDE` in BigQuery). |
| `LGPD_001` | `CRITICAL` | `examples/legacy_sql_sample.sql` | 5 | Unmasked PII column(s) projected without masking macro: cpf, email. | Wrap PII columns in a portable masking macro such as `{{ mask_lgpd_pii('email', mode='email') }}` or replace with a salted surrogate hash. |
| `PERF_002` | `CRITICAL` | `examples/legacy_sql_sample.sql` | 8 | CROSS JOIN detected; verify explicit join predicate or pre-aggregate. | Add deterministic equality/range join predicates inside an explicit `ON` or `USING` clause, or pre-aggregate to a matching grain before joining. |
| `PERF_004` | `MEDIUM` | `examples/legacy_sql_sample.sql` | 9 | Non-sargable expression 'EXTRACT(YEAR FROM o.order_date)' wraps a column in a filter predicate. | Rewrite predicates as range comparisons (`created_at >= '2026-01-01' AND created_at < '2027-01-01'`) or normalize the column once in staging. |
