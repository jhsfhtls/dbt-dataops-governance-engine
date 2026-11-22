"""Automated Medallion scaffolder and ODCS v3.1 contract generator."""

from dbt_dataops_governance.scaffolder.engine import MedallionScaffolder
from dbt_dataops_governance.scaffolder.models import ColumnSpec, ScaffoldResult, TableSpec
from dbt_dataops_governance.scaffolder.path_guard import ScaffoldPathError

__all__ = [
    "ColumnSpec",
    "MedallionScaffolder",
    "ScaffoldPathError",
    "ScaffoldResult",
    "TableSpec",
]
