"""Multi-cloud SQL/dbt AST transpiler across DuckDB, Spark SQL, Snowflake, and BigQuery."""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

from dbt_dataops_governance.transpiler.models import TranspileLimitation, TranspileResult

DIALECT_ALIASES: dict[str, str] = {
    "duckdb": "duckdb",
    "snowflake": "snowflake",
    "spark": "spark",
    "sparksql": "spark",
    "databricks": "spark",
    "bigquery": "bigquery",
}

_CONFIG_BLOCK_RE = re.compile(r"(\{\{\s*config\(.*?\)\s*\}\}\s*)", re.DOTALL)
_JINJA_EXPR_RE = re.compile(
    r"\{\{\s*(?:"
    r"ref\([^}]+\)"
    r"|source\([^}]+\)"
    r"|this"
    r"|mask_lgpd_pii\([^}]+\)"
    r"|generate_surrogate_key(?:_strict)?\([^}]+\)"
    r")\s*\}\}",
    re.DOTALL,
)
_SEMI_STRUCTURED_RE = re.compile(
    r"\b(LATERAL\s+FLATTEN|PARSE_JSON|GET_JSON_OBJECT|JSON_EXTRACT_STRING|FLATTEN|EXPLODE|UNNEST|VARIANT)\b",
    re.IGNORECASE,
)
_SNOWFLAKE_COLON_PATH_RE = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*:[a-zA-Z_][a-zA-Z0-9_]*")


def normalize_dialect(dialect: str) -> str:
    """Normalize supported warehouse/engine dialect aliases to sqlglot names."""
    key = dialect.strip().lower()
    if key not in DIALECT_ALIASES:
        supported = sorted(DIALECT_ALIASES)
        raise ValueError(f"Unsupported dialect '{dialect}'. Expected one of {supported}.")
    return DIALECT_ALIASES[key]


def _extract_leading_configs(sql: str) -> tuple[list[str], str]:
    """Separate dbt {{ config(...) }} blocks from the SQL body."""
    configs = [m.group(1).strip() for m in _CONFIG_BLOCK_RE.finditer(sql)]
    stripped = _CONFIG_BLOCK_RE.sub("", sql).strip()
    return configs, stripped


def _mask_jinja_tokens(sql: str) -> tuple[str, dict[str, str]]:
    """Replace dbt Jinja expressions with case-insensitive reversible SQL tokens."""
    token_map: dict[str, str] = {}
    counter = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal counter
        expr_text = match.group(0)
        if "mask_lgpd_pii" in expr_text or "generate_surrogate_key" in expr_text:
            placeholder = f"__dge_fn_{counter}__()"
        else:
            placeholder = f"__dge_tok_{counter}__"
        token_map[placeholder.rstrip("()")] = expr_text
        counter += 1
        return placeholder

    masked = _JINJA_EXPR_RE.sub(_sub, sql)
    return masked, token_map


def _restore_jinja_tokens(sql: str, token_map: dict[str, str]) -> str:
    """Restore original dbt Jinja expressions inside transpiled SQL."""
    restored = sql
    for token, original in token_map.items():
        if "mask_lgpd_pii" in original or "generate_surrogate_key" in original:
            pattern = re.compile(rf"{re.escape(token)}\s*\(\s*\)", re.IGNORECASE)
        else:
            pattern = re.compile(re.escape(token), re.IGNORECASE)
        restored = pattern.sub(lambda _m, orig=original: orig, restored)
    return restored


def _detect_limitations(
    sql: str,
    trees: list[exp.Expr | None],
    source_dialect: str,
    target_dialect: str,
) -> list[TranspileLimitation]:
    """Identify known cross-engine syntax/semantic gaps in transpiled SQL."""
    limitations: list[TranspileLimitation] = []
    seen_codes: set[str] = set()

    def _add(
        code: str,
        feature: str,
        severity: str,
        description: str,
        workaround: str,
    ) -> None:
        if code in seen_codes:
            return
        seen_codes.add(code)
        limitations.append(
            TranspileLimitation(
                code=code,
                feature=feature,
                source_dialect=source_dialect,
                target_dialect=target_dialect,
                severity=severity,
                description=description,
                workaround=workaround,
            )
        )

    for tree in trees:
        if tree is None:
            continue
        if any(sel.args.get("qualify") is not None for sel in tree.find_all(exp.Select)):
            _add(
                "LIM_QUALIFY",
                "QUALIFY window filter clause",
                "MEDIUM",
                f"QUALIFY rewriting between {source_dialect} and {target_dialect} may expand into an inline ROW_NUMBER() subquery.",
                "Verify generated subquery column aliases or materialize deduplication in a named CTE.",
            )
        if any(True for _ in tree.find_all(exp.ILike)):
            _add(
                "LIM_ILIKE",
                "Case-insensitive ILIKE predicate",
                "LOW",
                f"ILIKE between {source_dialect} and {target_dialect} may require LOWER() normalization on engines lacking native ILIKE.",
                "Normalize strings with LOWER(TRIM(col)) in staging models for deterministic cross-warehouse filters.",
            )
        if any(True for _ in tree.find_all(exp.Merge)):
            _add(
                "LIM_MERGE_SEMANTICS",
                "MERGE DML semantics",
                "HIGH",
                f"MERGE clauses (such as WHEN NOT MATCHED BY SOURCE) differ across {source_dialect} and {target_dialect}.",
                "Prefer dbt incremental_strategy='merge' or 'delete+insert' rather than raw vendor MERGE DDL.",
            )
        if "spark" in (source_dialect, target_dialect) and any(
            True for _ in tree.find_all(exp.Cast, exp.TryCast)
        ):
            _add(
                "LIM_SPARK_CAST_ANSI",
                "Spark non-ANSI CAST vs strict CAST",
                "MEDIUM",
                "Spark CAST returns NULL on invalid conversions outside ANSI mode, mapping to TRY_CAST on DuckDB/Snowflake.",
                "Use TRY_CAST explicitly when null-on-error semantics are desired across all clouds.",
            )

    if _SEMI_STRUCTURED_RE.search(sql) or _SNOWFLAKE_COLON_PATH_RE.search(sql):
        _add(
            "LIM_SEMI_STRUCTURED",
            "Semi-structured JSON/VARIANT & array flattening",
            "HIGH",
            f"Semi-structured traversal or FLATTEN/EXPLODE/UNNEST differs significantly between {source_dialect} and {target_dialect}.",
            "Isolate semi-structured parsing in bronze/staging adapters and test target dialect output explicitly.",
        )

    return limitations


def _canonicalize_roundtrip_ast(tree: exp.Expr) -> exp.Expr:
    """Collapse semantically idempotent SQL rewrites such as NULLIF(NULLIF(x, 0), 0)."""

    def _collapse_idempotent_nullif(node: exp.Expr) -> exp.Expr:
        if (
            isinstance(node, exp.Nullif)
            and isinstance(node.this, exp.Nullif)
            and node.expression == node.this.expression
        ):
            return node.this.copy()
        return node

    return tree.transform(_collapse_idempotent_nullif)


class MultiCloudTranspiler:
    """Static AST SQL transpiler across DuckDB, Spark SQL (Databricks), Snowflake, and BigQuery."""

    def transpile(
        self,
        sql: str,
        source_dialect: str,
        target_dialect: str,
        *,
        preserve_dbt_jinja: bool = True,
        check_roundtrip: bool = False,
    ) -> TranspileResult:
        """Transpile SQL or dbt model text across cloud/embedded dialects without executing SQL."""
        src = normalize_dialect(source_dialect)
        tgt = normalize_dialect(target_dialect)
        if not sql.strip():
            raise ValueError("Input SQL must not be empty.")

        configs, body_sql = _extract_leading_configs(sql) if preserve_dbt_jinja else ([], sql)
        masked_sql, token_map = (
            _mask_jinja_tokens(body_sql) if preserve_dbt_jinja else (body_sql, {})
        )

        if "{{" in masked_sql or "{%" in masked_sql:
            raise ValueError(
                "Unsupported complex Jinja control flow detected; compile dbt SQL before transpiling."
            )

        parsed_trees = sqlglot.parse(masked_sql, read=src, error_level=sqlglot.ErrorLevel.RAISE)
        transpiled_statements = sqlglot.transpile(
            masked_sql,
            read=src,
            write=tgt,
            pretty=True,
            error_level=sqlglot.ErrorLevel.RAISE,
        )
        transpiled_body = ";\n".join(stmt.strip() for stmt in transpiled_statements if stmt.strip())

        if preserve_dbt_jinja and token_map:
            transpiled_body = _restore_jinja_tokens(transpiled_body, token_map)
        if configs:
            config_header = "\n".join(configs)
            transpiled_sql = f"{config_header}\n\n{transpiled_body}"
        else:
            transpiled_sql = transpiled_body

        limitations = _detect_limitations(body_sql, parsed_trees, src, tgt)
        warnings = [f"[{lim.code}] {lim.description}" for lim in limitations]

        roundtrip_equivalent: bool | None = None
        if check_roundtrip:
            roundtrip_equivalent, _, rt_notes = self.validate_roundtrip(sql, src, tgt)
            warnings.extend(rt_notes)

        return TranspileResult(
            source_dialect=src,
            target_dialect=tgt,
            source_sql=sql,
            transpiled_sql=transpiled_sql,
            dbt_jinja_preserved=preserve_dbt_jinja and bool(configs or token_map),
            warnings=warnings,
            limitations=limitations,
            roundtrip_equivalent=roundtrip_equivalent,
        )

    def validate_roundtrip(
        self,
        sql: str,
        source_dialect: str,
        target_dialect: str,
    ) -> tuple[bool, str, list[str]]:
        """Transpile source -> target -> source and verify structural AST equivalence."""
        src = normalize_dialect(source_dialect)
        tgt = normalize_dialect(target_dialect)

        forward = self.transpile(sql, src, tgt, preserve_dbt_jinja=True, check_roundtrip=False)
        backward = self.transpile(
            forward.transpiled_sql,
            tgt,
            src,
            preserve_dbt_jinja=True,
            check_roundtrip=False,
        )

        _, orig_body = _extract_leading_configs(sql)
        _, rt_body = _extract_leading_configs(backward.transpiled_sql)
        masked_orig, _ = _mask_jinja_tokens(orig_body)
        masked_rt, _ = _mask_jinja_tokens(rt_body)

        orig_trees = [t for t in sqlglot.parse(masked_orig, read=src) if t is not None]
        rt_trees = [t for t in sqlglot.parse(masked_rt, read=src) if t is not None]

        if len(orig_trees) != len(rt_trees):
            return False, backward.transpiled_sql, ["Statement count changed during round-trip."]

        notes: list[str] = []
        equivalent = True
        for orig_tree, rt_tree in zip(orig_trees, rt_trees, strict=True):
            canon_orig = _canonicalize_roundtrip_ast(orig_tree)
            canon_rt = _canonicalize_roundtrip_ast(rt_tree)
            edits = [d for d in sqlglot.diff(canon_orig, canon_rt) if type(d).__name__ != "Keep"]
            if edits:
                equivalent = False
                edit_kinds = ", ".join(sorted({type(d).__name__ for d in edits}))
                notes.append(
                    f"Round-trip AST divergence across {src} <-> {tgt} ({len(edits)} edits: {edit_kinds})."
                )
        return equivalent, backward.transpiled_sql, notes
