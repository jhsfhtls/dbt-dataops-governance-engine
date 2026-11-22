"""Integration tests for the synthetic reference dbt project, portable macros, and docs linter."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb

from dbt_dataops_governance.auditor import AuditEngine, Severity

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = REPO_ROOT / "dbt"
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _dbt_executable() -> str:
    """Locate the dbt CLI executable in the active Python environment."""
    exe_name = "dbt.exe" if sys.platform == "win32" else "dbt"
    candidate = Path(sys.executable).resolve().parent / exe_name
    if candidate.is_file():
        return str(candidate)
    resolved = shutil.which("dbt")
    if resolved:
        return resolved
    raise FileNotFoundError("dbt executable not found in active Python environment.")


def test_reference_dbt_builds_passes_lint_and_masks_pii(tmp_path: Path) -> None:
    """Reference dbt project compiles, passes dbt build/tests/unit tests, lint_dbt_docs, and PII masking."""
    dbt_bin = _dbt_executable()
    isolated_db = tmp_path / "ref_test.duckdb"
    isolated_target = tmp_path / "target"
    isolated_target.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["DGE_DUCKDB_PATH"] = isolated_db.as_posix()

    build = subprocess.run(
        [
            dbt_bin,
            "build",
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(DBT_DIR),
            "--target-path",
            str(isolated_target),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, f"dbt build failed:\n{build.stdout}\n{build.stderr}"

    docs = subprocess.run(
        [
            dbt_bin,
            "docs",
            "generate",
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(DBT_DIR),
            "--target-path",
            str(isolated_target),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert docs.returncode == 0, f"dbt docs generate failed:\n{docs.stdout}\n{docs.stderr}"

    lint = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "lint_dbt_docs.py"),
            "--manifest",
            str(isolated_target / "manifest.json"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert lint.returncode == 0, f"lint_dbt_docs failed:\n{lint.stdout}\n{lint.stderr}"

    # Verify PII masking, leading-zero preservation, and mart cohort aggregation in DuckDB
    with duckdb.connect(str(isolated_db), read_only=True) as conn:
        cust_rows = conn.execute(
            "SELECT customer_id, cpf_masked, email_masked, phone_masked, postal_code, customer_segment "
            "FROM dim_customers ORDER BY customer_id"
        ).fetchall()
        mart_rows = conn.execute(
            "SELECT customer_segment, order_count, total_net_usd "
            "FROM mart_revenue_by_segment ORDER BY customer_segment, order_date"
        ).fetchall()

    assert len(cust_rows) == 5
    first = cust_rows[0]
    assert first[0] == "cust_001"
    assert "00011122233" not in first[1] and first[1].startswith("***")
    assert "user1@" not in first[2] and first[2] == "***@example.invalid"
    assert first[3] == "****-0001"
    assert first[4] == "01310100"  # leading zero preserved
    assert cust_rows[3][5] == "UNCLASSIFIED"  # sentinel 'N/A' normalized
    assert len(mart_rows) >= 3


def test_reference_dbt_models_pass_audit_engine_without_severe_findings() -> None:
    """Reference dbt models emit zero CRITICAL or HIGH findings under AuditEngine."""
    summary = AuditEngine().audit_path(DBT_DIR / "models", dialect="duckdb")
    severe = [f for f in summary.findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
    assert severe == [], f"Unexpected severe audit findings in dbt/models: {severe}"
