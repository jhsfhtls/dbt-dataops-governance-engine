"""Domain models for multi-cloud SQL transpilation and incremental optimization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TranspileLimitation:
    """Explicit dialect feature gap or semantic caveat detected during transpilation."""

    code: str
    feature: str
    source_dialect: str
    target_dialect: str
    severity: str
    description: str
    workaround: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize limitation entry to a JSON-friendly dictionary."""
        return {
            "code": self.code,
            "feature": self.feature,
            "source_dialect": self.source_dialect,
            "target_dialect": self.target_dialect,
            "severity": self.severity,
            "description": self.description,
            "workaround": self.workaround,
        }


@dataclass(frozen=True)
class TranspileResult:
    """Output of a multi-cloud SQL/dbt transpilation operation."""

    source_dialect: str
    target_dialect: str
    source_sql: str
    transpiled_sql: str
    dbt_jinja_preserved: bool
    warnings: list[str] = field(default_factory=list)
    limitations: list[TranspileLimitation] = field(default_factory=list)
    roundtrip_equivalent: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize transpilation result to a JSON-friendly dictionary."""
        return {
            "source_dialect": self.source_dialect,
            "target_dialect": self.target_dialect,
            "source_sql": self.source_sql,
            "transpiled_sql": self.transpiled_sql,
            "dbt_jinja_preserved": self.dbt_jinja_preserved,
            "warnings": list(self.warnings),
            "limitations": [lim.to_dict() for lim in self.limitations],
            "roundtrip_equivalent": self.roundtrip_equivalent,
        }


@dataclass(frozen=True)
class IncrementalSuggestion:
    """Advisory recommendation for converting a full-refresh SQL/dbt model to incremental."""

    model_name: str
    target_dialect: str
    already_incremental: bool
    recommended_strategy: str
    unique_key: str
    watermark_column: str
    lookback_days: int
    on_schema_change: str
    confidence: str
    rationale: str
    suggested_sql: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize incremental suggestion to a JSON-friendly dictionary."""
        return {
            "model_name": self.model_name,
            "target_dialect": self.target_dialect,
            "already_incremental": self.already_incremental,
            "recommended_strategy": self.recommended_strategy,
            "unique_key": self.unique_key,
            "watermark_column": self.watermark_column,
            "lookback_days": self.lookback_days,
            "on_schema_change": self.on_schema_change,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "suggested_sql": self.suggested_sql,
            "warnings": list(self.warnings),
        }
