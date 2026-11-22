"""Client Path Shield and path-traversal protection for audit reports."""

from __future__ import annotations

from pathlib import Path


class ClientPathShieldError(PermissionError):
    """Raised when report output violates Client Path Shield or traversal guards."""


def _is_within(path: Path, parent: Path) -> bool:
    """Return True if path resolves inside parent directory (inclusive)."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_report_output_path(
    target_path: Path,
    output_path: Path,
    repo_root: Path,
) -> Path:
    """Validate report output path against path traversal and Client Path Shield.

    When auditing an external/client directory outside ``repo_root``, writing
    audit artifacts back inside the public repository tree is strictly forbidden.
    """
    if ".." in output_path.parts:
        raise ClientPathShieldError(
            f"Path traversal segments ('..') are disallowed in report output path: {output_path}"
        )

    resolved_repo = repo_root.resolve()
    resolved_target = target_path.resolve()
    resolved_output = output_path.resolve()

    target_is_external = not _is_within(resolved_target, resolved_repo)
    output_is_inside_repo = _is_within(resolved_output, resolved_repo)

    if target_is_external and output_is_inside_repo:
        raise ClientPathShieldError(
            "Client Path Shield blocked writing an external audit report inside the "
            f"public repository ({resolved_output}). Write reports inside the client directory."
        )

    return resolved_output
