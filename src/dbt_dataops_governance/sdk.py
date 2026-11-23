"""Unified Python SDK facade (DbtGovernance) exposing all platform capabilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dbt_dataops_governance.auditor import AuditEngine
from dbt_dataops_governance.auditor.jinja_preprocessor import preprocess_dbt_sql
from dbt_dataops_governance.auditor.models import build_audit_summary
from dbt_dataops_governance.auditor.rules_sql import evaluate_sql_document
from dbt_dataops_governance.lineage import extract_lineage
from dbt_dataops_governance.scaffolder import MedallionScaffolder
from dbt_dataops_governance.transpiler import IncrementalOptimizer, MultiCloudTranspiler


class DbtGovernance:
    """Unified SDK facade backing CLI, FastAPI, and MCP interfaces identically."""

    def __init__(self, catalog_path: Path | None = None, repo_root: Path | None = None) -> None:
        self.auditor = AuditEngine(catalog_path=catalog_path, repo_root=repo_root)
        self.scaffolder = MedallionScaffolder()
        self.transpiler = MultiCloudTranspiler()
        self.incremental_optimizer = IncrementalOptimizer()

    def list_rules(
        self,
        *,
        family: str | None = None,
        severity: str | None = None,
        dialect: str | None = None,
    ) -> list[dict[str, Any]]:
        """List declarative governance rules with optional family, severity, and dialect filters."""
        fam_filter = family.strip().upper() if family else None
        sev_filter = severity.strip().upper() if severity else None
        dia_filter = dialect.strip().lower() if dialect else None

        items: list[dict[str, Any]] = []
        for rule_id in sorted(self.auditor.rules):
            meta = self.auditor.rules[rule_id]
            if fam_filter and meta.family.upper() != fam_filter:
                continue
            if sev_filter and meta.severity.value.upper() != sev_filter:
                continue
            if dia_filter and dia_filter not in meta.dialects:
                continue
            items.append(
                {
                    "id": meta.rule_id,
                    "name": meta.name,
                    "family": meta.family,
                    "severity": meta.severity.value,
                    "dialects": list(meta.dialects),
                    "applies_to": list(meta.applies_to),
                    "rationale": meta.rationale,
                    "remediation": meta.remediation,
                    "known_false_positives": list(meta.known_false_positives),
                }
            )
        return items

    def audit(
        self,
        target_path: Path | str,
        *,
        dialect: str = "duckdb",
        output_path: Path | str | None = None,
        output_format: str = "markdown",
    ) -> dict[str, Any]:
        """Audit a SQL/YAML file or directory statically and return Scorecard summary."""
        summary = self.auditor.audit_path(
            target_path=target_path,
            dialect=dialect,
            output_path=output_path,
            output_format=output_format,
        )
        return summary.to_dict()

    def audit_sql(
        self,
        sql: str,
        *,
        dialect: str = "duckdb",
        file_path: str = "inline.sql",
    ) -> dict[str, Any]:
        """Audit an inline SQL/dbt string statically and return Scorecard summary."""
        self.auditor._validate_dialect(dialect)  # noqa: SLF001
        prep = preprocess_dbt_sql(sql, file_path=file_path)
        findings, parse_err = evaluate_sql_document(prep, dialect, file_path, self.auditor.rules)
        parse_errors = [{"file_path": file_path, "error": parse_err}] if parse_err else []
        summary = build_audit_summary(
            target_path=file_path,
            dialect=dialect,
            files_audited=1,
            findings=findings,
            parse_errors=parse_errors,
        )
        return summary.to_dict()

    def scaffold(
        self,
        input_source: Any,
        output_dir: Path | str,
        *,
        source_type: str | None = None,
        project_name: str = "scaffolded_lakehouse",
        source_name: str | None = None,
        table_name: str | None = None,
        dialect: str = "duckdb",
        entity_kind: str | None = None,
        accepted_values: dict[str, tuple[str, ...]] | None = None,
        relationships: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Generate a complete Medallion dbt structure and ODCS v3.1 contract."""
        result = self.scaffolder.scaffold(
            input_source=input_source,
            output_dir=output_dir,
            source_type=source_type,
            project_name=project_name,
            source_name=source_name,
            table_name=table_name,
            dialect=dialect,
            entity_kind=entity_kind,
            accepted_values=accepted_values,
            relationships=relationships,
        )
        return result.to_dict()

    def transpile(
        self,
        sql: str,
        source_dialect: str,
        target_dialect: str,
        *,
        preserve_dbt_jinja: bool = True,
        check_roundtrip: bool = False,
    ) -> dict[str, Any]:
        """Transpile SQL/dbt code across DuckDB, Spark SQL, Snowflake, and BigQuery."""
        result = self.transpiler.transpile(
            sql=sql,
            source_dialect=source_dialect,
            target_dialect=target_dialect,
            preserve_dbt_jinja=preserve_dbt_jinja,
            check_roundtrip=check_roundtrip,
        )
        return result.to_dict()

    def suggest_incremental(
        self,
        sql: str,
        *,
        model_name: str = "fct_model",
        target_dialect: str = "duckdb",
        unique_key: str | None = None,
        watermark_column: str | None = None,
        lookback_days: int = 3,
    ) -> dict[str, Any]:
        """Suggest full-refresh to incremental conversion for a SQL/dbt model."""
        suggestion = self.incremental_optimizer.suggest(
            sql=sql,
            model_name=model_name,
            target_dialect=target_dialect,
            unique_key=unique_key,
            watermark_column=watermark_column,
            lookback_days=lookback_days,
        )
        return suggestion.to_dict()

    def lineage(self, target_path: Path | str) -> dict[str, Any]:
        """Extract deterministic dbt/SQL DAG lineage and Mermaid flowchart."""
        return extract_lineage(target_path)
