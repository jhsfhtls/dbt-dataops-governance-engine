"""FastAPI REST API (/api/v1/*) exposing audit, scaffold, transpile, lineage, and rules."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from dbt_dataops_governance import __version__
from dbt_dataops_governance.auditor import ClientPathShieldError
from dbt_dataops_governance.scaffolder import ScaffoldPathError
from dbt_dataops_governance.sdk import DbtGovernance


class AuditRequest(BaseModel):
    """Request payload for static AST audit via file path or inline SQL."""

    target_path: str | None = Field(default=None, description="File or directory path to audit.")
    sql: str | None = Field(default=None, description="Inline SQL/dbt string to audit.")
    file_path: str = Field(default="inline.sql", description="Logical file path label for inline SQL.")
    dialect: str = Field(default="duckdb", description="SQL dialect.")
    output_path: str | None = Field(default=None, description="Optional output report path.")
    output_format: str = Field(default="json", description="Report format (json or markdown).")


class ScaffoldRequest(BaseModel):
    """Request payload for automated Medallion scaffolding and ODCS v3.1 contract generation."""

    input_source: str = Field(description="Path to Parquet/CSV/DuckDB or CREATE TABLE DDL.")
    output_dir: str = Field(description="Explicit output directory.")
    source_type: str | None = Field(default=None, description="parquet, csv, duckdb, or ddl.")
    project_name: str = Field(default="scaffolded_lakehouse")
    source_name: str | None = None
    table_name: str | None = None
    dialect: str = Field(default="duckdb")
    entity_kind: str | None = None


class TranspileRequest(BaseModel):
    """Request payload for multi-cloud SQL/dbt AST transpilation."""

    sql: str
    source_dialect: str
    target_dialect: str
    preserve_dbt_jinja: bool = True
    check_roundtrip: bool = False


class LineageRequest(BaseModel):
    """Request payload for static dbt/SQL lineage extraction."""

    target_path: str


def create_app(governance: DbtGovernance | None = None) -> FastAPI:
    """Create and configure the FastAPI governance application."""
    gov = governance or DbtGovernance()
    app = FastAPI(
        title="dbt-dataops-governance-engine API",
        version=__version__,
        description="Static SQL/dbt AST auditor, Medallion scaffolder, ODCS v3.1 & transpiler REST API.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/rules")
    def list_rules(
        family: str | None = Query(default=None),
        severity: str | None = Query(default=None),
        dialect: str | None = Query(default=None),
    ) -> dict[str, Any]:
        rules = gov.list_rules(family=family, severity=severity, dialect=dialect)
        return {"total": len(rules), "rules": rules}

    @app.post("/api/v1/audit")
    def run_audit(payload: AuditRequest) -> dict[str, Any]:
        if not payload.target_path and not payload.sql:
            raise HTTPException(status_code=422, detail="Either 'target_path' or 'sql' must be provided.")
        try:
            if payload.target_path:
                return gov.audit(
                    payload.target_path,
                    dialect=payload.dialect,
                    output_path=payload.output_path,
                    output_format=payload.output_format,
                )
            return gov.audit_sql(
                payload.sql or "",
                dialect=payload.dialect,
                file_path=payload.file_path,
            )
        except ClientPathShieldError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/scaffold")
    def run_scaffold(payload: ScaffoldRequest) -> dict[str, Any]:
        try:
            return gov.scaffold(
                payload.input_source,
                output_dir=payload.output_dir,
                source_type=payload.source_type,
                project_name=payload.project_name,
                source_name=payload.source_name,
                table_name=payload.table_name,
                dialect=payload.dialect,
                entity_kind=payload.entity_kind,
            )
        except ScaffoldPathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/transpile")
    def run_transpile(payload: TranspileRequest) -> dict[str, Any]:
        try:
            return gov.transpile(
                payload.sql,
                source_dialect=payload.source_dialect,
                target_dialect=payload.target_dialect,
                preserve_dbt_jinja=payload.preserve_dbt_jinja,
                check_roundtrip=payload.check_roundtrip,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/lineage")
    def run_lineage(payload: LineageRequest) -> dict[str, Any]:
        try:
            return gov.lineage(payload.target_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app
