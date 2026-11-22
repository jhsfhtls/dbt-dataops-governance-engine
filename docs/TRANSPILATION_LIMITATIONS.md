# Multi-Cloud Transpilation Matrix & Incremental Strategy Defaults

> **Scope:** Cross-engine SQL/dbt transpilation via `sqlglot` AST (`DuckDB ↔ Spark SQL / Databricks ↔ Snowflake`, plus `BigQuery` read/target support) and automated `full-refresh → incremental` optimization advisories.

---

## 1. Dialect Compatibility Matrix

| Source / Target | DuckDB (`duckdb`) | Spark SQL / Databricks (`spark` / `databricks`) | Snowflake (`snowflake`) | BigQuery (`bigquery`) |
| :--- | :---: | :---: | :---: | :---: |
| **DuckDB** | Native | Bidirectional round-trip | Bidirectional round-trip | Read + forward transpile |
| **Spark SQL / Databricks** | Bidirectional round-trip | Native | Bidirectional round-trip | Read + forward transpile |
| **Snowflake** | Bidirectional round-trip | Bidirectional round-trip | Native | Read + forward transpile |
| **BigQuery** | Forward transpile | Forward transpile | Forward transpile | Native |

### Preserved dbt Jinja Constructs
- `{{ config(...) }}` headers (preserved intact above transpiled SQL)
- `{{ ref(...) }}` and `{{ source(...) }}` lineage references
- `{{ this }}` incremental self-references
- `{{ mask_lgpd_pii(...) }}` and `{{ generate_surrogate_key_strict(...) }}` macro calls

*Complex control flow (`{% for ... %}`, dynamic macro loops) requires dbt compile-time expansion (`target/compiled/`) prior to transpilation.*

---

## 2. Known Limitations & Workarounds

| Code | Feature | Severity | Behavior Across Engines | Recommended Workaround |
| :--- | :--- | :---: | :--- | :--- |
| `LIM_QUALIFY` | `QUALIFY` clause | `MEDIUM` | Rewritten into an inline `ROW_NUMBER()` subquery (`_w = 1`) on older Spark SQL engines without native `QUALIFY`. | Inspect generated subquery aliases or materialize deduplication in a named CTE. |
| `LIM_SPARK_CAST_ANSI` | `CAST` vs `TRY_CAST` & Zero Division | `MEDIUM` | Spark non-ANSI `CAST` returns `NULL` on bad inputs (`TRY_CAST` on DuckDB/Snowflake), and Spark division returns `NULL` on `0`, prompting `sqlglot` to emit `NULLIF(denom, 0)` on DuckDB/Snowflake. | Use `TRY_CAST` and `NULLIF(denominator, 0)` explicitly whenever cross-warehouse consistency is required. |
| `LIM_SEMI_STRUCTURED` | `VARIANT`, `FLATTEN`, `EXPLODE`, `UNNEST` | `HIGH` | Semi-structured traversal (`payload:key::string`, `LATERAL FLATTEN`, `EXPLODE`, `UNNEST`) relies on engine-specific runtime types. | Isolate JSON/array flattening inside Bronze/Staging adapters per warehouse. |
| `LIM_ILIKE` | Case-insensitive `ILIKE` | `LOW` | Engines without native `ILIKE` rewrite predicates into `LOWER(col) LIKE LOWER(...)`. | Normalize casing once in Staging via `LOWER(TRIM(col))` for sargable downstream filters. |
| `LIM_MERGE_SEMANTICS` | Raw `MERGE` DDL | `HIGH` | Vendor `MERGE` extensions (`WHEN NOT MATCHED BY SOURCE`) vary across Delta Lake, Snowflake, and DuckDB. | Rely on dbt `incremental_strategy='merge'` or `'delete+insert'` instead of hand-written `MERGE`. |

---

## 3. Incremental Strategy Defaults

| Target Dialect | Default Strategy | Default `on_schema_change` | Lookback Watermark Pattern |
| :--- | :---: | :---: | :--- |
| `duckdb` | `delete+insert` | `append_new_columns` | `COALESCE(MAX(wm), TIMESTAMP '1970-01-01 00:00:00') - INTERVAL 'N days'` |
| `snowflake` | `merge` | `append_new_columns` | `DATEADD('day', -N, COALESCE(MAX(wm), TO_TIMESTAMP('1970-01-01 00:00:00')))` |
| `spark` / `databricks` | `merge` | `append_new_columns` | `COALESCE(MAX(wm), TIMESTAMP '1970-01-01 00:00:00') - INTERVAL N DAYS` |
| `bigquery` | `merge` | `append_new_columns` | `TIMESTAMP_SUB(COALESCE(MAX(wm), TIMESTAMP '1970-01-01 00:00:00'), INTERVAL N DAY)` |
