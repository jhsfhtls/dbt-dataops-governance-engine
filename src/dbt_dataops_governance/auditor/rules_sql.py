"""Static AST rule evaluators for SQL and dbt models using sqlglot."""

from __future__ import annotations

import re
from pathlib import Path

import sqlglot
from sqlglot import exp

from dbt_dataops_governance.auditor.jinja_preprocessor import PreprocessedSql
from dbt_dataops_governance.auditor.models import AuditFinding, RuleMetadata

CANONICAL_STRING_KEY_RE = re.compile(
    r"(^|_)(cnpj|cpf|cep|ibge|id_municipio|postal_code|zip_code|cnae|cbo|ncm)(_|$)",
    re.IGNORECASE,
)
CANONICAL_EXCLUSION_RE = re.compile(r"(_masked|_hash|_sk|_len|_count|_valid)$", re.IGNORECASE)

PII_COLUMN_RE = re.compile(
    r"^(cpf|cnpj_cpf|email|telefone|celular|phone|rg|cnh|nome_completo|full_name|ssn|passport|birth_date|full_address)$"
    r"|_(cpf|email|telefone|celular)$",
    re.IGNORECASE,
)
PII_SAFE_SUFFIX_RE = re.compile(r"(_masked|_hash|_sk|_surrogate|_token|_count|_flag)$", re.IGNORECASE)

NUMERIC_DTYPES = {
    exp.DataType.Type.INT,
    exp.DataType.Type.BIGINT,
    exp.DataType.Type.SMALLINT,
    exp.DataType.Type.TINYINT,
    exp.DataType.Type.INT128,
    exp.DataType.Type.UINT,
    exp.DataType.Type.UBIGINT,
    exp.DataType.Type.USMALLINT,
    exp.DataType.Type.UTINYINT,
    exp.DataType.Type.DECIMAL,
    exp.DataType.Type.FLOAT,
    exp.DataType.Type.DOUBLE,
}

SAFE_MASKING_FUNCS = {
    "__dge_masked__",
    "__dge_surrogate__",
    "sha256",
    "sha2",
    "sha512",
    "md5",
    "hash",
    "mask",
    "regexp_replace",
}

NON_SARGABLE_ALLOWED_WRAPPERS = {
    "coalesce",
    "nullif",
    "__dge_masked__",
    "__dge_surrogate__",
    "safe_divide",
}

COMPARISON_TYPES = (
    exp.EQ,
    exp.NEQ,
    exp.GT,
    exp.GTE,
    exp.LT,
    exp.LTE,
    exp.Like,
    exp.ILike,
    exp.Between,
    exp.In,
)

HARDCODED_SQL_SECRET_RE = re.compile(
    r"(?:PASSWORD|SECRET|API_TOKEN|API_KEY|ACCESS_KEY|AUTH_TOKEN|KEY_ID)\s*(?:=|:|\s)\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
EXECUTE_IMMEDIATE_RE = re.compile(r"\bEXECUTE\s+IMMEDIATE\b", re.IGNORECASE)


def _infer_layer(file_path: str) -> dict[str, bool]:
    """Infer Medallion layer flags from model path and filename."""
    norm = file_path.replace("\\", "/").lower()
    stem = Path(norm).stem
    is_staging = "/staging/" in norm or stem.startswith("stg_")
    is_mart = "/marts/" in norm or "/gold/" in norm or stem.startswith("mart_")
    is_core = "/core/" in norm or stem.startswith(("dim_", "fct_"))
    return {
        "is_staging": is_staging,
        "is_mart": is_mart,
        "is_core": is_core,
        "is_core_or_mart": is_core or is_mart,
        "is_fact": stem.startswith("fct_"),
        "stem": stem,  # type: ignore[dict-item]
    }


def _make_finding(
    catalog: dict[str, RuleMetadata],
    rule_id: str,
    file_path: str,
    line: int,
    message: str,
    snippet: str = "",
) -> AuditFinding:
    """Create an AuditFinding enriched with catalog metadata."""
    meta = catalog[rule_id]
    return AuditFinding(
        rule_id=rule_id,
        rule_name=meta.name,
        family=meta.family,
        severity=meta.severity,
        file_path=file_path,
        line=max(1, line),
        message=message,
        remediation=meta.remediation,
        snippet=snippet[:200],
    )


def _find_line(raw_sql: str, needle: str, default: int = 1) -> int:
    """Locate 1-based line number of a substring in raw SQL."""
    if not needle:
        return default
    idx = raw_sql.lower().find(needle.lower())
    if idx < 0:
        return default
    return raw_sql[:idx].count("\n") + 1


def _is_tautology(expr: exp.Expr) -> bool:
    """Return True if expression is a constant TRUE or X = X tautology."""
    if isinstance(expr, exp.Boolean) and expr.this is True:
        return True
    if isinstance(expr, exp.EQ) and expr.this == expr.expression:
        return True
    return False


def _has_non_sargable_wrapper(node: exp.Expr) -> bool:
    """Return True if node wraps a column in a function/cast breaking sargability."""
    if isinstance(node, exp.Paren):
        return _has_non_sargable_wrapper(node.this)

    is_cast_or_extract = isinstance(node, (exp.Cast, exp.TryCast, exp.Extract))
    is_func = isinstance(node, exp.Func)
    if not (is_cast_or_extract or is_func):
        return False

    func_name = node.sql_name().lower() if hasattr(node, "sql_name") else ""
    if func_name in NON_SARGABLE_ALLOWED_WRAPPERS or isinstance(node, (exp.Coalesce, exp.Nullif)):
        return any(_has_non_sargable_wrapper(child) for child in node.iter_expressions())

    return any(isinstance(col, exp.Column) for col in node.find_all(exp.Column))


def _subquery_nesting_depth(node: exp.Expr, depth: int = 0) -> int:
    """Compute maximum nesting depth of FROM/JOIN derived subqueries."""
    max_depth = depth
    for child in node.iter_expressions():
        if isinstance(child, exp.Subquery):
            max_depth = max(max_depth, _subquery_nesting_depth(child, depth + 1))
        else:
            max_depth = max(max_depth, _subquery_nesting_depth(child, depth))
    return max_depth


def _is_pii_column_name(name: str) -> bool:
    """Return True if identifier represents an unmasked PII attribute."""
    clean = name.strip().lower()
    if not clean or PII_SAFE_SUFFIX_RE.search(clean):
        return False
    return bool(PII_COLUMN_RE.search(clean))


def _is_masked_or_aggregated(expr: exp.Expr) -> bool:
    """Return True if projection expression wraps PII in a masking/hash/aggregate call."""
    target = expr.this if isinstance(expr, exp.Alias) else expr
    if isinstance(expr, exp.Alias) and PII_SAFE_SUFFIX_RE.search(expr.alias.lower()):
        return True
    if isinstance(target, exp.AggFunc):
        return True
    for func in target.find_all(exp.Func):
        fname = func.sql_name().lower() if hasattr(func, "sql_name") else ""
        if fname in SAFE_MASKING_FUNCS or isinstance(func, (exp.SHA2, exp.SHA, exp.MD5)):
            return True
    return False


def _evaluate_performance_rules(
    tree: exp.Expr,
    preprocessed: PreprocessedSql,
    file_path: str,
    layer: dict[str, bool],
    catalog: dict[str, RuleMetadata],
) -> list[AuditFinding]:
    """Evaluate PERF_001 through PERF_007 against one parsed SQL AST."""
    findings: list[AuditFinding] = []
    raw_sql = preprocessed.raw_sql

    # PERF_001: SELECT * in non-staging models
    if not layer["is_staging"]:
        for select in tree.find_all(exp.Select):
            if isinstance(select.parent, exp.Exists):
                continue
            for proj in select.expressions:
                is_star = isinstance(proj, exp.Star) or (
                    isinstance(proj, exp.Column) and isinstance(proj.this, exp.Star)
                )
                if is_star:
                    findings.append(
                        _make_finding(
                            catalog,
                            "PERF_001",
                            file_path,
                            _find_line(raw_sql, "select"),
                            "Avoid SELECT * in core/mart or final models; enumerate explicit columns.",
                            proj.sql(),
                        )
                    )
                    break

    # PERF_002: JOIN without predicate / CROSS JOIN / implicit comma join
    for join in tree.find_all(exp.Join):
        kind = (join.args.get("kind") or "").upper()
        method = (join.args.get("method") or "").upper()
        on_expr = join.args.get("on")
        using_expr = join.args.get("using")
        if kind == "CROSS":
            findings.append(
                _make_finding(
                    catalog,
                    "PERF_002",
                    file_path,
                    _find_line(raw_sql, "cross join"),
                    "CROSS JOIN detected; verify explicit join predicate or pre-aggregate.",
                    join.sql(),
                )
            )
        elif method != "NATURAL" and on_expr is None and using_expr is None:
            findings.append(
                _make_finding(
                    catalog,
                    "PERF_002",
                    file_path,
                    _find_line(raw_sql, "join"),
                    "JOIN or implicit comma join missing explicit ON/USING predicate.",
                    join.sql(),
                )
            )
        elif on_expr is not None and _is_tautology(on_expr):
            findings.append(
                _make_finding(
                    catalog,
                    "PERF_002",
                    file_path,
                    _find_line(raw_sql, " on "),
                    "JOIN uses a tautological ON predicate (TRUE / 1=1), causing a Cartesian product.",
                    join.sql(),
                )
            )

    # PERF_003: Incremental / fact model missing incremental watermark guard
    requires_incremental = (
        preprocessed.is_dbt_model
        and (
            preprocessed.materialized == "incremental"
            or (layer["is_fact"] and preprocessed.materialized not in {"table", "view", "ephemeral"})
        )
    )
    if requires_incremental and not preprocessed.has_is_incremental:
        findings.append(
            _make_finding(
                catalog,
                "PERF_003",
                file_path,
                1,
                "Incremental/fact model lacks an is_incremental() or incremental_watermark_filter() predicate.",
            )
        )

    # PERF_004: Non-sargable function calls on columns in WHERE or JOIN ON
    predicate_roots: list[exp.Expr] = [w.this for w in tree.find_all(exp.Where) if w.this is not None]
    for join in tree.find_all(exp.Join):
        if join.args.get("on") is not None:
            predicate_roots.append(join.args["on"])

    seen_non_sargable = False
    for root in predicate_roots:
        if seen_non_sargable:
            break
        for comp in root.find_all(*COMPARISON_TYPES):
            for child in comp.iter_expressions():
                if _has_non_sargable_wrapper(child):
                    findings.append(
                        _make_finding(
                            catalog,
                            "PERF_004",
                            file_path,
                            _find_line(raw_sql, "where"),
                            f"Non-sargable expression '{child.sql()}' wraps a column in a filter predicate.",
                            comp.sql(),
                        )
                    )
                    seen_non_sargable = True
                    break
            if seen_non_sargable:
                break

    # PERF_005: Repeated scalar/correlated subqueries in SELECT or WHERE
    for select in tree.find_all(exp.Select):
        scalar_subqueries: list[exp.Subquery] = []
        for proj in select.expressions:
            scalar_subqueries.extend(proj.find_all(exp.Subquery))
        where_node = select.args.get("where")
        if where_node is not None:
            scalar_subqueries.extend(where_node.find_all(exp.Subquery))
        if len(scalar_subqueries) >= 2:
            findings.append(
                _make_finding(
                    catalog,
                    "PERF_005",
                    file_path,
                    _find_line(raw_sql, "select"),
                    f"Detected {len(scalar_subqueries)} inline scalar/correlated subqueries; consolidate into a CTE.",
                )
            )
            break

    # PERF_006: ORDER BY without LIMIT inside CTEs, derived subqueries, or staging/views
    reported_order_issue = False
    for cte in tree.find_all(exp.CTE):
        if isinstance(cte.this, exp.Select) and cte.this.args.get("order") and not cte.this.args.get("limit"):
            findings.append(
                _make_finding(
                    catalog,
                    "PERF_006",
                    file_path,
                    _find_line(raw_sql, "order by"),
                    f"CTE '{cte.alias_or_name}' contains ORDER BY without LIMIT.",
                )
            )
            reported_order_issue = True
            break

    if not reported_order_issue:
        for subq in tree.find_all(exp.Subquery):
            if isinstance(subq.this, exp.Select) and subq.this.args.get("order") and not subq.this.args.get("limit"):
                findings.append(
                    _make_finding(
                        catalog,
                        "PERF_006",
                        file_path,
                        _find_line(raw_sql, "order by"),
                        "Subquery contains ORDER BY without LIMIT.",
                    )
                )
                reported_order_issue = True
                break

    if (
        not reported_order_issue
        and isinstance(tree, exp.Select)
        and (layer["is_staging"] or preprocessed.materialized == "view")
        and tree.args.get("order")
        and not tree.args.get("limit")
    ):
        findings.append(
            _make_finding(
                catalog,
                "PERF_006",
                file_path,
                _find_line(raw_sql, "order by"),
                "Non-final/view model contains ORDER BY without LIMIT.",
            )
        )

    # PERF_007: SELECT DISTINCT or UNION without ALL
    has_distinct = any(s.args.get("distinct") is not None for s in tree.find_all(exp.Select))
    has_distinct_union = any(u.args.get("distinct") is True for u in tree.find_all(exp.Union))
    if has_distinct or has_distinct_union:
        findings.append(
            _make_finding(
                catalog,
                "PERF_007",
                file_path,
                _find_line(raw_sql, "distinct" if has_distinct else "union"),
                "SELECT DISTINCT or UNION (without ALL) triggers full deduplication shuffles.",
            )
        )

    return findings


def _evaluate_modeling_rules(
    tree: exp.Expr,
    preprocessed: PreprocessedSql,
    file_path: str,
    layer: dict[str, bool],
    catalog: dict[str, RuleMetadata],
) -> list[AuditFinding]:
    """Evaluate MOD_001 through MOD_006 against one parsed SQL AST."""
    findings: list[AuditFinding] = []
    raw_sql = preprocessed.raw_sql
    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE) if cte.alias_or_name}

    # MOD_001: Hardcoded physical tables in dbt models
    if preprocessed.is_dbt_model:
        for table in tree.find_all(exp.Table):
            tname = table.name
            if not tname or tname.startswith(("__dge_ref__", "__dge_source__", "__dge_this__", "__dge_expr__")):
                continue
            has_qualifier = bool(table.db or table.catalog)
            if not has_qualifier and tname.lower() in cte_names:
                continue
            findings.append(
                _make_finding(
                    catalog,
                    "MOD_001",
                    file_path,
                    _find_line(raw_sql, tname),
                    f"Hardcoded table reference '{table.sql()}' in dbt model; use ref() or source().",
                    table.sql(),
                )
            )
            break

    # MOD_002: core/marts referencing source() directly
    if preprocessed.is_dbt_model and layer["is_core_or_mart"] and preprocessed.sources:
        src_pairs = ", ".join(f"{s}.{t}" for s, t in preprocessed.sources)
        findings.append(
            _make_finding(
                catalog,
                "MOD_002",
                file_path,
                _find_line(raw_sql, "source("),
                f"Core/mart model references source() directly ({src_pairs}); route via stg_* first.",
            )
        )

    # MOD_003: staging model containing JOIN or GROUP BY
    if layer["is_staging"]:
        has_join = any(True for _ in tree.find_all(exp.Join))
        has_group = any(True for _ in tree.find_all(exp.Group))
        if has_join or has_group:
            findings.append(
                _make_finding(
                    catalog,
                    "MOD_003",
                    file_path,
                    _find_line(raw_sql, "join" if has_join else "group by"),
                    "Staging model contains JOIN or GROUP BY; keep staging strictly 1:1 with source.",
                )
            )

    # MOD_004: canonical Medallion model prefix
    norm_path = file_path.replace("\\", "/").lower()
    is_regular_model_file = (
        preprocessed.is_dbt_model
        and norm_path.endswith(".sql")
        and not any(seg in norm_path for seg in ("/macros/", "/tests/", "/snapshots/", "/analyses/"))
    )
    if is_regular_model_file:
        stem = Path(norm_path).stem
        if not stem.startswith(("stg_", "int_", "dim_", "fct_", "mart_")):
            findings.append(
                _make_finding(
                    catalog,
                    "MOD_004",
                    file_path,
                    1,
                    f"Model '{stem}.sql' violates Medallion naming prefix (stg_, int_, dim_, fct_, mart_).",
                )
            )

    # MOD_005: deeply nested subqueries (depth >= 3)
    if _subquery_nesting_depth(tree) >= 3:
        findings.append(
            _make_finding(
                catalog,
                "MOD_005",
                file_path,
                _find_line(raw_sql, "from"),
                "Query uses subquery nesting depth >= 3; refactor into modular CTEs.",
            )
        )

    # MOD_006: numeric cast on canonical string keys
    for cast_node in tree.find_all(exp.Cast, exp.TryCast):
        target_type = cast_node.to
        if isinstance(target_type, exp.DataType) and target_type.this in NUMERIC_DTYPES:
            for col in cast_node.this.find_all(exp.Column):
                col_name = col.name
                if (
                    col_name
                    and CANONICAL_STRING_KEY_RE.search(col_name)
                    and not CANONICAL_EXCLUSION_RE.search(col_name)
                ):
                    findings.append(
                        _make_finding(
                            catalog,
                            "MOD_006",
                            file_path,
                            _find_line(raw_sql, col_name),
                            f"Numeric cast on canonical string identifier '{col_name}' risks stripping leading zeros.",
                            cast_node.sql(),
                        )
                    )
                    break

    return findings


def _evaluate_quality_sql_rules(
    tree: exp.Expr,
    preprocessed: PreprocessedSql,
    file_path: str,
    layer: dict[str, bool],
    catalog: dict[str, RuleMetadata],
) -> list[AuditFinding]:
    """Evaluate QUAL_004 and QUAL_005 against one parsed SQL AST."""
    findings: list[AuditFinding] = []
    raw_sql = preprocessed.raw_sql

    # QUAL_004: staging model without sentinel/whitespace sanitization
    if layer["is_staging"] and isinstance(tree, exp.Select):
        has_hygiene = any(
            True for _ in tree.find_all(exp.Nullif, exp.Coalesce, exp.Case, exp.If, exp.Trim)
        )
        if not has_hygiene and tree.expressions:
            findings.append(
                _make_finding(
                    catalog,
                    "QUAL_004",
                    file_path,
                    1,
                    "Staging model lacks explicit TRIM/NULLIF/COALESCE/CASE sentinel sanitization.",
                )
            )

    # QUAL_005: division without NULLIF(denom, 0) or SAFE_DIVIDE protection
    for div_node in tree.find_all(exp.Div):
        if div_node.args.get("safe"):
            continue
        denom = div_node.expression
        while isinstance(denom, exp.Paren):
            denom = denom.this
        if isinstance(denom, exp.Nullif) or any(True for _ in denom.find_all(exp.Nullif)):
            continue
        if isinstance(denom, exp.Literal) and not denom.is_string:
            try:
                if float(denom.name) != 0.0:
                    continue
            except ValueError:
                pass
        findings.append(
            _make_finding(
                catalog,
                "QUAL_005",
                file_path,
                _find_line(raw_sql, "/"),
                f"Unprotected division '{div_node.sql()}' lacks NULLIF(denominator, 0).",
                div_node.sql(),
            )
        )
        break

    return findings


def _evaluate_lgpd_sql_rules(
    tree: exp.Expr,
    preprocessed: PreprocessedSql,
    file_path: str,
    layer: dict[str, bool],
    catalog: dict[str, RuleMetadata],
) -> list[AuditFinding]:
    """Evaluate LGPD_001, LGPD_002, LGPD_004, LGPD_005, LGPD_006 on SQL AST."""
    findings: list[AuditFinding] = []
    raw_sql = preprocessed.raw_sql

    # Determine outermost Select for projection checks
    outer_select = tree if isinstance(tree, exp.Select) else None
    unmasked_pii_cols: list[str] = []

    if outer_select is not None:
        for proj in outer_select.expressions:
            if _is_masked_or_aggregated(proj):
                continue
            for col in proj.find_all(exp.Column):
                if _is_pii_column_name(col.name):
                    unmasked_pii_cols.append(col.name)

    # LGPD_001: unmasked PII projection
    if unmasked_pii_cols:
        cols_str = ", ".join(sorted(set(unmasked_pii_cols)))
        findings.append(
            _make_finding(
                catalog,
                "LGPD_001",
                file_path,
                _find_line(raw_sql, unmasked_pii_cols[0]),
                f"Unmasked PII column(s) projected without masking macro: {cols_str}.",
            )
        )

    # LGPD_006: exporting unmasked PII in Gold/marts
    if layer["is_mart"] and unmasked_pii_cols:
        cols_str = ", ".join(sorted(set(unmasked_pii_cols)))
        findings.append(
            _make_finding(
                catalog,
                "LGPD_006",
                file_path,
                _find_line(raw_sql, unmasked_pii_cols[0]),
                f"Gold/mart model exports unmasked PII ({cols_str}) without cohort anonymization.",
            )
        )

    # LGPD_002: plaintext PII in JOIN ON or GROUP BY
    pii_join_or_group: list[str] = []
    key_containers: list[exp.Expr] = [
        j.args["on"] for j in tree.find_all(exp.Join) if j.args.get("on") is not None
    ]
    key_containers.extend(tree.find_all(exp.Group))
    for container in key_containers:
        for col in container.find_all(exp.Column):
            if not _is_pii_column_name(col.name):
                continue
            parent = col.parent
            is_hashed = False
            while parent is not None and parent is not container:
                if isinstance(parent, (exp.SHA2, exp.SHA, exp.MD5)):
                    is_hashed = True
                    break
                if isinstance(parent, exp.Func):
                    fname = parent.sql_name().lower() if hasattr(parent, "sql_name") else ""
                    if fname in SAFE_MASKING_FUNCS:
                        is_hashed = True
                        break
                parent = parent.parent
            if not is_hashed:
                pii_join_or_group.append(col.name)

    if pii_join_or_group:
        cols_str = ", ".join(sorted(set(pii_join_or_group)))
        findings.append(
            _make_finding(
                catalog,
                "LGPD_002",
                file_path,
                _find_line(raw_sql, pii_join_or_group[0]),
                f"Plaintext PII column(s) used in JOIN or GROUP BY ({cols_str}); use surrogate hashes.",
            )
        )

    # LGPD_004: hardcoded credentials in SQL
    clean_no_comments = re.sub(r"\{#.*?#\}", "", raw_sql, flags=re.DOTALL)
    clean_no_comments = re.sub(r"--[^\n]*", "", clean_no_comments)
    for match in HARDCODED_SQL_SECRET_RE.finditer(clean_no_comments):
        literal = match.group(1)
        if "env_var" in literal or "__dge_env_var__" in literal:
            continue
        findings.append(
            _make_finding(
                catalog,
                "LGPD_004",
                file_path,
                _find_line(raw_sql, match.group(0)),
                "Hardcoded secret, password, or token literal detected in SQL.",
            )
        )
        break

    # LGPD_005: unsafe dynamic SQL or raw var interpolation
    has_exec_concat = bool(EXECUTE_IMMEDIATE_RE.search(clean_no_comments)) and (
        "||" in clean_no_comments
        or "+" in clean_no_comments
        or "CONCAT(" in clean_no_comments.upper()
        or preprocessed.has_raw_var_interpolation
    )
    if has_exec_concat or preprocessed.has_raw_var_interpolation:
        findings.append(
            _make_finding(
                catalog,
                "LGPD_005",
                file_path,
                _find_line(raw_sql, "EXECUTE IMMEDIATE" if has_exec_concat else "var("),
                "Unsafe dynamic SQL concatenation or unquoted Jinja variable interpolation detected.",
            )
        )

    return findings


def evaluate_sql_document(
    preprocessed: PreprocessedSql,
    dialect: str,
    file_path: str,
    catalog: dict[str, RuleMetadata],
) -> tuple[list[AuditFinding], str | None]:
    """Parse sanitized SQL via sqlglot and evaluate all 19 SQL/dbt rules."""
    sql_body = preprocessed.sanitized_sql.strip()
    if not sql_body:
        return [], None

    try:
        trees = sqlglot.parse(sql_body, read=dialect, error_level=sqlglot.ErrorLevel.IGNORE)
    except Exception as exc:  # noqa: BLE001
        return [], f"SQL parse error ({dialect}): {exc}"

    layer = _infer_layer(file_path)
    findings: list[AuditFinding] = []
    seen_keys: set[tuple[str, int, str]] = set()

    for tree in trees:
        if tree is None:
            continue
        batch = [
            *_evaluate_performance_rules(tree, preprocessed, file_path, layer, catalog),
            *_evaluate_modeling_rules(tree, preprocessed, file_path, layer, catalog),
            *_evaluate_quality_sql_rules(tree, preprocessed, file_path, layer, catalog),
            *_evaluate_lgpd_sql_rules(tree, preprocessed, file_path, layer, catalog),
        ]
        for finding in batch:
            key = (finding.rule_id, finding.line, finding.message)
            if key not in seen_keys:
                seen_keys.add(key)
                findings.append(finding)

    return findings, None
