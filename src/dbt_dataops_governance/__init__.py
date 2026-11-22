"""dbt-dataops-governance-engine package root."""

from dbt_dataops_governance.auditor import AuditEngine

__version__ = "0.1.0"

__all__ = ["AuditEngine", "__version__"]
