"""Slim CI runner executing dbt build --select state:modified+ against a baseline manifest."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DBT_DIR = REPO_ROOT / "dbt"


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


def _copy_baseline_db_if_needed(
    state_dir: Path,
    dbt_dir: Path,
    duckdb_path: Path | None,
) -> dict[str, str]:
    """Copy baseline DuckDB warehouse file so upstream unselected models exist for Slim CI."""
    env = os.environ.copy()
    target_db = duckdb_path or (dbt_dir / "target" / "dge_reference.duckdb")
    target_db.parent.mkdir(parents=True, exist_ok=True)

    baseline_db = state_dir / "dge_reference.duckdb"
    if baseline_db.is_file() and not target_db.is_file():
        shutil.copy2(baseline_db, target_db)

    if duckdb_path is not None:
        env["DGE_DUCKDB_PATH"] = duckdb_path.as_posix()
    return env


def run_slim_ci(
    dbt_dir: Path,
    state_dir: Path | None = None,
    duckdb_path: Path | None = None,
) -> int:
    """Run state:modified+ dbt build when baseline manifest exists, else full dbt build."""
    dbt_bin = _dbt_executable()
    resolved_dbt = dbt_dir.resolve()
    (resolved_dbt / "target").mkdir(parents=True, exist_ok=True)

    manifest_file = (state_dir / "manifest.json") if state_dir is not None else None
    if manifest_file is None or not manifest_file.is_file():
        print("[SLIM CI] No baseline manifest.json found; falling back to full dbt build.")
        env = os.environ.copy()
        if duckdb_path is not None:
            env["DGE_DUCKDB_PATH"] = duckdb_path.as_posix()
        res = subprocess.run(
            [
                dbt_bin,
                "build",
                "--project-dir",
                str(resolved_dbt),
                "--profiles-dir",
                str(resolved_dbt),
            ],
            env=env,
            check=False,
        )
        return res.returncode

    resolved_state = state_dir.resolve()  # type: ignore[union-attr]
    env = _copy_baseline_db_if_needed(resolved_state, resolved_dbt, duckdb_path)

    ls_res = subprocess.run(
        [
            dbt_bin,
            "ls",
            "--project-dir",
            str(resolved_dbt),
            "--profiles-dir",
            str(resolved_dbt),
            "--select",
            "state:modified+",
            "--state",
            str(resolved_state),
            "--output",
            "name",
            "--quiet",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if ls_res.returncode != 0:
        print(f"[ERROR] dbt ls failed:\n{ls_res.stdout}\n{ls_res.stderr}", file=sys.stderr)
        return ls_res.returncode

    selected = [line.strip() for line in ls_res.stdout.splitlines() if line.strip()]
    if not selected:
        print("[SLIM CI] No modified dbt nodes detected; skipping build.")
        return 0

    print(f"[SLIM CI] Selected {len(selected)} modified node(s): {', '.join(selected)}")
    build_res = subprocess.run(
        [
            dbt_bin,
            "build",
            "--project-dir",
            str(resolved_dbt),
            "--profiles-dir",
            str(resolved_dbt),
            "--select",
            "state:modified+",
            "--state",
            str(resolved_state),
        ],
        env=env,
        check=False,
    )
    return build_res.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for Slim CI runner."""
    parser = argparse.ArgumentParser(description="Run dbt Slim CI (state:modified+).")
    parser.add_argument("--dbt-dir", type=Path, default=DEFAULT_DBT_DIR, help="Path to dbt project.")
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Path containing baseline manifest.json (and optional dge_reference.duckdb).",
    )
    parser.add_argument(
        "--duckdb-path",
        type=Path,
        default=None,
        help="Optional override path for DGE_DUCKDB_PATH.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for Slim CI execution."""
    args = parse_args(argv)
    return run_slim_ci(
        dbt_dir=args.dbt_dir,
        state_dir=args.state_dir,
        duckdb_path=args.duckdb_path,
    )


if __name__ == "__main__":
    sys.exit(main())
