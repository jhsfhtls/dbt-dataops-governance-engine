"""Command-line interface (dge) for audit, scaffold, transpile, lineage, and rules."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from dbt_dataops_governance.auditor import ClientPathShieldError
from dbt_dataops_governance.scaffolder import ScaffoldPathError
from dbt_dataops_governance.sdk import DbtGovernance


def _build_parser() -> argparse.ArgumentParser:
    """Construct argument parser for the dge CLI."""
    parser = argparse.ArgumentParser(
        prog="dge",
        description="dbt-dataops-governance-engine CLI (audit, scaffold, transpile, lineage, rules).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # dge audit
    p_audit = sub.add_parser("audit", help="Run static SQL/dbt AST audit (zero SQL execution).")
    p_audit.add_argument("target", type=Path, help="SQL/YAML file or directory to audit.")
    p_audit.add_argument("--dialect", default="duckdb", help="SQL dialect (duckdb, snowflake, spark, bigquery).")
    p_audit.add_argument("--output", type=Path, default=None, help="Optional output report file path.")
    p_audit.add_argument("--format", choices=["json", "markdown"], default="json", help="Output format.")

    # dge scaffold
    p_scaf = sub.add_parser("scaffold", help="Generate Medallion dbt project & ODCS v3.1 contract.")
    p_scaf.add_argument("input_source", help="Path to Parquet/CSV/DuckDB file or CREATE TABLE DDL string.")
    p_scaf.add_argument("--output-dir", type=Path, required=True, help="Explicit output directory.")
    p_scaf.add_argument("--source-type", default=None, help="Source type (parquet, csv, duckdb, ddl).")
    p_scaf.add_argument("--project-name", default="scaffolded_lakehouse", help="dbt project name.")
    p_scaf.add_argument("--source-name", default=None, help="dbt source name.")
    p_scaf.add_argument("--table-name", default=None, help="Target table name.")
    p_scaf.add_argument("--dialect", default="duckdb", help="DDL dialect.")
    p_scaf.add_argument("--entity-kind", choices=["dim", "fct"], default=None, help="Entity kind override.")

    # dge transpile
    p_tr = sub.add_parser("transpile", help="Transpile SQL/dbt across DuckDB, Spark SQL, Snowflake, BigQuery.")
    tr_group = p_tr.add_mutually_exclusive_group(required=True)
    tr_group.add_argument("--sql", help="Inline SQL string to transpile.")
    tr_group.add_argument("--file", type=Path, help="Path to SQL/dbt file to transpile.")
    p_tr.add_argument("--source", required=True, help="Source dialect.")
    p_tr.add_argument("--target", required=True, help="Target dialect.")
    p_tr.add_argument("--roundtrip", action="store_true", help="Validate AST round-trip equivalence.")
    p_tr.add_argument("--format", choices=["json", "sql"], default="json", help="Output format.")

    # dge lineage
    p_lin = sub.add_parser("lineage", help="Extract dbt/SQL lineage graph and Mermaid diagram.")
    p_lin.add_argument("target", type=Path, help="dbt models directory or SQL file.")
    p_lin.add_argument("--format", choices=["json", "mermaid"], default="json", help="Output format.")

    # dge rules
    p_rules = sub.add_parser("rules", help="List 25 governance rules from the catalog.")
    p_rules.add_argument("--family", default=None, help="Filter by family ID.")
    p_rules.add_argument("--severity", default=None, help="Filter by severity (CRITICAL, HIGH, MEDIUM, LOW).")
    p_rules.add_argument("--dialect", default=None, help="Filter by dialect.")
    p_rules.add_argument("--format", choices=["json", "table"], default="json", help="Output format.")

    return parser


def main(argv: Sequence[str] | None = None, governance: DbtGovernance | None = None) -> int:
    """Execute dge CLI command and return process exit code."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    gov = governance or DbtGovernance()

    try:
        if args.command == "audit":
            result = gov.audit(
                args.target,
                dialect=args.dialect,
                output_path=args.output,
                output_format=args.format,
            )
            if args.format == "json":
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(
                    f"Score: {result['score']} ({result['grade']}) | "
                    f"FinOps: {result['finops_risk_level']} | "
                    f"LGPD: {result['lgpd_risk_level']} | "
                    f"Findings: {result['total_findings']}"
                )
            return 0

        if args.command == "scaffold":
            result = gov.scaffold(
                args.input_source,
                output_dir=args.output_dir,
                source_type=args.source_type,
                project_name=args.project_name,
                source_name=args.source_name,
                table_name=args.table_name,
                dialect=args.dialect,
                entity_kind=args.entity_kind,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "transpile":
            raw_sql = args.sql if args.sql is not None else args.file.read_text(encoding="utf-8")
            result = gov.transpile(
                raw_sql,
                source_dialect=args.source,
                target_dialect=args.target,
                check_roundtrip=args.roundtrip,
            )
            if args.format == "sql":
                print(result["transpiled_sql"])
            else:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "lineage":
            result = gov.lineage(args.target)
            if args.format == "mermaid":
                print(result["mermaid"])
            else:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

        if args.command == "rules":
            rules = gov.list_rules(
                family=args.family,
                severity=args.severity,
                dialect=args.dialect,
            )
            if args.format == "table":
                for rule in rules:
                    print(f"{rule['id']:<10} {rule['severity']:<8} {rule['family']:<20} {rule['name']}")
            else:
                print(json.dumps({"total": len(rules), "rules": rules}, indent=2, ensure_ascii=False))
            return 0

    except (ClientPathShieldError, ScaffoldPathError) as exc:
        print(f"[SECURITY ERROR] {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
