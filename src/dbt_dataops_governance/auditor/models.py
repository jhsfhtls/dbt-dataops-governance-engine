"""Domain models and deterministic Scorecard calculation for static AST audits."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    """Rule severity levels aligned with catalog/governance_rules.yaml."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


SEVERITY_PENALTIES: dict[Severity, float] = {
    Severity.CRITICAL: 15.0,
    Severity.HIGH: 8.0,
    Severity.MEDIUM: 4.0,
    Severity.LOW: 1.0,
}

ALL_FAMILIES = (
    "PERFORMANCE_FINOPS",
    "MODELING_MEDALLION",
    "QUALITY_CONTRACTS",
    "LGPD_PII_SECURITY",
)


@dataclass(frozen=True)
class RuleMetadata:
    """Declarative metadata loaded from catalog/governance_rules.yaml."""

    rule_id: str
    name: str
    family: str
    severity: Severity
    dialects: tuple[str, ...]
    applies_to: tuple[str, ...]
    rationale: str
    remediation: str
    known_false_positives: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditFinding:
    """Single deterministic governance rule violation detected by static analysis."""

    rule_id: str
    rule_name: str
    family: str
    severity: Severity
    file_path: str
    line: int
    message: str
    remediation: str
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize finding to a JSON-friendly dictionary."""
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "family": self.family,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line": self.line,
            "message": self.message,
            "remediation": self.remediation,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class AuditSummary:
    """Aggregated audit Scorecard, FinOps/LGPD risk assessment, and findings."""

    target_path: str
    dialect: str
    files_audited: int
    score: float
    grade: str
    finops_risk_level: str
    lgpd_risk_level: str
    counts_by_severity: dict[str, int]
    counts_by_family: dict[str, int]
    findings: list[AuditFinding] = field(default_factory=list)
    parse_errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize full audit summary to a JSON-friendly dictionary."""
        return {
            "target_path": self.target_path,
            "dialect": self.dialect,
            "files_audited": self.files_audited,
            "score": self.score,
            "grade": self.grade,
            "finops_risk_level": self.finops_risk_level,
            "lgpd_risk_level": self.lgpd_risk_level,
            "total_findings": len(self.findings),
            "counts_by_severity": self.counts_by_severity,
            "counts_by_family": self.counts_by_family,
            "findings": [finding.to_dict() for finding in self.findings],
            "parse_errors": self.parse_errors,
        }


def _compute_grade(score: float) -> str:
    """Map numeric Scorecard (0-100) to letter grade."""
    if score >= 90.0:
        return "A"
    if score >= 80.0:
        return "B"
    if score >= 70.0:
        return "C"
    if score >= 55.0:
        return "D"
    return "F"


def _compute_family_risk(findings: list[AuditFinding], family: str) -> str:
    """Determine FinOps or LGPD risk rating from family findings."""
    fam_findings = [f for f in findings if f.family == family]
    if not fam_findings:
        return "LOW"

    criticals = sum(1 for f in fam_findings if f.severity == Severity.CRITICAL)
    highs = sum(1 for f in fam_findings if f.severity == Severity.HIGH)
    mediums = sum(1 for f in fam_findings if f.severity == Severity.MEDIUM)

    if criticals >= 1 or highs >= 2:
        return "CRITICAL"
    if highs >= 1 or mediums >= 2:
        return "HIGH"
    return "MEDIUM"


def build_audit_summary(
    target_path: str,
    dialect: str,
    files_audited: int,
    findings: list[AuditFinding],
    parse_errors: list[dict[str, str]] | None = None,
) -> AuditSummary:
    """Compute Scorecard, letter grade, risk bands, and summary counters."""
    sorted_findings = sorted(
        findings,
        key=lambda f: (f.file_path, f.line, f.rule_id, f.message),
    )
    penalty = sum(SEVERITY_PENALTIES[f.severity] for f in sorted_findings)
    score = round(max(0.0, min(100.0, 100.0 - penalty)), 2)

    counts_by_severity = {
        sev.value: sum(1 for f in sorted_findings if f.severity == sev)
        for sev in Severity
    }
    counts_by_family = {
        fam: sum(1 for f in sorted_findings if f.family == fam)
        for fam in ALL_FAMILIES
    }

    return AuditSummary(
        target_path=target_path,
        dialect=dialect,
        files_audited=files_audited,
        score=score,
        grade=_compute_grade(score),
        finops_risk_level=_compute_family_risk(sorted_findings, "PERFORMANCE_FINOPS"),
        lgpd_risk_level=_compute_family_risk(sorted_findings, "LGPD_PII_SECURITY"),
        counts_by_severity=counts_by_severity,
        counts_by_family=counts_by_family,
        findings=sorted_findings,
        parse_errors=parse_errors or [],
    )
