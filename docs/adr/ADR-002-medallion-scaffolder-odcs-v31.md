# ADR-002: Automated Medallion Scaffolder, ODCS v3.1 Contracts & Client Path Shield

- **Status:** Accepted
- **Date:** 2026-11-22
- **Governance & Standards:** `Medallion Architecture (Staging -> Core -> Marts)`, `ODCS v3.1`, `dbt Model Contracts`, `POP_T_070`, `POP_T_074`, `POP_T_154`, `POP_T_175`, `OWASP LLM01`

## Context

Analytics engineering deliveries repeatedly spend days writing boilerplate `source.yml` definitions, `stg_*` type-casting/trimming/sentinel-cleaning SQL, `dim_*/fct_*` schemas, `_models.yml` documentation, schema tests, dbt unit tests, and data contracts. Without an automated, opinionated generator, projects ship with partial column documentation, missing primary-key assertions, numeric corruption of leading-zero identifiers (`cnpj`, `cpf`, `cep`, `id_municipio`), and inconsistent contract enforcement.

Additionally, using an open-source governance tool across both public portfolio examples and confidential client Discovery/Delivery work introduces severe IP-leakage and security risks if client outputs or credentials can be written inside the public repository tree or exposed unsanitized to LLM agents.

## Decision

1. **Automated Medallion Scaffolder:** From Parquet files, CSV datasets, DuckDB schemas, or SQL DDL inputs, the scaffolder generates a complete dbt Medallion hierarchy:
   - `staging`: `sources.yml` and `stg_<source>_<table>.sql` applying explicit type casts, `TRIM()`, sentinel-to-`NULL` normalization (`''`, `'-1'`, `'999'`, `'N/A'`), and canonical `STRING` key preservation.
   - `core` & `marts`: `dim_*` / `fct_*` skeletons with `_models.yml` enforcing `contract: {enforced: true}`, `unique`/`not_null`/`accepted_values`/`relationships` schema tests, 100% model and column documentation (`lint_dbt_docs.py` compatible), and dbt native `unit_tests` YAML skeletons.
2. **Open Data Contract Standard (`ODCS v3.1`):** Each scaffolded dataset emits a declarative `contract.yaml` aligned with `dataContractSpecification: 3.1.0` (`POP_T_070`) and the 5 Pillars of Data Observability (`POP_T_074`: freshness, volume, schema, distribution/nulls, lineage).
3. **Path Traversal & Client Path Shield (`POP_T_154`):**
   - The scaffolder writes **only** to an explicitly supplied output directory and strictly rejects path traversal (`..`), symlink escapes, or writes outside the designated target root.
   - The auditor enforces **Client Path Shield**: when auditing external/client directories, it refuses to persist reports inside the public `dbt-dataops-governance-engine` repository tree.
4. **LLM & MCP Output Containment (`OWASP LLM01` / `POP_T_175`):** All MCP server tool responses wrapping inspected SQL, table names, or schema strings enclose external content inside `<untrusted_data>` delimiters to mitigate indirect prompt injection.

## Consequences

- Reduces initial Medallion pipeline bootstrap effort from multi-week manual setup to standardized, CI-verifiable templates ready for `dbt build` on DuckDB.
- Guarantees zero client SQL, schemas, or audit artifacts ever enter the public repository while keeping the engine immediately usable on confidential client engagements in isolated directories.
