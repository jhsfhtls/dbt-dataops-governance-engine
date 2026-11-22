"""Domain models for automated Medallion scaffolding and ODCS v3.1 contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ColumnSpec:
    """Normalized column specification extracted from Parquet, CSV, DuckDB, or DDL."""

    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_canonical_string_key: bool = False
    accepted_values: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize column spec to a JSON-friendly dictionary."""
        return {
            "name": self.name,
            "data_type": self.data_type,
            "nullable": self.nullable,
            "is_primary_key": self.is_primary_key,
            "is_canonical_string_key": self.is_canonical_string_key,
            "accepted_values": list(self.accepted_values),
            "description": self.description,
        }


@dataclass(frozen=True)
class TableSpec:
    """Normalized source table specification used to generate Medallion dbt layers."""

    source_name: str
    table_name: str
    columns: tuple[ColumnSpec, ...]
    entity_kind: str = "fct"
    external_location: str | None = None
    source_duckdb_path: str | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize table spec to a JSON-friendly dictionary."""
        return {
            "source_name": self.source_name,
            "table_name": self.table_name,
            "entity_kind": self.entity_kind,
            "external_location": self.external_location,
            "source_duckdb_path": self.source_duckdb_path,
            "description": self.description,
            "columns": [col.to_dict() for col in self.columns],
        }


@dataclass(frozen=True)
class ScaffoldResult:
    """Summary of generated Medallion dbt project and ODCS v3.1 contract files."""

    output_dir: str
    project_name: str
    source_name: str
    table_name: str
    target_model_name: str
    generated_files: list[str] = field(default_factory=list)
    table_spec: TableSpec | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize scaffold result to a JSON-friendly dictionary."""
        return {
            "output_dir": self.output_dir,
            "project_name": self.project_name,
            "source_name": self.source_name,
            "table_name": self.table_name,
            "target_model_name": self.target_model_name,
            "generated_files": list(self.generated_files),
            "table_spec": self.table_spec.to_dict() if self.table_spec else None,
        }
