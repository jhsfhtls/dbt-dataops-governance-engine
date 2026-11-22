"""Markdown and JSON report formatters for static AST audit summaries."""

from __future__ import annotations

import json

from dbt_dataops_governance.auditor.models import AuditSummary


def render_json_report(summary: AuditSummary) -> str:
    """Render deterministic indented JSON report."""
    return json.dumps(summary.to_dict(), indent=2, ensure_ascii=False) + "\n"


def render_markdown_report(summary: AuditSummary) -> str:
    """Render an executive Markdown Scorecard and FinOps/LGPD risk report."""
    lines: list[str] = [
        "# dbt DataOps Governance Audit Report",
        "",
        "## Executive Scorecard",
        "",
        f"- **Target Audited:** `{summary.target_path}`",
        f"- **SQL Dialect:** `{summary.dialect}`",
        f"- **Files Audited:** `{summary.files_audited}`",
        f"- **Governance Score:** **{summary.score:.1f} / 100.0** (Grade **{summary.grade}**)",
        f"- **FinOps Risk Level:** `{summary.finops_risk_level}`",
        f"- **LGPD / Security Risk Level:** `{summary.lgpd_risk_level}`",
        f"- **Total Findings:** **{len(summary.findings)}**",
        "",
        "### Severity Breakdown",
        "",
        "| Severity | Count |",
        "| :--- | :---: |",
    ]
    for sev, count in summary.counts_by_severity.items():
        lines.append(f"| `{sev}` | {count} |")

    lines.extend([
        "",
        "### Family Breakdown",
        "",
        "| Family | Count |",
        "| :--- | :---: |",
    ])
    for fam, count in summary.counts_by_family.items():
        lines.append(f"| `{fam}` | {count} |")

    lines.extend(["", "## Findings", ""])
    if not summary.findings:
        lines.append("No governance violations detected.")
    else:
        lines.extend([
            "| Rule ID | Severity | File | Line | Message | Remediation |",
            "| :--- | :---: | :--- | :---: | :--- | :--- |",
        ])
        for f in summary.findings:
            msg = f.message.replace("|", "\\|")
            rem = f.remediation.replace("|", "\\|")
            lines.append(
                f"| `{f.rule_id}` | `{f.severity.value}` | `{f.file_path}` | {f.line} | {msg} | {rem} |"
            )

    if summary.parse_errors:
        lines.extend(["", "## Parse Errors", ""])
        for err in summary.parse_errors:
            lines.append(f"- `{err['file_path']}`: {err['error']}")

    lines.append("")
    return "\n".join(lines)
