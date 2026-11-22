"""Advisory optimizer for converting full-refresh SQL/dbt models to incremental."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from dbt_dataops_governance.auditor.jinja_preprocessor import preprocess_dbt_sql
from dbt_dataops_governance.transpiler.engine import normalize_dialect
from dbt_dataops_governance.transpiler.models import IncrementalSuggestion

STRATEGY_BY_DIALECT: dict[str, str] = {
    "duckdb": "delete+insert",
    "snowflake": "merge",
    "spark": "merge",
    "bigquery": "merge",
}

WATERMARK_PRIORITY: tuple[str, ...] = (
    "updated_at",
    "modified_at",
    "loaded_at",
    "ingested_at",
    "event_timestamp",
    "created_at",
)
WATERMARK_SUFFIXES = ("_at", "_ts", "_timestamp", "_date")

_CONFIG_BLOCK_RE = re.compile(r"\{\{\s*config\(.*?\)\s*\}\}\s*", re.DOTALL)
_TRAILING_CLAUSE_RE = re.compile(
    r"\b(GROUP\s+BY|HAVING|QUALIFY|ORDER\s+BY|LIMIT)\b",
    re.IGNORECASE,
)


def _extract_projected_names(tree: exp.Expr) -> list[str]:
    """Collect projected output column aliases or identifiers in SELECT order."""
    if not isinstance(tree, exp.Select):
        return []
    names: list[str] = []
    for expr in tree.expressions:
        if isinstance(expr, exp.Alias):
            names.append(expr.alias)
        elif isinstance(expr, exp.Column) and expr.name:
            names.append(expr.name)
    return names


def _infer_unique_key(projected: list[str], all_columns: list[str]) -> tuple[str, bool]:
    """Infer primary unique key candidate from projected and referenced columns."""
    candidates = projected + [c for c in all_columns if c not in projected]
    for col in candidates:
        if col.lower().endswith("_sk"):
            return col, True
    for col in candidates:
        low = col.lower()
        if low.endswith("_id") or low == "id":
            return col, True
    return "record_id", False


def _infer_watermark_column(projected: list[str], all_columns: list[str]) -> tuple[str, bool]:
    """Infer incremental watermark timestamp column from projected and referenced columns."""
    candidates = projected + [c for c in all_columns if c not in projected]
    lower_map = {col.lower(): col for col in candidates}
    for pref in WATERMARK_PRIORITY:
        if pref in lower_map:
            return lower_map[pref], True
    for col in candidates:
        if col.lower().endswith(WATERMARK_SUFFIXES):
            return col, True
    return "updated_at", False


def _dialect_watermark_predicate(dialect: str, watermark_col: str, lookback_days: int) -> str:
    """Format dialect-specific incremental lookback predicate referencing {{ this }}."""
    if dialect == "snowflake":
        return (
            f"{watermark_col} >= (\n"
            f"    SELECT DATEADD('day', -{lookback_days}, "
            f"COALESCE(MAX({watermark_col}), TO_TIMESTAMP('1970-01-01 00:00:00')))\n"
            "    FROM {{ this }}\n"
            ")"
        )
    if dialect == "spark":
        return (
            f"{watermark_col} >= (\n"
            f"    SELECT COALESCE(MAX({watermark_col}), TIMESTAMP '1970-01-01 00:00:00') "
            f"- INTERVAL {lookback_days} DAYS\n"
            "    FROM {{ this }}\n"
            ")"
        )
    if dialect == "bigquery":
        return (
            f"{watermark_col} >= (\n"
            f"    SELECT TIMESTAMP_SUB(COALESCE(MAX({watermark_col}), "
            f"TIMESTAMP '1970-01-01 00:00:00'), INTERVAL {lookback_days} DAY)\n"
            "    FROM {{ this }}\n"
            ")"
        )
    # Default: duckdb
    return (
        f"{watermark_col} >= (\n"
        f"    SELECT COALESCE(MAX({watermark_col}), TIMESTAMP '1970-01-01 00:00:00') "
        f"- INTERVAL '{lookback_days} days'\n"
        "    FROM {{ this }}\n"
        ")"
    )


def _inject_incremental_block(body_sql: str, has_where: bool, predicate: str) -> str:
    """Insert {% if is_incremental() %} filter cleanly before trailing clauses."""
    keyword = "AND" if has_where else "WHERE"
    inc_block = f"{{% if is_incremental() %}}\n{keyword} {predicate}\n{{% endif %}}"

    stripped = body_sql.rstrip().rstrip(";")
    # Locate outer trailing clauses outside parentheses
    depth = 0
    insert_pos: int | None = None
    idx = 0
    while idx < len(stripped):
        ch = stripped[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            match = _TRAILING_CLAUSE_RE.match(stripped[idx:])
            if match:
                insert_pos = idx
                break
        idx += 1

    if insert_pos is None:
        return f"{stripped}\n{inc_block}"

    head = stripped[:insert_pos].rstrip()
    tail = stripped[insert_pos:].lstrip()
    return f"{head}\n{inc_block}\n{tail}"


class IncrementalOptimizer:
    """Recommends full-refresh to incremental conversions for dbt SQL models."""

    def suggest(
        self,
        sql: str,
        *,
        model_name: str = "fct_model",
        target_dialect: str = "duckdb",
        unique_key: str | None = None,
        watermark_column: str | None = None,
        lookback_days: int = 3,
    ) -> IncrementalSuggestion:
        """Analyze a SQL/dbt model statically and propose an incremental configuration."""
        if lookback_days < 0:
            raise ValueError("lookback_days must be non-negative.")

        dialect = normalize_dialect(target_dialect)
        strategy = STRATEGY_BY_DIALECT[dialect]
        preprocessed = preprocess_dbt_sql(sql, file_path=f"models/core/{model_name}.sql")
        tree = sqlglot.parse_one(preprocessed.sanitized_sql, read=dialect)

        already_inc = preprocessed.materialized == "incremental" and preprocessed.has_is_incremental
        projected = _extract_projected_names(tree)
        all_columns = [c.name for c in tree.find_all(exp.Column) if c.name]

        inferred_uk, uk_found = _infer_unique_key(projected, all_columns)
        final_uk = unique_key or preprocessed.unique_key or inferred_uk
        uk_ok = bool(unique_key or preprocessed.unique_key or uk_found)

        inferred_wm, wm_found = _infer_watermark_column(projected, all_columns)
        final_wm = watermark_column or inferred_wm
        wm_ok = bool(watermark_column or wm_found)

        warnings: list[str] = []
        if not uk_ok:
            warnings.append(
                f"No obvious primary key column detected; defaulted unique_key='{final_uk}'."
            )
        if not wm_ok:
            warnings.append(
                f"No timestamp watermark column detected; defaulted watermark_column='{final_wm}'."
            )

        has_group = any(True for _ in tree.find_all(exp.Group))
        has_window = any(True for _ in tree.find_all(exp.Window))
        if has_group or has_window:
            warnings.append(
                "Model uses GROUP BY or window functions; ensure lookback_days covers the full aggregation partition window."
            )

        if uk_ok and wm_ok:
            confidence = "HIGH"
        elif wm_ok:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        if already_inc:
            return IncrementalSuggestion(
                model_name=model_name,
                target_dialect=dialect,
                already_incremental=True,
                recommended_strategy=strategy,
                unique_key=final_uk,
                watermark_column=final_wm,
                lookback_days=lookback_days,
                on_schema_change="append_new_columns",
                confidence=confidence,
                rationale="Model is already configured as incremental with an is_incremental() watermark filter.",
                suggested_sql=sql.strip(),
                warnings=warnings,
            )

        body_without_config = _CONFIG_BLOCK_RE.sub("", sql).strip()
        has_outer_where = isinstance(tree, exp.Select) and tree.args.get("where") is not None
        predicate = _dialect_watermark_predicate(dialect, final_wm, lookback_days)
        body_with_inc = _inject_incremental_block(body_without_config, has_outer_where, predicate)

        config_block = (
            "{{\n"
            "    config(\n"
            "        materialized='incremental',\n"
            f"        incremental_strategy='{strategy}',\n"
            f"        unique_key='{final_uk}',\n"
            "        on_schema_change='append_new_columns'\n"
            "    )\n"
            "}}"
        )
        suggested_sql = f"{config_block}\n\n{body_with_inc}\n"

        rationale = (
            f"Recommended '{strategy}' strategy on {dialect} keyed by '{final_uk}' with a "
            f"{lookback_days}-day lookback watermark on '{final_wm}' to eliminate full-table scans."
        )

        return IncrementalSuggestion(
            model_name=model_name,
            target_dialect=dialect,
            already_incremental=False,
            recommended_strategy=strategy,
            unique_key=final_uk,
            watermark_column=final_wm,
            lookback_days=lookback_days,
            on_schema_change="append_new_columns",
            confidence=confidence,
            rationale=rationale,
            suggested_sql=suggested_sql,
            warnings=warnings,
        )
