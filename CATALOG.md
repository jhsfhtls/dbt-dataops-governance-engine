# Governance Rules & Portable Macros Catalog

> **Single Source of Truth (SSOT):** Deterministically rendered from [`catalog/governance_rules.yaml`](catalog/governance_rules.yaml) and [`catalog/macros_registry.yaml`](catalog/macros_registry.yaml). Do not edit manually.

- **Rules Schema Version:** `1.0.0` (Updated: `2026-11-22`)
- **Macros Schema Version:** `1.0.0` (Updated: `2026-11-22`)
- **Total Governance Rules:** **25** across **4** families
- **Severity Breakdown:** `CRITICAL`: **7** | `HIGH`: **7** | `MEDIUM`: **9** | `LOW`: **2**
- **Portable dbt Macros Registered:** **4**

---

## 1. Governance Families

| Family ID | Display Name | Rules | Focus |
| :--- | :--- | :---: | :--- |
| `PERFORMANCE_FINOPS` | Performance & FinOps | 7/7 | Detects query anti-patterns that inflate cloud warehouse compute spend, trigger full table scans, or break partition pruning. |
| `MODELING_MEDALLION` | Modeling & Medallion Architecture | 6/6 | Enforces staging-core-marts isolation, dbt lineage macros, canonical naming conventions, and leading-zero-safe string keys. |
| `QUALITY_CONTRACTS` | Data Quality & ODCS v3.1 Contracts | 6/6 | Enforces primary-key assertions, referential integrity, sentinel-to-NULL hygiene, 100% documentation, and enforced contracts. |
| `LGPD_PII_SECURITY` | LGPD, PII & SQL Security | 6/6 | Prevents unmasked PII exposure, secret leakage, unsafe SQL interpolation, and unanonymized Gold exports. |

---

## 2. Governance Rules Summary (25 Rules)

| Rule ID | Family | Severity | Rule Name | Dialects | Applies To |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `PERF_001` | `PERFORMANCE_FINOPS` | `HIGH` | Disallow SELECT * in core and mart final models | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `PERF_002` | `PERFORMANCE_FINOPS` | `CRITICAL` | Disallow JOIN without predicate or implicit Cartesian cross join | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `PERF_003` | `PERFORMANCE_FINOPS` | `HIGH` | Require incremental watermark filter on fact and incremental models | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_model` |
| `PERF_004` | `PERFORMANCE_FINOPS` | `MEDIUM` | Disallow non-sargable function calls on columns in WHERE or JOIN predicates | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `PERF_005` | `PERFORMANCE_FINOPS` | `HIGH` | Flag repeated correlated subqueries as candidates for CTE materialization | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `PERF_006` | `PERFORMANCE_FINOPS` | `MEDIUM` | Disallow ORDER BY without LIMIT inside CTEs, subqueries, or non-final models | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `PERF_007` | `PERFORMANCE_FINOPS` | `MEDIUM` | Flag SELECT DISTINCT or UNION masking join fan-out and triggering shuffles | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `MOD_001` | `MODELING_MEDALLION` | `CRITICAL` | Disallow hardcoded physical table references instead of dbt ref or source | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_model` |
| `MOD_002` | `MODELING_MEDALLION` | `HIGH` | Enforce Medallion isolation by disallowing source calls in core and marts | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_model` |
| `MOD_003` | `MODELING_MEDALLION` | `MEDIUM` | Disallow multi-table joins or business aggregations inside staging models | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_model` |
| `MOD_004` | `MODELING_MEDALLION` | `LOW` | Enforce canonical Medallion model naming prefixes | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_model` |
| `MOD_005` | `MODELING_MEDALLION` | `MEDIUM` | Disallow deeply nested subqueries in favor of modular CTEs | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `MOD_006` | `MODELING_MEDALLION` | `HIGH` | Disallow numeric coercion on canonical string identifier keys | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `QUAL_001` | `QUALITY_CONTRACTS` | `CRITICAL` | Require primary key unique and not_null tests on every dbt model | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_yaml` |
| `QUAL_002` | `QUALITY_CONTRACTS` | `MEDIUM` | Require 100 percent model and column documentation coverage | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_yaml` |
| `QUAL_003` | `QUALITY_CONTRACTS` | `HIGH` | Require enforced dbt model contracts or ODCS v3.1 contracts on public marts | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_yaml`, `odcs_contract` |
| `QUAL_004` | `QUALITY_CONTRACTS` | `MEDIUM` | Require explicit sentinel-to-NULL sanitization in staging models | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `QUAL_005` | `QUALITY_CONTRACTS` | `MEDIUM` | Require NULLIF zero-division protection on denominator expressions | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `QUAL_006` | `QUALITY_CONTRACTS` | `LOW` | Require relationships referential integrity test on foreign-key columns | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_yaml` |
| `LGPD_001` | `LGPD_PII_SECURITY` | `CRITICAL` | Disallow unmasked PII columns without a masking or hashing macro | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `LGPD_002` | `LGPD_PII_SECURITY` | `HIGH` | Disallow plaintext PII columns in JOIN or GROUP BY clauses | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `LGPD_003` | `LGPD_PII_SECURITY` | `MEDIUM` | Require meta.lgpd_tier classification on models handling personal attributes | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_yaml`, `odcs_contract` |
| `LGPD_004` | `LGPD_PII_SECURITY` | `CRITICAL` | Disallow hardcoded credentials, passwords, or API tokens in SQL or YAML | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model`, `dbt_yaml` |
| `LGPD_005` | `LGPD_PII_SECURITY` | `CRITICAL` | Disallow unsafe dynamic SQL or raw string interpolation susceptible to injection | `duckdb`, `snowflake`, `spark`, `bigquery` | `sql`, `dbt_model` |
| `LGPD_006` | `LGPD_PII_SECURITY` | `CRITICAL` | Disallow exporting unmasked PII into Gold marts without anonymization | `duckdb`, `snowflake`, `spark`, `bigquery` | `dbt_model` |

---

## 3. Rule Specifications & False-Positive Guardrails

### Performance & FinOps (`PERFORMANCE_FINOPS`)

#### `PERF_001` — Disallow SELECT * in core and mart final models (`HIGH`)

- **Rationale:** Wildcard column projections scan unnecessary columnar storage blocks in Snowflake/BigQuery/Parquet and silently break downstream schema contracts when upstream columns change.
- **Remediation:** Enumerate all required columns explicitly in the `SELECT` projection list and pair them with typed casts and documentation.
- **Known False Positives:**
  - Ephemeral staging passthroughs or `SELECT * EXCLUDE (...)` wrappers intentionally forwarding an explicit contract upstream.
  - Test fixture queries inside `tests/` asserting row counts (`COUNT(*)`).

#### `PERF_002` — Disallow JOIN without predicate or implicit Cartesian cross join (`CRITICAL`)

- **Rationale:** Unconstrained joins (comma joins without `WHERE` predicates, `JOIN ... ON TRUE`, or unintended `CROSS JOIN`) explode row cardinality quadratically, exhausting cluster memory and FinOps quotas.
- **Remediation:** Add deterministic equality/range join predicates inside an explicit `ON` or `USING` clause, or pre-aggregate to a matching grain before joining.
- **Known False Positives:**
  - Intentional small date-spine x dimension scaffolding when explicitly capped and documented with a rationale comment.

#### `PERF_003` — Require incremental watermark filter on fact and incremental models (`HIGH`)

- **Rationale:** Configuring `materialized='incremental'` or building large `fct_*` tables without an `{% if is_incremental() %}` watermark predicate forces full-table reprocessing on every scheduled run.
- **Remediation:** Add an `{% if is_incremental() %}` filter referencing `{{ this }}` with a bounded lookback window on the event/updated timestamp column.
- **Known False Positives:**
  - Small reference snapshot tables explicitly configured as `materialized='table'` with bounded row volume.

#### `PERF_004` — Disallow non-sargable function calls on columns in WHERE or JOIN predicates (`MEDIUM`)

- **Rationale:** Wrapping indexed or partitioned columns in scalar functions (such as `YEAR(created_at)`, `CAST(created_at AS DATE)`, or `LOWER(email)`) prevents micro-partition pruning and index pushdown.
- **Remediation:** Rewrite predicates as range comparisons (`created_at >= '2026-01-01' AND created_at < '2027-01-01'`) or normalize the column once in staging.
- **Known False Positives:**
  - Filters on low-cardinality staging attributes where upstream normalization has not yet materialized a canonical column.

#### `PERF_005` — Flag repeated correlated subqueries as candidates for CTE materialization (`HIGH`)

- **Rationale:** Multiple scalar or correlated subqueries in `SELECT` or `WHERE` force repeated scans of the same source table instead of a single pre-aggregated join or window pass.
- **Remediation:** Consolidate repeated subqueries into a pre-aggregated CTE joined once on the shared key, or replace with a window function.
- **Known False Positives:**
  - Single lightweight `EXISTS` semi-join over a small pre-filtered dimension table when the optimizer rewrites it as a hash semi-join.

#### `PERF_006` — Disallow ORDER BY without LIMIT inside CTEs, subqueries, or non-final models (`MEDIUM`)

- **Rationale:** Unbounded `ORDER BY` inside CTEs or dbt views triggers an expensive distributed global sort whose row ordering is discarded by downstream relational operators.
- **Remediation:** Remove `ORDER BY` from intermediate CTEs and views, or pair it with `LIMIT` / `QUALIFY ROW_NUMBER()` when selecting Top-N rows.
- **Known False Positives:**
  - `ORDER BY` inside `OVER (...)` window clauses or `ARRAY_AGG(... ORDER BY ...)` aggregate specifications.
  - Top-N CTEs that explicitly specify `LIMIT`.

#### `PERF_007` — Flag SELECT DISTINCT or UNION masking join fan-out and triggering shuffles (`MEDIUM`)

- **Rationale:** Broad `SELECT DISTINCT` or `UNION` (instead of `UNION ALL`) introduces full-dataset hash/sort deduplication overhead and frequently hides broken join granularity.
- **Remediation:** Deduplicate upstream relations via `QUALIFY ROW_NUMBER() OVER (...) = 1`, fix join keys to avoid fan-out, and replace `UNION` with `UNION ALL` for disjoint branches.
- **Known False Positives:**
  - Explicit single-column domain lookup tables derived from an un-deduplicated event stream when `GROUP BY` is unavailable.

### Modeling & Medallion Architecture (`MODELING_MEDALLION`)

#### `MOD_001` — Disallow hardcoded physical table references instead of dbt ref or source (`CRITICAL`)

- **Rationale:** Hardcoding `database.schema.table` bypasses dbt DAG dependency tracking, breaks Slim CI `state:modified+` selection, and couples code to a single environment.
- **Remediation:** Replace hardcoded table paths with `{{ source('source_name', 'table_name') }}` in staging and `{{ ref('model_name') }}` downstream.
- **Known False Positives:**
  - Standalone non-dbt legacy SQL migration scripts audited prior to dbt refactoring.

#### `MOD_002` — Enforce Medallion isolation by disallowing source calls in core and marts (`HIGH`)

- **Rationale:** Allowing `core` (`dim_*`, `fct_*`) or `marts` models to read `{{ source() }}` directly bypasses staging type normalization, sentinel cleanup, and PII masking gates.
- **Remediation:** Route every raw source through a dedicated `stg_*` model and reference that staging model via `{{ ref('stg_*') }}` in `core` and `marts`.
- **Known False Positives:**
  - Dedicated seed/reference lookup bridges explicitly placed under `models/staging/`.

#### `MOD_003` — Disallow multi-table joins or business aggregations inside staging models (`MEDIUM`)

- **Rationale:** Staging models (`stg_*`) should perform 1:1 source standardization (renaming, casting, trimming, sentinel NULLs); adding joins or `GROUP BY` obscures lineage and grain.
- **Remediation:** Keep `stg_*` strictly 1:1 with its source table and move joins or aggregations into `int_*`, `core`, or `marts` models.
- **Known False Positives:**
  - Single-source deduplication CTE using `ROW_NUMBER()` without collapsing business grain.

#### `MOD_004` — Enforce canonical Medallion model naming prefixes (`LOW`)

- **Rationale:** Consistent prefixes (`stg_`, `int_`, `dim_`, `fct_`, `mart_`) make layer boundaries, grain, and Slim CI impact self-evident to engineers and automated linters.
- **Remediation:** Rename model SQL files and YAML schema entries to start with `stg_`, `int_`, `dim_`, `fct_`, or `mart_` matching their layer folder.
- **Known False Positives:**
  - Snapshot models in `snapshots/` or ephemeral utilities explicitly scoped in `dbt_project.yml`.

#### `MOD_005` — Disallow deeply nested subqueries in favor of modular CTEs (`MEDIUM`)

- **Rationale:** Subqueries nested 3 or more levels deep degrade readability, hinder code review, and obscure intermediate transformation grains compared to named CTEs.
- **Remediation:** Flatten nested inline subqueries into sequential, single-purpose CTEs (`source_data`, `cleaned`, `final`).
- **Known False Positives:**
  - Automatically generated SQL emitted by BI tools prior to manual refactoring.

#### `MOD_006` — Disallow numeric coercion on canonical string identifier keys (`HIGH`)

- **Rationale:** Casting identifiers with leading zeros (`cnpj`, `cpf`, `cep`, `ibge`, `id_municipio`, `postal_code`, `zip_code`) to `INT`/`BIGINT`/`NUMBER` silently corrupts keys and breaks joins.
- **Remediation:** Cast canonical identifiers strictly to `VARCHAR`/`STRING`, apply `TRIM()`, and preserve zero-padded fixed widths with `LPAD()`.
- **Known False Positives:**
  - Explicit integer check-digit arithmetic performed inside a dedicated validation macro after preserving the canonical `VARCHAR` column.

### Data Quality & ODCS v3.1 Contracts (`QUALITY_CONTRACTS`)

#### `QUAL_001` — Require primary key unique and not_null tests on every dbt model (`CRITICAL`)

- **Rationale:** Without both `unique` and `not_null` schema assertions on the primary key, duplicate fan-out rows or null join keys silently inflate business metrics downstream.
- **Remediation:** Declare `unique` and `not_null` `data_tests` on the primary-key column (or composite uniqueness test at model level) in `_models.yml`.
- **Known False Positives:**
  - Composite-key models tested via `dbt_utils.unique_combination_of_columns` at model level instead of single-column `unique`.

#### `QUAL_002` — Require 100 percent model and column documentation coverage (`MEDIUM`)

- **Rationale:** Undocumented models and columns stall onboarding, prevent catalog discovery, and fail automated governance checks such as `lint_dbt_docs.py`.
- **Remediation:** Populate meaningful non-empty `description` fields for every model and every column in `_models.yml`.
- **Known False Positives:**
  - Temporary scratch models excluded from production manifests before PR review.

#### `QUAL_003` — Require enforced dbt model contracts or ODCS v3.1 contracts on public marts (`HIGH`)

- **Rationale:** Public `core` and `marts` tables consumed by BI, ML, or external APIs require `contract: {enforced: true}` and declared `data_type` constraints (or ODCS v3.1 specs) to fail fast on breaking schema drift.
- **Remediation:** Enable `config: {contract: {enforced: true}}` with explicit `data_type` on every column in `_models.yml` and maintain an accompanying ODCS v3.1 `contract.yaml`.
- **Known False Positives:**
  - Ephemeral internal intermediate models (`int_*`) not exposed to external consumers.

#### `QUAL_004` — Require explicit sentinel-to-NULL sanitization in staging models (`MEDIUM`)

- **Rationale:** Legacy extracts frequently encode missing values as `'-1'`, `'99'`, `'999'`, `'N/A'`, `'UNKNOWN'`, or `''`, skewing averages, `COUNT(col)` metrics, and ML features when not converted to `NULL`.
- **Remediation:** Normalize string whitespace with `TRIM()` and convert known sentinel literals to `NULL` via `NULLIF()` or `CASE WHEN ... THEN NULL`.
- **Known False Positives:**
  - Legitimate numeric quantities or category codes where `0` or `99` is a genuine domain value rather than a sentinel.

#### `QUAL_005` — Require NULLIF zero-division protection on denominator expressions (`MEDIUM`)

- **Rationale:** Unprotected division expressions (`numerator / denominator`) crash batch pipelines on DuckDB/Snowflake or emit silent `Infinity`/`NaN` values when zero counts appear.
- **Remediation:** Wrap dynamic denominator expressions with `NULLIF(denominator, 0)` (or `SAFE_DIVIDE` in BigQuery).
- **Known False Positives:**
  - Division by a strictly non-zero positive numeric literal constant (e.g., `/ 100.0`).

#### `QUAL_006` — Require relationships referential integrity test on foreign-key columns (`LOW`)

- **Rationale:** Fact models referencing dimension foreign keys (`*_id`, `*_sk`, `*_key`) without a `relationships` test allow orphan records that quietly drop rows in inner-join BI reports.
- **Remediation:** Add a dbt `relationships` test pointing `to: ref('dim_*')` and `field: <pk>` on foreign-key columns in `_models.yml`.
- **Known False Positives:**
  - Late-arriving dimension keys intentionally bridged to an explicit `'UNKNOWN'` sentinel surrogate row prior to reconciliation.

### LGPD, PII & SQL Security (`LGPD_PII_SECURITY`)

#### `LGPD_001` — Disallow unmasked PII columns without a masking or hashing macro (`CRITICAL`)

- **Rationale:** Projecting raw sensitive personal identifiers (`cpf`, `email`, `telefone`, `celular`, `rg`, `cnh`, `nome_completo`, `ssn`, `passport`) violates LGPD data minimization (Art. 6) and leaks PII into analytics layers.
- **Remediation:** Wrap PII columns in a portable masking macro such as `{{ mask_lgpd_pii('email', mode='email') }}` or replace with a salted surrogate hash.
- **Known False Positives:**
  - Restricted compliance quarantine tables where masking is applied downstream with documented `meta.lgpd_tier` access controls.

#### `LGPD_002` — Disallow plaintext PII columns in JOIN or GROUP BY clauses (`HIGH`)

- **Rationale:** Joining or grouping directly on raw `cpf`, `email`, or `telefone` propagates plaintext PII into query execution plans, logs, and downstream composite keys.
- **Remediation:** Join and group on an anonymized surrogate key (`{{ generate_surrogate_key_strict(['customer_id']) }}` or salted SHA-256 token) rather than plaintext PII.
- **Known False Positives:**
  - Staging deduplication when no anonymized surrogate key exists yet and the output immediately drops the raw PII column.

#### `LGPD_003` — Require meta.lgpd_tier classification on models handling personal attributes (`MEDIUM`)

- **Rationale:** Models processing customer, partner, or masked personal attributes require explicit `meta.lgpd_tier` metadata so governance catalogs and access-control policies remain auditable.
- **Remediation:** Add `meta: {lgpd_tier: ...}` (e.g., `ANONYMIZED_MICRODATA`, `PSEUDONYMIZED_PII`, `PUBLIC_NON_PERSONAL`) to the model YAML metadata block.
- **Known False Positives:**
  - Pure macroeconomic, calendar, or geographic aggregate dimensions without any personal entities.

#### `LGPD_004` — Disallow hardcoded credentials, passwords, or API tokens in SQL or YAML (`CRITICAL`)

- **Rationale:** Embedding passwords, storage keys, or bearer tokens in SQL/YAML files risks immediate credential exposure via Git history and CI logs.
- **Remediation:** Remove all literal credentials immediately and inject warehouse authentication exclusively via `env_var(...)` or secret managers.
- **Known False Positives:**
  - Environment-variable Jinja lookups such as `{{ env_var('WAREHOUSE_TOKEN') }}` with no literal secret value.

#### `LGPD_005` — Disallow unsafe dynamic SQL or raw string interpolation susceptible to injection (`CRITICAL`)

- **Rationale:** Unsanitized `EXECUTE IMMEDIATE` with concatenated strings or unvalidated Jinja SQL interpolation exposes analytics warehouses to SQL injection and unauthorized DDL/DML execution.
- **Remediation:** Eliminate dynamic string concatenation in SQL; use declarative dbt models, explicit allowlists, or `adapter.quote()` / bind parameters.
- **Known False Positives:**
  - Parameterized warehouse statements using explicit bind variables (`USING (...)`) or allowlisted dbt adapter quote helpers (`adapter.quote(...)`).

#### `LGPD_006` — Disallow exporting unmasked PII into Gold marts without anonymization (`CRITICAL`)

- **Rationale:** Models in `models/marts/` serve BI dashboards and external data products; exporting individual PII columns (`cpf`, `email`, `telefone`, `birth_date`, `full_address`) violates LGPD Art. 12/14 anonymization boundaries.
- **Remediation:** Aggregate marts to business cohorts (with k-anonymity thresholds where needed) or expose only irreversible hashes and masked fields (`*_masked`).
- **Known False Positives:**
  - Cohort-level aggregates (`COUNT(DISTINCT customer_surrogate_key)`) or models that expose only `*_masked` or hashed surrogate keys.

---

## 4. Portable Cross-Warehouse dbt Macros

| Macro | Category | Status | Supported Dialects | Signature | Description |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `mask_lgpd_pii` | `LGPD_PRIVACY` | `PLANNED` | `duckdb`, `snowflake`, `spark`, `bigquery` | `mask_lgpd_pii(column_name, mode='default')` | Applies deterministic LGPD-compliant masking for CPF, CNPJ, email, and phone attributes across supported SQL adapters. |
| `generate_surrogate_key_strict` | `MODELING_INTEGRITY` | `PLANNED` | `duckdb`, `snowflake`, `spark`, `bigquery` | `generate_surrogate_key_strict(field_list)` | Generates a deterministic SHA-256 surrogate key that preserves leading zeros and differentiates NULL values from empty strings. |
| `incremental_watermark_filter` | `PERFORMANCE_FINOPS` | `PLANNED` | `duckdb`, `snowflake`, `spark`, `bigquery` | `incremental_watermark_filter(watermark_column, lookback_days=3)` | Emits a portable incremental lookback predicate guarded by is_incremental() to prevent full-table scans on large fact models. |
| `audit_run_metadata` | `OBSERVABILITY_LINEAGE` | `PLANNED` | `duckdb`, `snowflake`, `spark`, `bigquery` | `audit_run_metadata()` | Injects standardized lineage and execution metadata columns (_dge_invocation_id, _dge_loaded_at_utc, _dge_model_name) into materialized tables. |

---

## 5. Synchronization & Verification

```bash
python scripts/validate_catalog.py
python scripts/render_catalog.py --check
python scripts/render_catalog.py
```
