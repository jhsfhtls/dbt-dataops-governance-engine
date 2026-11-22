# ADR-001: Static Multi-Dialect SQL/dbt AST Analysis via `sqlglot`

- **Status:** Accepted
- **Date:** 2026-11-22
- **Governance & Standards:** `sqlglot AST`, `Zero-Execution Static Analysis`, `POP_T_070`, `POP_T_074`, `POP_T_154`, `POP_T_175`

## Context

Legacy SQL repositories and dbt projects frequently accumulate FinOps waste (`SELECT *` in final layers, missing incremental/partition watermarks, non-sargable predicates, repeated correlated subqueries, Cartesian joins), modeling drift (layer bypasses, numeric casts destroying leading zeros on canonical keys), and LGPD/PII exposure before issues reach production.

Running SQL queries against a live cloud warehouse (Snowflake, Databricks, BigQuery) during Discovery audits or CI checks introduces four blockers: (1) warehouse compute cost, (2) credential management overhead, (3) SQL injection and side-effect risks on untrusted client SQL, and (4) fragile regex linters that break on nested CTEs, multi-line expressions, and dialect differences.

## Decision

1. **Zero-Execution Static AST Engine (`sqlglot`):** All SQL and dbt model audits parse expressions exclusively into Abstract Syntax Trees (ASTs) using `sqlglot`. The audit engine **never executes** audited SQL against any database or warehouse, eliminating warehouse credentials, compute charges, and runtime side effects during auditing.
2. **Multi-Dialect Support:** The engine supports four primary analytics dialects out of the box: `duckdb`, `snowflake`, `spark` (Databricks Spark SQL), and `bigquery`, enabling multi-cloud transpilation (`DuckDB <-> Spark SQL <-> Snowflake`) and `full-refresh -> incremental` optimization advisories (`merge` / `delete+insert`, `unique_key`, watermark filters).
3. **Deterministic dbt Jinja Pre-Processor:** Because raw dbt models contain Jinja tags (`{{ ref(...) }}`, `{{ source(...) }}`, `{{ config(...) }}`, `{% if is_incremental() %}`, and PII masking macros), a deterministic and reversible pre-processor extracts dbt metadata (layer, dependencies, materialization, incremental guards, macro calls) and substitutes Jinja constructs with syntactically valid SQL placeholders prior to `sqlglot` AST parsing.
4. **Declarative 25-Rule Governance Catalog (`catalog/governance_rules.yaml`):** Rules across `PERFORMANCE_FINOPS`, `MODELING_MEDALLION`, `QUALITY_CONTRACTS`, and `LGPD_PII_SECURITY` are cataloged declaratively with severity, target dialects, rationale, remediation guidance, synthetic good/bad examples, and explicit `known_false_positives` to ensure transparent, auditable scoring.

## Consequences

- Deterministic, sub-second SQL/dbt governance audits runnable offline in local environments, client Discovery engagements, and CI pipelines without warehouse credentials.
- Clean separation between static AST inspection (auditor) and optional sandbox execution on synthetic fixtures (DuckDB reference project and dbt builds).
- Known limitation: dynamic Jinja loops or complex custom adapter macros that alter query topology at compile time require fallback reporting or compiled-SQL mode (`target/compiled/`), documented transparently per rule.
