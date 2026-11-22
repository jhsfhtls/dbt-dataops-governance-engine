"""Zero-execution static AST AuditEngine orchestrating SQL and YAML rule checks."""

from __future__ import annotations

from pathlib import Path

from dbt_dataops_governance.auditor.catalog_loader import DEFAULT_REPO_ROOT, load_governance_rules
from dbt_dataops_governance.auditor.jinja_preprocessor import preprocess_dbt_sql
from dbt_dataops_governance.auditor.models import AuditFinding, AuditSummary, build_audit_summary
from dbt_dataops_governance.auditor.path_shield import validate_report_output_path
from dbt_dataops_governance.auditor.reporter import render_json_report, render_markdown_report
from dbt_dataops_governance.auditor.rules_sql import evaluate_sql_document
from dbt_dataops_governance.auditor.rules_yaml import evaluate_yaml_document

SUPPORTED_DIALECTS = ("duckdb", "snowflake", "spark", "bigquery")
IGNORED_DIR_PARTS = {".git", ".venv", "target", "dbt_packages", "logs", "__pycache__"}


class AuditEngine:
    """Static SQL/dbt AST auditor driven by catalog/governance_rules.yaml."""

    def __init__(self, catalog_path: Path | None = None, repo_root: Path | None = None) -> None:
        self.rules = load_governance_rules(catalog_path=catalog_path)
        self.repo_root = (repo_root or DEFAULT_REPO_ROOT).resolve()

    def audit_sql(
        self,
        sql_text: str,
        dialect: str = "duckdb",
        file_path: str = "inline.sql",
        is_dbt_model: bool | None = None,
    ) -> list[AuditFinding]:
        """Audit a single SQL or dbt Jinja model string without executing SQL."""
        self._validate_dialect(dialect)
        preprocessed = preprocess_dbt_sql(sql_text, file_path=file_path, force_dbt_model=is_dbt_model)
        findings, parse_error = evaluate_sql_document(
            preprocessed=preprocessed,
            dialect=dialect,
            file_path=file_path,
            catalog=self.rules,
        )
        if parse_error:
            raise ValueError(f"{file_path}: {parse_error}")
        return findings

    def audit_yaml(
        self,
        yaml_text: str,
        file_path: str = "_models.yml",
    ) -> list[AuditFinding]:
        """Audit a single dbt schema YAML or ODCS contract YAML string."""
        findings, parse_error = evaluate_yaml_document(
            raw_yaml=yaml_text,
            file_path=file_path,
            catalog=self.rules,
        )
        if parse_error:
            raise ValueError(f"{file_path}: {parse_error}")
        return findings

    def audit_path(
        self,
        target_path: Path | str,
        dialect: str = "duckdb",
        output_path: Path | str | None = None,
        output_format: str = "markdown",
    ) -> AuditSummary:
        """Audit a SQL/YAML file or directory tree and optionally write a shielded report."""
        self._validate_dialect(dialect)
        target = Path(target_path)
        if not target.exists():
            raise FileNotFoundError(f"Audit target path does not exist: {target}")

        files = self._collect_target_files(target)
        findings: list[AuditFinding] = []
        parse_errors: list[dict[str, str]] = []

        for file_item in files:
            rel_label = self._relative_label(target, file_item)
            raw_text = file_item.read_text(encoding="utf-8", errors="replace")

            if file_item.suffix.lower() == ".sql":
                preprocessed = preprocess_dbt_sql(raw_text, file_path=rel_label)
                file_findings, err = evaluate_sql_document(preprocessed, dialect, rel_label, self.rules)
            else:
                file_findings, err = evaluate_yaml_document(raw_text, rel_label, self.rules)

            findings.extend(file_findings)
            if err:
                parse_errors.append({"file_path": rel_label, "error": err})

        summary = build_audit_summary(
            target_path=str(target.resolve()),
            dialect=dialect,
            files_audited=len(files),
            findings=findings,
            parse_errors=parse_errors,
        )

        if output_path is not None:
            safe_out = validate_report_output_path(target, Path(output_path), self.repo_root)
            rendered = (
                render_json_report(summary)
                if output_format.lower() == "json"
                else render_markdown_report(summary)
            )
            safe_out.parent.mkdir(parents=True, exist_ok=True)
            with safe_out.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)

        return summary

    @staticmethod
    def _validate_dialect(dialect: str) -> None:
        if dialect not in SUPPORTED_DIALECTS:
            raise ValueError(
                f"Unsupported dialect '{dialect}'. Expected one of {SUPPORTED_DIALECTS}."
            )

    @staticmethod
    def _collect_target_files(target: Path) -> list[Path]:
        if target.is_file():
            return [target]

        collected: list[Path] = []
        for path in sorted(target.rglob("*")):
            if not path.is_file():
                continue
            if any(part in IGNORED_DIR_PARTS for part in path.parts):
                continue
            if path.suffix.lower() in {".sql", ".yml", ".yaml"}:
                if path.name in {"dbt_project.yml", "profiles.yml", "packages.yml"}:
                    continue
                collected.append(path)
        return collected

    @staticmethod
    def _relative_label(root: Path, file_item: Path) -> str:
        if root.is_file():
            return file_item.name
        return file_item.relative_to(root).as_posix()
