"""FastAPI REST gateway package for dbt-dataops-governance-engine."""

from dbt_dataops_governance.api.app import create_app

__all__ = ["create_app"]
