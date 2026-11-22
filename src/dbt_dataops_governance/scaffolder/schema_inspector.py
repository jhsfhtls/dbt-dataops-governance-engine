"""Schema inspection adapters for Parquet, CSV, DuckDB tables, and SQL DDL."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import sqlglot
from sqlglot import exp

from dbt_dataops_governance.scaffolder.models import ColumnSpec, TableSpec

CANONICAL_STRING_KEY_RE = re.compile(
    r"(^|_)(cnpj|cpf|cep|ibge|id_municipio|postal_code|zip_code|cnae|cbo|ncm)(_|$)",
    re.IGNORECASE,
)

DIM_TABLE_HINTS = ("customer", "client", "user", "product", "merchant", "store", "account", "dim_")


def _sanitize_identifier(raw: str) -> str:
    """Normalize table or column name into lowercase snake_case identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", raw.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "col"


def _normalize_arrow_type(arrow_type: pa.DataType) -> str:
    """Map PyArrow type to canonical DuckDB dbt contract type."""
    if pa.types.is_boolean(arrow_type):
        return "boolean"
    if pa.types.is_integer(arrow_type):
        return "bigint"
    if pa.types.is_floating(arrow_type) or pa.types.is_decimal(arrow_type):
        return "double"
    if pa.types.is_date(arrow_type):
        return "date"
    if pa.types.is_timestamp(arrow_type):
        return "timestamp"
    return "varchar"


def _normalize_sql_type(type_str: str) -> str:
    """Map DuckDB / ANSI SQL type strings to canonical DuckDB contract types."""
    low = type_str.strip().lower()
    if any(tok in low for tok in ("bool",)):
        return "boolean"
    if any(tok in low for tok in ("bigint", "int64", "integer", "int", "smallint", "tinyint")):
        return "bigint"
    if any(tok in low for tok in ("double", "float", "real", "decimal", "numeric")):
        return "double"
    if "timestamp" in low or "datetime" in low:
        return "timestamp"
    if low == "date":
        return "date"
    return "varchar"


def _build_columns(
    raw_cols: list[tuple[str, str, bool]],
    accepted_values_map: dict[str, tuple[str, ...]] | None = None,
    explicit_pks: set[str] | None = None,
) -> tuple[ColumnSpec, ...]:
    """Build normalized ColumnSpec tuple with PK and canonical string key detection."""
    accepted_map = accepted_values_map or {}
    pk_set = {p.lower() for p in (explicit_pks or set())}

    # Choose primary key if not explicitly marked in DDL
    chosen_pk: str | None = None
    if pk_set:
        for col_name, _, _ in raw_cols:
            if col_name.lower() in pk_set:
                chosen_pk = col_name.lower()
                break
    if chosen_pk is None:
        for col_name, _, _ in raw_cols:
            if col_name.lower().endswith("_sk"):
                chosen_pk = col_name.lower()
                break
    if chosen_pk is None:
        for col_name, _, _ in raw_cols:
            low = col_name.lower()
            if low == "id" or low.endswith("_id"):
                chosen_pk = low
                break
    if chosen_pk is None and raw_cols:
        chosen_pk = raw_cols[0][0].lower()

    specs: list[ColumnSpec] = []
    for raw_name, raw_dtype, nullable in raw_cols:
        col_name = _sanitize_identifier(raw_name)
        is_canonical = bool(CANONICAL_STRING_KEY_RE.search(col_name))
        is_pk = col_name == chosen_pk
        dtype = "varchar" if is_canonical else raw_dtype
        desc = f"Column {col_name} ({dtype}) ingested from source table."
        specs.append(
            ColumnSpec(
                name=col_name,
                data_type=dtype,
                nullable=False if is_pk else nullable,
                is_primary_key=is_pk,
                is_canonical_string_key=is_canonical,
                accepted_values=tuple(accepted_map.get(col_name, ())),
                description=desc,
            )
        )
    return tuple(specs)


def _infer_entity_kind(table_name: str, explicit_kind: str | None) -> str:
    """Infer Medallion entity prefix ('dim' or 'fct') from table name or override."""
    if explicit_kind:
        kind = explicit_kind.strip().lower()
        if kind not in {"dim", "fct"}:
            raise ValueError(f"entity_kind must be 'dim' or 'fct', got '{explicit_kind}'.")
        return kind
    low = table_name.lower()
    if any(hint in low for hint in DIM_TABLE_HINTS):
        return "dim"
    return "fct"


def inspect_parquet(
    parquet_path: Path | str,
    *,
    source_name: str = "raw_parquet",
    table_name: str | None = None,
    entity_kind: str | None = None,
    accepted_values: dict[str, tuple[str, ...]] | None = None,
) -> TableSpec:
    """Inspect a Parquet file's schema using PyArrow metadata."""
    path = Path(parquet_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    schema = pq.read_schema(path)
    raw_cols = [(field.name, _normalize_arrow_type(field.type), field.nullable) for field in schema]
    tbl = _sanitize_identifier(table_name or path.stem)
    kind = _infer_entity_kind(tbl, entity_kind)
    return TableSpec(
        source_name=_sanitize_identifier(source_name),
        table_name=tbl,
        columns=_build_columns(raw_cols, accepted_values_map=accepted_values),
        entity_kind=kind,
        external_location=f"read_parquet('{path.as_posix()}')",
        description=f"Parquet source table '{tbl}' ({len(raw_cols)} columns).",
    )


def inspect_csv(
    csv_path: Path | str,
    *,
    source_name: str = "raw_csv",
    table_name: str | None = None,
    entity_kind: str | None = None,
    accepted_values: dict[str, tuple[str, ...]] | None = None,
) -> TableSpec:
    """Inspect a CSV file's inferred schema via in-memory DuckDB read_csv_auto."""
    path = Path(csv_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with duckdb.connect(":memory:") as conn:
        rows = conn.execute(
            "DESCRIBE SELECT * FROM read_csv_auto(?)",
            [path.as_posix()],
        ).fetchall()

    raw_cols = [(str(r[0]), _normalize_sql_type(str(r[1])), str(r[2]).upper() != "NO") for r in rows]
    tbl = _sanitize_identifier(table_name or path.stem)
    kind = _infer_entity_kind(tbl, entity_kind)
    return TableSpec(
        source_name=_sanitize_identifier(source_name),
        table_name=tbl,
        columns=_build_columns(raw_cols, accepted_values_map=accepted_values),
        entity_kind=kind,
        external_location=f"read_csv_auto('{path.as_posix()}', all_varchar=true)",
        description=f"CSV source table '{tbl}' ({len(raw_cols)} columns).",
    )


def inspect_duckdb(
    db_path: Path | str,
    *,
    table_name: str,
    source_name: str = "raw_duckdb",
    schema_name: str = "main",
    entity_kind: str | None = None,
    accepted_values: dict[str, tuple[str, ...]] | None = None,
) -> TableSpec:
    """Inspect an existing DuckDB database table read-only via information_schema."""
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"DuckDB database file not found: {path}")

    with duckdb.connect(str(path), read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            [schema_name, table_name],
        ).fetchall()

    if not rows:
        raise ValueError(f"Table '{schema_name}.{table_name}' not found in DuckDB file {path}.")

    raw_cols = [(str(r[0]), _normalize_sql_type(str(r[1])), str(r[2]).upper() != "NO") for r in rows]
    tbl = _sanitize_identifier(table_name)
    kind = _infer_entity_kind(tbl, entity_kind)
    return TableSpec(
        source_name=_sanitize_identifier(source_name),
        table_name=tbl,
        columns=_build_columns(raw_cols, accepted_values_map=accepted_values),
        entity_kind=kind,
        source_duckdb_path=path.as_posix(),
        description=f"DuckDB source table '{schema_name}.{tbl}' ({len(raw_cols)} columns).",
    )


def inspect_ddl(
    ddl_sql: str,
    *,
    source_name: str = "raw_ddl",
    table_name: str | None = None,
    dialect: str = "duckdb",
    entity_kind: str | None = None,
    accepted_values: dict[str, tuple[str, ...]] | None = None,
) -> TableSpec:
    """Inspect a CREATE TABLE DDL statement statically using sqlglot without execution."""
    if not ddl_sql.strip():
        raise ValueError("DDL SQL string must not be empty.")

    tree = sqlglot.parse_one(ddl_sql, read=dialect)
    if not isinstance(tree, exp.Create) or not isinstance(tree.this, exp.Schema):
        raise ValueError("DDL must be a CREATE TABLE (...) statement.")

    schema_expr = tree.this
    tbl_expr = schema_expr.this
    raw_tbl_name = tbl_expr.name if isinstance(tbl_expr, exp.Table) else (table_name or "entity")
    tbl = _sanitize_identifier(table_name or raw_tbl_name)

    raw_cols: list[tuple[str, str, bool]] = []
    explicit_pks: set[str] = set()
    for expr in schema_expr.expressions:
        if isinstance(expr, exp.ColumnDef):
            col_name = expr.name
            dtype_str = expr.kind.sql(dialect=dialect) if expr.kind else "varchar"
            nullable = True
            for constraint in expr.constraints:
                kind = constraint.kind
                if isinstance(kind, exp.NotNullColumnConstraint):
                    nullable = False
                elif isinstance(kind, exp.PrimaryKeyColumnConstraint):
                    explicit_pks.add(col_name.lower())
                    nullable = False
            raw_cols.append((col_name, _normalize_sql_type(dtype_str), nullable))
        elif isinstance(expr, exp.PrimaryKey):
            for col in expr.expressions:
                if isinstance(col, exp.Ordered) and isinstance(col.this, exp.Column):
                    explicit_pks.add(col.this.name.lower())
                elif isinstance(col, exp.Column):
                    explicit_pks.add(col.name.lower())
                elif hasattr(col, "name") and col.name:
                    explicit_pks.add(str(col.name).lower())

    if not raw_cols:
        raise ValueError("No columns found in CREATE TABLE DDL.")

    kind = _infer_entity_kind(tbl, entity_kind)
    return TableSpec(
        source_name=_sanitize_identifier(source_name),
        table_name=tbl,
        columns=_build_columns(
            raw_cols,
            accepted_values_map=accepted_values,
            explicit_pks=explicit_pks,
        ),
        entity_kind=kind,
        description=f"DDL-defined source table '{tbl}' ({len(raw_cols)} columns).",
    )


def inspect_source(
    input_source: Any,
    *,
    source_type: str | None = None,
    source_name: str | None = None,
    table_name: str | None = None,
    dialect: str = "duckdb",
    entity_kind: str | None = None,
    accepted_values: dict[str, tuple[str, ...]] | None = None,
) -> TableSpec:
    """Dispatch schema inspection for Parquet, CSV, DuckDB, or SQL DDL inputs."""
    inferred_type = (source_type or "").strip().lower()
    if not inferred_type:
        if isinstance(input_source, Path) or (
            isinstance(input_source, str) and Path(input_source).suffix.lower() in {".parquet", ".csv", ".duckdb"}
        ):
            suffix = Path(input_source).suffix.lower()
            inferred_type = suffix.lstrip(".")
        elif isinstance(input_source, str) and "create" in input_source.lower():
            inferred_type = "ddl"

    if inferred_type == "parquet":
        return inspect_parquet(
            input_source,
            source_name=source_name or "raw_parquet",
            table_name=table_name,
            entity_kind=entity_kind,
            accepted_values=accepted_values,
        )
    if inferred_type == "csv":
        return inspect_csv(
            input_source,
            source_name=source_name or "raw_csv",
            table_name=table_name,
            entity_kind=entity_kind,
            accepted_values=accepted_values,
        )
    if inferred_type == "duckdb":
        if not table_name:
            raise ValueError("table_name is required when inspecting a DuckDB file.")
        return inspect_duckdb(
            input_source,
            table_name=table_name,
            source_name=source_name or "raw_duckdb",
            entity_kind=entity_kind,
            accepted_values=accepted_values,
        )
    if inferred_type == "ddl":
        return inspect_ddl(
            str(input_source),
            source_name=source_name or "raw_ddl",
            table_name=table_name,
            dialect=dialect,
            entity_kind=entity_kind,
            accepted_values=accepted_values,
        )
    raise ValueError(
        f"Unsupported source_type '{inferred_type or source_type}'. Expected parquet, csv, duckdb, or ddl."
    )
