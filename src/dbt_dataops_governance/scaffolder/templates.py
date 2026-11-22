"""Deterministic template renderers for dbt Medallion layers and ODCS v3.1 contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dbt_dataops_governance.scaffolder.models import ColumnSpec, TableSpec


def _sample_value(col: ColumnSpec) -> Any:
    """Return a deterministic synthetic value matching the column contract type."""
    if col.accepted_values:
        return col.accepted_values[0]
    if col.is_canonical_string_key:
        return "01310100"
    if col.data_type == "bigint":
        return 1
    if col.data_type == "double":
        return 125.5
    if col.data_type == "boolean":
        return True
    if col.data_type == "date":
        return "2026-11-22"
    if col.data_type == "timestamp":
        return "2026-11-22 12:00:00"
    return f"{col.name}_sample"


def _staging_column_expr(col: ColumnSpec) -> str:
    """Build staging SQL expression with explicit cast, trim, and sentinel cleanup."""
    name = col.name
    if col.data_type == "varchar":
        return (
            f"    NULLIF(NULLIF(NULLIF(TRIM(CAST({name} AS VARCHAR)), ''), 'N/A'), '-1') "
            f"AS {name}"
        )

    cleaned_str = f"NULLIF(NULLIF(TRIM(CAST({name} AS VARCHAR)), ''), 'N/A')"
    cast_expr = f"TRY_CAST({cleaned_str} AS {col.data_type.upper()})"
    if col.data_type == "bigint" and not col.is_primary_key:
        return f"    CASE WHEN {cast_expr} IN (-1, 999) THEN NULL ELSE {cast_expr} END AS {name}"
    return f"    {cast_expr} AS {name}"


def render_dbt_project_yml(project_name: str) -> str:
    """Render dbt_project.yml configured for staging -> core Medallion materializations."""
    payload = {
        "name": project_name,
        "version": "1.0.0",
        "config-version": 2,
        "profile": project_name,
        "model-paths": ["models"],
        "test-paths": ["tests"],
        "models": {
            project_name: {
                "staging": {"+materialized": "view"},
                "core": {"+materialized": "table"},
            }
        },
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def render_profiles_yml(project_name: str, spec: TableSpec, output_dir: Path | None = None) -> str:
    """Render profiles.yml for local DuckDB execution."""
    if spec.source_duckdb_path:
        db_path = spec.source_duckdb_path
    elif output_dir is not None:
        db_path = (output_dir.resolve() / "target" / f"{project_name}.duckdb").as_posix()
    else:
        db_path = f"target/{project_name}.duckdb"
    payload = {
        project_name: {
            "target": "dev",
            "outputs": {
                "dev": {
                    "type": "duckdb",
                    "path": db_path,
                    "threads": 4,
                }
            },
        }
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def render_sources_yml(spec: TableSpec) -> str:
    """Render models/staging/sources.yml with 100% column documentation."""
    table_entry: dict[str, Any] = {
        "name": spec.table_name,
        "description": spec.description or f"Raw source table {spec.table_name}.",
        "columns": [
            {"name": col.name, "description": col.description}
            for col in spec.columns
        ],
    }
    if spec.external_location:
        table_entry["meta"] = {"external_location": spec.external_location}

    source_entry: dict[str, Any] = {
        "name": spec.source_name,
        "description": f"Source system {spec.source_name}.",
        "schema": "main",
        "tables": [table_entry],
    }
    payload = {"version": 2, "sources": [source_entry]}
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def render_staging_sql(spec: TableSpec) -> str:
    """Render models/staging/stg_<source>__<table>.sql (1:1 standardization)."""
    expressions = ",\n".join(_staging_column_expr(col) for col in spec.columns)
    return (
        f"-- Standardized staging model for {spec.source_name}.{spec.table_name}\n"
        "SELECT\n"
        f"{expressions}\n"
        f"FROM {{{{ source('{spec.source_name}', '{spec.table_name}') }}}}\n"
    )


def render_staging_models_yml(spec: TableSpec, stg_name: str) -> str:
    """Render models/staging/_models.yml with 100% documentation and PK tests."""
    cols: list[dict[str, Any]] = []
    for col in spec.columns:
        entry: dict[str, Any] = {"name": col.name, "description": col.description}
        if col.is_primary_key:
            entry["data_tests"] = ["unique", "not_null"]
        cols.append(entry)

    payload = {
        "version": 2,
        "models": [
            {
                "name": stg_name,
                "description": f"Standardized 1:1 staging model for {spec.source_name}.{spec.table_name}.",
                "columns": cols,
            }
        ],
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def render_core_sql(spec: TableSpec, stg_name: str) -> str:
    """Render models/core/<dim|fct>_<table>.sql with explicit typed projections."""
    projections = ",\n".join(
        f"    CAST({col.name} AS {col.data_type.upper()}) AS {col.name}"
        for col in spec.columns
    )
    return (
        "{{ config(materialized='table') }}\n\n"
        "SELECT\n"
        f"{projections}\n"
        f"FROM {{{{ ref('{stg_name}') }}}}\n"
    )


def render_core_models_yml(
    spec: TableSpec,
    stg_name: str,
    target_model_name: str,
    relationships: dict[str, tuple[str, str]] | None = None,
) -> str:
    """Render models/core/_models.yml with enforced contract, tests, and unit test."""
    rel_map = relationships or {}
    cols: list[dict[str, Any]] = []
    sample_row: dict[str, Any] = {}

    for col in spec.columns:
        sample_row[col.name] = _sample_value(col)
        col_entry: dict[str, Any] = {
            "name": col.name,
            "description": col.description,
            "data_type": col.data_type,
        }
        tests: list[Any] = []
        if col.is_primary_key:
            tests.extend(["unique", "not_null"])
        elif not col.nullable:
            tests.append("not_null")
        if col.accepted_values:
            tests.append({"accepted_values": {"values": list(col.accepted_values)}})
        if col.name in rel_map:
            target_ref, target_field = rel_map[col.name]
            tests.append({"relationships": {"to": f"ref('{target_ref}')", "field": target_field}})
        if tests:
            col_entry["data_tests"] = tests
        cols.append(col_entry)

    payload = {
        "version": 2,
        "models": [
            {
                "name": target_model_name,
                "description": f"Contract-enforced Medallion {spec.entity_kind} model for {spec.table_name}.",
                "config": {
                    "contract": {"enforced": True},
                    "meta": {"lgpd_tier": "PUBLIC_NON_PERSONAL"},
                },
                "columns": cols,
            }
        ],
        "unit_tests": [
            {
                "name": f"test_{target_model_name}_contract_smoke",
                "description": f"Synthetic dbt unit test validating {target_model_name} projection.",
                "model": target_model_name,
                "given": [
                    {
                        "input": f"ref('{stg_name}')",
                        "rows": [sample_row],
                    }
                ],
                "expect": {"rows": [dict(sample_row)]},
            }
        ],
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def render_odcs_contract_yaml(spec: TableSpec, target_model_name: str) -> str:
    """Render ODCS v3.1 (dataContractSpecification: 3.1.0) contract YAML."""
    pk_cols = [c.name for c in spec.columns if c.is_primary_key]
    fields_map: dict[str, Any] = {}
    for col in spec.columns:
        field_def: dict[str, Any] = {
            "type": "string" if col.data_type == "varchar" else col.data_type,
            "required": col.is_primary_key or not col.nullable,
            "unique": col.is_primary_key,
            "description": col.description,
        }
        if col.accepted_values:
            field_def["enum"] = list(col.accepted_values)
        fields_map[col.name] = field_def

    payload = {
        "dataContractSpecification": "3.1.0",
        "id": f"urn:datacontract:{spec.source_name}:{target_model_name}",
        "info": {
            "title": f"Data Contract for {target_model_name}",
            "version": "1.0.0",
            "status": "active",
            "description": f"ODCS v3.1 contract generated for Medallion model {target_model_name}.",
            "owner": "analytics-engineering",
        },
        "models": {
            target_model_name: {
                "type": "table",
                "description": spec.description,
                "primaryKey": pk_cols,
                "fields": fields_map,
            }
        },
        "servicelevels": {
            "freshness": {"threshold": "24h"},
            "quality": {
                "fivePillars": [
                    "freshness",
                    "volume",
                    "schema",
                    "distribution",
                    "lineage",
                ]
            },
        },
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
