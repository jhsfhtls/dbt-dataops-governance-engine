"""Medallion scaffolder engine orchestrating schema inspection and artifact generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dbt_dataops_governance.scaffolder.models import ScaffoldResult
from dbt_dataops_governance.scaffolder.path_guard import safe_join, validate_output_dir
from dbt_dataops_governance.scaffolder.schema_inspector import inspect_source
from dbt_dataops_governance.scaffolder.templates import (
    render_core_models_yml,
    render_core_sql,
    render_dbt_project_yml,
    render_odcs_contract_yaml,
    render_profiles_yml,
    render_sources_yml,
    render_staging_models_yml,
    render_staging_sql,
)


def _write_utf8_lf(path: Path, content: str) -> None:
    """Write text file strictly as UTF-8 without BOM and LF line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = content.replace("\r\n", "\n")
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(normalized)


class MedallionScaffolder:
    """Generates complete Medallion dbt layers, contracts, tests, and ODCS v3.1 specs."""

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
    ) -> ScaffoldResult:
        """Inspect source metadata and generate a complete dbt Medallion structure."""
        safe_root = validate_output_dir(output_dir)
        spec = inspect_source(
            input_source,
            source_type=source_type,
            source_name=source_name,
            table_name=table_name,
            dialect=dialect,
            entity_kind=entity_kind,
            accepted_values=accepted_values,
        )

        stg_name = f"stg_{spec.source_name}__{spec.table_name}"
        target_model_name = f"{spec.entity_kind}_{spec.table_name}"
        clean_proj = project_name.strip().lower().replace("-", "_")

        file_contents: dict[tuple[str, ...], str] = {
            ("dbt_project.yml",): render_dbt_project_yml(clean_proj),
            ("profiles.yml",): render_profiles_yml(clean_proj, spec, output_dir=safe_root),
            ("models", "staging", "sources.yml"): render_sources_yml(spec),
            ("models", "staging", f"{stg_name}.sql"): render_staging_sql(spec),
            ("models", "staging", "_models.yml"): render_staging_models_yml(spec, stg_name),
            ("models", "core", f"{target_model_name}.sql"): render_core_sql(spec, stg_name),
            ("models", "core", "_models.yml"): render_core_models_yml(
                spec,
                stg_name,
                target_model_name,
                relationships=relationships,
            ),
            ("contracts", f"{target_model_name}_contract.yaml"): render_odcs_contract_yaml(
                spec,
                target_model_name,
            ),
        }

        generated_files: list[str] = []
        for rel_parts, content in file_contents.items():
            dest = safe_join(safe_root, *rel_parts)
            _write_utf8_lf(dest, content)
            generated_files.append(dest.relative_to(safe_root).as_posix())

        if not spec.source_duckdb_path:
            safe_join(safe_root, "target").mkdir(parents=True, exist_ok=True)

        return ScaffoldResult(
            output_dir=str(safe_root),
            project_name=clean_proj,
            source_name=spec.source_name,
            table_name=spec.table_name,
            target_model_name=target_model_name,
            generated_files=sorted(generated_files),
            table_spec=spec,
        )
