"""Tests for SQLFluff lint, Slim CI state:modified+ runner, and GitHub workflows."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = REPO_ROOT / "dbt"
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _venv_executable(name: str) -> str:
    """Locate a CLI executable inside the active Python environment."""
    exe_name = f"{name}.exe" if sys.platform == "win32" else name
    candidate = Path(sys.executable).resolve().parent / exe_name
    if candidate.is_file():
        return str(candidate)
    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise FileNotFoundError(f"Executable '{name}' not found in active Python environment.")


def test_sqlfluff_lint_passes_on_reference_dbt_models() -> None:
    """SQLFluff with jinja templater passes cleanly on dbt/models."""
    sqlfluff_bin = _venv_executable("sqlfluff")
    res = subprocess.run(
        [sqlfluff_bin, "lint", "dbt/models"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"SQLFluff lint failed:\n{res.stdout}\n{res.stderr}"


def test_slim_ci_skips_unchanged_and_rebuilds_only_modified_models(tmp_path: Path) -> None:
    """Slim CI runner skips unmodified graphs and selectively builds state:modified+."""
    dbt_bin = _venv_executable("dbt")
    baseline_dir = tmp_path / "baseline" / "dbt"
    shutil.copytree(DBT_DIR, baseline_dir, ignore=shutil.ignore_patterns("target", "logs", ".user.yml"))
    baseline_target = baseline_dir / "target"
    baseline_target.mkdir(parents=True, exist_ok=True)
    baseline_db = baseline_target / "dge_reference.duckdb"

    base_env = os.environ.copy()
    base_env["DGE_DUCKDB_PATH"] = baseline_db.as_posix()

    build_base = subprocess.run(
        [
            dbt_bin,
            "build",
            "--project-dir",
            str(baseline_dir),
            "--profiles-dir",
            str(baseline_dir),
            "--target-path",
            str(baseline_target),
        ],
        env=base_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build_base.returncode == 0, f"Baseline build failed:\n{build_base.stdout}\n{build_base.stderr}"

    # 1. Unmodified copy -> Slim CI detects 0 modified nodes and skips cleanly
    unchanged_dir = tmp_path / "unchanged" / "dbt"
    shutil.copytree(DBT_DIR, unchanged_dir, ignore=shutil.ignore_patterns("target", "logs", ".user.yml"))
    unchanged_db = tmp_path / "unchanged" / "work.duckdb"
    skip_res = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "run_slim_ci.py"),
            "--dbt-dir",
            str(unchanged_dir),
            "--state-dir",
            str(baseline_target),
            "--duckdb-path",
            str(unchanged_db),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert skip_res.returncode == 0, skip_res.stderr
    assert "No modified dbt nodes detected; skipping build." in skip_res.stdout

    # 2. Modified mart -> Slim CI selects mart_revenue_by_segment only (not stg_synthetic__customers)
    modified_dir = tmp_path / "modified" / "dbt"
    shutil.copytree(DBT_DIR, modified_dir, ignore=shutil.ignore_patterns("target", "logs", ".user.yml"))
    mart_file = modified_dir / "models" / "marts" / "mart_revenue_by_segment.sql"
    mart_file.write_text(
        mart_file.read_text(encoding="utf-8") + "\n-- slim_ci_test_delta\n",
        encoding="utf-8",
        newline="\n",
    )
    modified_db = tmp_path / "modified" / "work.duckdb"

    slim_res = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "run_slim_ci.py"),
            "--dbt-dir",
            str(modified_dir),
            "--state-dir",
            str(baseline_target),
            "--duckdb-path",
            str(modified_db),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert slim_res.returncode == 0, f"Slim CI selective run failed:\n{slim_res.stdout}\n{slim_res.stderr}"
    assert "mart_revenue_by_segment" in slim_res.stdout
    assert "stg_synthetic__customers" not in slim_res.stdout


def test_slim_ci_and_pages_workflows_are_valid_yaml() -> None:
    """Validate GitHub Actions YAML structure for Slim CI and dbt docs Pages deployment."""
    slim_wf = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "slim-ci.yml").read_text(encoding="utf-8")
    )
    pages_wf = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "dbt-docs-pages.yml").read_text(encoding="utf-8")
    )

    assert "slim-ci-dbt" in slim_wf["jobs"]
    assert pages_wf["permissions"]["pages"] == "write"
    assert pages_wf["permissions"]["id-token"] == "write"
    assert "build-and-deploy" in pages_wf["jobs"]
