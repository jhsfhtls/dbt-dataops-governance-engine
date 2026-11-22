"""Explicit output directory validation and path-traversal protection for scaffolder."""

from __future__ import annotations

from pathlib import Path


class ScaffoldPathError(ValueError):
    """Raised when scaffold output path is empty or attempts directory traversal."""


def validate_output_dir(output_dir: Path | str) -> Path:
    """Validate that output_dir is explicitly specified without traversal segments."""
    raw = str(output_dir).strip()
    if not raw:
        raise ScaffoldPathError("Explicit output_dir must be provided and non-empty.")

    candidate = Path(raw)
    if ".." in candidate.parts:
        raise ScaffoldPathError(
            f"Path traversal segment ('..') is forbidden in output_dir: {output_dir}"
        )

    return candidate.resolve()


def safe_join(base_dir: Path, *relative_parts: str) -> Path:
    """Safely join relative path segments under base_dir, rejecting escapes."""
    resolved_base = base_dir.resolve()
    rel = Path(*relative_parts)
    if rel.is_absolute() or ".." in rel.parts:
        raise ScaffoldPathError(
            f"Unsafe relative path component for scaffold target: {rel}"
        )

    target = (resolved_base / rel).resolve()
    try:
        target.relative_to(resolved_base)
    except ValueError as exc:
        raise ScaffoldPathError(
            f"Resolved path {target} escapes scaffold base directory {resolved_base}."
        ) from exc

    return target
