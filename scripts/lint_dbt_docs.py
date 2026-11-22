"""Linter enforcing 100% model and column documentation coverage in the reference dbt project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "dbt" / "target" / "manifest.json"


def lint_manifest(manifest_path: Path, project_prefix: str = "model.dge_reference.") -> int:
    """Validate 100% model and column documentation coverage in a dbt manifest.json."""
    if not manifest_path.is_file():
        print(
            f"[ERROR] dbt manifest not found at {manifest_path}. Run 'dbt docs generate' first.",
            file=sys.stderr,
        )
        return 1

    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    nodes = manifest.get("nodes", {})
    sources = manifest.get("sources", {})

    total_models = 0
    total_columns = 0
    undocumented_models: list[str] = []
    models_without_columns: list[str] = []
    undocumented_columns: list[str] = []

    for unique_id, node in sorted(nodes.items()):
        if not unique_id.startswith(project_prefix):
            continue

        model_name = str(node.get("name", unique_id))
        total_models += 1

        if not str(node.get("description", "")).strip():
            undocumented_models.append(model_name)

        columns = node.get("columns", {})
        if not columns:
            models_without_columns.append(model_name)
            continue

        for col_name, col_meta in sorted(columns.items()):
            total_columns += 1
            if not str(col_meta.get("description", "")).strip():
                undocumented_columns.append(f"{model_name}.{col_name}")

    print("=================================================================")
    print("dbt Documentation & Metadata Governance Linter (ODCS v3.1)")
    print("=================================================================")
    print(f"Manifest Path:           {manifest_path}")
    print(f"Total Models Evaluated:  {total_models}")
    print(f"Total Columns Evaluated: {total_columns}")
    print(f"Total Sources Evaluated: {len(sources)}")

    has_errors = total_models == 0

    if total_models == 0:
        print("\n[FAIL] Zero dbt models found in manifest.", file=sys.stderr)

    if undocumented_models:
        print(f"\n[FAIL] Found {len(undocumented_models)} undocumented models:", file=sys.stderr)
        for model in undocumented_models:
            print(f"  - {model}", file=sys.stderr)
        has_errors = True

    if models_without_columns:
        print(f"\n[FAIL] Found {len(models_without_columns)} models with no documented columns:", file=sys.stderr)
        for model in models_without_columns:
            print(f"  - {model}", file=sys.stderr)
        has_errors = True

    if undocumented_columns:
        print(f"\n[FAIL] Found {len(undocumented_columns)} undocumented columns:", file=sys.stderr)
        for col in undocumented_columns:
            print(f"  - {col}", file=sys.stderr)
        has_errors = True

    if has_errors:
        print("\nResult: REJECTED - 100% model and column documentation coverage is mandatory.", file=sys.stderr)
        return 1

    print("\nResult: APPROVED - 100% Documentation Coverage across all models and columns!")
    print("=================================================================")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for dbt documentation coverage linting."""
    parser = argparse.ArgumentParser(description="Enforce 100% dbt model and column documentation.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to dbt target/manifest.json",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for dbt documentation coverage verification."""
    args = parse_args(argv)
    return lint_manifest(args.manifest)


if __name__ == "__main__":
    sys.exit(main())
