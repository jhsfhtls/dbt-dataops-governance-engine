"""Deterministic, reversible dbt Jinja pre-processor for static AST parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)
_CONFIG_RE = re.compile(r"\{\{\s*config\((.*?)\)\s*\}\}", re.DOTALL)
_MATERIALIZED_RE = re.compile(r"materialized\s*=\s*['\"]([a-zA-Z0-9_]+)['\"]")
_UNIQUE_KEY_RE = re.compile(r"unique_key\s*=\s*['\"]([a-zA-Z0-9_]+)['\"]")

_REF_RE = re.compile(
    r"\{\{\s*ref\(\s*(?:['\"]([a-zA-Z0-9_.-]+)['\"]\s*,\s*)?['\"]([a-zA-Z0-9_.-]+)['\"]\s*\)\s*\}\}"
)
_SOURCE_RE = re.compile(
    r"\{\{\s*source\(\s*['\"]([a-zA-Z0-9_.-]+)['\"]\s*,\s*['\"]([a-zA-Z0-9_.-]+)['\"]\s*\)\s*\}\}"
)
_THIS_RE = re.compile(r"\{\{\s*this\s*\}\}")
_MASK_MACRO_RE = re.compile(
    r"\{\{\s*(?:mask_lgpd_pii|mask_pii|hash_pii)\(\s*['\"]([a-zA-Z0-9_]+)['\"][^}]*\)\s*\}\}",
    re.DOTALL,
)
_SURROGATE_MACRO_RE = re.compile(
    r"\{\{\s*(?:dbt_utils\.)?generate_surrogate_key(?:_strict)?\([^}]*\)\s*\}\}",
    re.DOTALL,
)
_INCREMENTAL_FILTER_MACRO_RE = re.compile(
    r"\{\{\s*incremental_watermark_filter\([^}]*\)\s*\}\}",
    re.DOTALL,
)
_AUDIT_META_MACRO_RE = re.compile(r"\{\{\s*audit_run_metadata\(\s*\)\s*\}\}")
_ADAPTER_QUOTE_RE = re.compile(r"\{\{\s*adapter\.quote\([^}]*\)\s*\}\}", re.DOTALL)
_ENV_VAR_RE = re.compile(r"\{\{\s*env_var\([^}]*\)\s*\}\}", re.DOTALL)
_VAR_EXPR_RE = re.compile(r"\{\{\s*var\([^}]*\)\s*\}\}", re.DOTALL)
_BLOCK_TAG_RE = re.compile(r"\{%.*?%\}", re.DOTALL)
_GENERIC_EXPR_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)
_IS_INCREMENTAL_RE = re.compile(r"\bis_incremental\s*\(\s*\)")


def _preserve_newlines(text: str, replacement: str = " ") -> str:
    """Replace matched Jinja text while preserving newline count for line tracking."""
    newline_count = text.count("\n")
    if newline_count == 0:
        return replacement
    return replacement + ("\n" * newline_count)


@dataclass(frozen=True)
class PreprocessedSql:
    """Result of static Jinja extraction and placeholder substitution."""

    raw_sql: str
    sanitized_sql: str
    refs: tuple[str, ...]
    sources: tuple[tuple[str, str], ...]
    materialized: str | None
    unique_key: str | None
    has_is_incremental: bool
    masked_columns: tuple[str, ...]
    has_raw_var_interpolation: bool
    is_dbt_model: bool


def preprocess_dbt_sql(
    raw_sql: str,
    file_path: str | None = None,
    force_dbt_model: bool | None = None,
) -> PreprocessedSql:
    """Extract dbt Jinja metadata and substitute tags with sqlglot-parseable SQL."""
    refs: list[str] = []
    sources: list[tuple[str, str]] = []
    masked_columns: list[str] = []
    materialized: str | None = None
    unique_key: str | None = None

    has_is_incremental = bool(_IS_INCREMENTAL_RE.search(raw_sql))
    has_raw_var_interpolation = False

    def _replace_comment(match: re.Match[str]) -> str:
        return _preserve_newlines(match.group(0), "")

    def _replace_config(match: re.Match[str]) -> str:
        nonlocal materialized, unique_key
        body = match.group(1)
        mat_match = _MATERIALIZED_RE.search(body)
        if mat_match:
            materialized = mat_match.group(1).lower()
        uk_match = _UNIQUE_KEY_RE.search(body)
        if uk_match:
            unique_key = uk_match.group(1)
        return _preserve_newlines(match.group(0), "")

    def _replace_ref(match: re.Match[str]) -> str:
        model = match.group(2)
        refs.append(model)
        safe_ident = re.sub(r"[^a-zA-Z0-9_]", "_", model)
        return f"__dge_ref__{safe_ident}"

    def _replace_source(match: re.Match[str]) -> str:
        src_name, tbl_name = match.group(1), match.group(2)
        sources.append((src_name, tbl_name))
        safe_src = re.sub(r"[^a-zA-Z0-9_]", "_", src_name)
        safe_tbl = re.sub(r"[^a-zA-Z0-9_]", "_", tbl_name)
        return f"__dge_source__{safe_src}__{safe_tbl}"

    def _replace_mask(match: re.Match[str]) -> str:
        col = match.group(1)
        masked_columns.append(col.lower())
        return f"__dge_masked__({col})"

    def _replace_inc_macro(match: re.Match[str]) -> str:
        nonlocal has_is_incremental
        has_is_incremental = True
        return _preserve_newlines(match.group(0), "WHERE 1 = 1")

    def _replace_var(match: re.Match[str]) -> str:
        nonlocal has_raw_var_interpolation
        has_raw_var_interpolation = True
        return _preserve_newlines(match.group(0), "'__dge_var__'")

    text = _COMMENT_RE.sub(_replace_comment, raw_sql)
    text = _CONFIG_RE.sub(_replace_config, text)
    text = _REF_RE.sub(_replace_ref, text)
    text = _SOURCE_RE.sub(_replace_source, text)
    text = _THIS_RE.sub("__dge_this__", text)
    text = _MASK_MACRO_RE.sub(_replace_mask, text)
    text = _SURROGATE_MACRO_RE.sub("__dge_surrogate__('key')", text)
    text = _INCREMENTAL_FILTER_MACRO_RE.sub(_replace_inc_macro, text)
    text = _AUDIT_META_MACRO_RE.sub("'__dge_audit_meta__' AS _dge_audit_meta", text)
    text = _ADAPTER_QUOTE_RE.sub("'__dge_quoted_var__'", text)
    text = _ENV_VAR_RE.sub("'__dge_env_var__'", text)
    text = _VAR_EXPR_RE.sub(_replace_var, text)

    if _BLOCK_TAG_RE.search(text):
        # Detect variable assignments using var(...) in {% set ... %} blocks
        for block in _BLOCK_TAG_RE.findall(text):
            if "var(" in block and "adapter.quote" not in block:
                has_raw_var_interpolation = True
        text = _BLOCK_TAG_RE.sub(lambda m: _preserve_newlines(m.group(0), ""), text)

    text = _GENERIC_EXPR_RE.sub(lambda m: _preserve_newlines(m.group(0), "__dge_expr__"), text)

    # Check if raw var(...) is interpolated inside SQL strings like '{{ target_filter }}'
    if re.search(r"'\s*\{\{[^}]+\}\}\s*'", raw_sql) and "adapter.quote" not in raw_sql:
        has_raw_var_interpolation = True

    inferred_dbt = bool(
        refs
        or sources
        or materialized is not None
        or has_is_incremental
        or masked_columns
        or ("{{" in raw_sql or "{%" in raw_sql)
        or (file_path and "/models/" in file_path.replace("\\", "/"))
    )
    is_dbt_model = inferred_dbt if force_dbt_model is None else force_dbt_model

    return PreprocessedSql(
        raw_sql=raw_sql,
        sanitized_sql=text,
        refs=tuple(refs),
        sources=tuple(sources),
        materialized=materialized,
        unique_key=unique_key,
        has_is_incremental=has_is_incremental,
        masked_columns=tuple(masked_columns),
        has_raw_var_interpolation=has_raw_var_interpolation,
        is_dbt_model=is_dbt_model,
    )
