"""Deterministic foundation, governance catalog, and packaging tests."""

from __future__ import annotations

import copy
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import dbt_dataops_governance

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_catalog import load_catalog, validate_catalog  # noqa: E402


def test_package_version_is_defined() -> None:
    """Package root exposes semantic version string."""
    assert dbt_dataops_governance.__version__ == "0.1.0"


def test_governance_catalog_validates_25_rules_across_4_families() -> None:
    """Catalog schema validator passes with exact expected family counts."""
    catalog = load_catalog(REPO_ROOT / "catalog" / "governance_rules.yaml")
    family_counts, severity_counts = validate_catalog(catalog)

    assert sum(family_counts.values()) == 25
    assert dict(family_counts) == {
        "PERFORMANCE_FINOPS": 7,
        "MODELING_MEDALLION": 6,
        "QUALITY_CONTRACTS": 6,
        "LGPD_PII_SECURITY": 6,
    }
    assert sum(severity_counts.values()) == 25


def test_governance_catalog_rejects_malformed_input() -> None:
    """Catalog schema validator fails fast on missing rule count or bad severity."""
    catalog = load_catalog(REPO_ROOT / "catalog" / "governance_rules.yaml")
    broken = copy.deepcopy(catalog)
    broken["rules"].pop()

    with pytest.raises(ValueError, match="Expected exactly 25 rules"):
        validate_catalog(broken)


def test_render_catalog_check_passes() -> None:
    """CATALOG.md matches deterministic output from YAML registries."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "render_catalog.py"), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_render_progress_check_passes() -> None:
    """JORNADA_IMPLEMENTACAO.md matches deterministic output from state and catalogs."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "render_progress.py"), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_gitignore_enforces_shield_and_env_isolation() -> None:
    """Public repository .gitignore retains AI SATELLITE SHIELD and .env exclusions."""
    gitignore_text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "# --- AI SATELLITE SHIELD (DO NOT REMOVE) ---" in gitignore_text
    assert ".env" in gitignore_text
    assert ".agents/" in gitignore_text
    assert "CLAUDE.md" in gitignore_text


def test_dependencies_are_strictly_pinned() -> None:
    """All dependencies in requirements files and pyproject.toml use exact == pins."""
    for req_file in ("requirements.txt", "requirements-dev.txt"):
        lines = (REPO_ROOT / req_file).read_text(encoding="utf-8").splitlines()
        non_empty = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        assert non_empty, f"{req_file} must not be empty."
        for dep in non_empty:
            assert "==" in dep, f"Unpinned dependency in {req_file}: {dep}"
            assert not any(op in dep for op in (">=", "<=", "~=")), f"Range specifier disallowed: {dep}"

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = pyproject["project"]["dependencies"]
    assert deps, "pyproject.toml project.dependencies must not be empty."
    for dep in deps:
        assert "==" in dep, f"Unpinned dependency in pyproject.toml: {dep}"
        assert not any(op in dep for op in (">=", "<=", "~=")), f"Range specifier disallowed: {dep}"
