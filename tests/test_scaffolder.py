"""End-to-end tests for MedallionScaffolder across Parquet, CSV, DuckDB, DDL, and dbt build."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import yaml

from dbt_dataops_governance.auditor import AuditEngine, Severity
from dbt_dataops_governance.scaffolder import MedallionScaffolder, ScaffoldPathError
from dbt_dataops_governance.scaffolder.path_guard import safe_join

SCAFFOLDER = MedallionScaffolder()


def _dbt_executable() -> str:
    """Locate the dbt CLI executable in the active Python virtual environment."""
    exe_name = "dbt.exe" if sys.platform == "win32" else "dbt"
    candidate = Path(sys.executable).resolve().parent / exe_name
    if candidate.is_file():
        return str(candidate)
    resolved = shutil.which("dbt")
    if resolved:
        return resolved
    raise FileNotFoundError("dbt executable not found in active Python environment.")


def _run_dbt_build(project_dir: Path) -> subprocess.CompletedProcess[str]:
    """Execute dbt build in DuckDB against a scaffolded project directory."""
    dbt_bin = _dbt_executable()
    return subprocess.run(
        [
            dbt_bin,
            "build",
            "--project-dir",
            str(project_dir),
            "--profiles-dir",
            str(project_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_path_guard_blocks_traversal_and_empty_paths(tmp_path: Path) -> None:
    """Reject empty output_dir and '..' path-traversal escapes."""
    ddl = "CREATE TABLE orders (order_id VARCHAR PRIMARY KEY, amount DOUBLE);"
    with pytest.raises(ScaffoldPathError, match="non-empty"):
        SCAFFOLDER.scaffold(ddl, output_dir="   ", source_type="ddl")

    with pytest.raises(ScaffoldPathError, match="Path traversal"):
        SCAFFOLDER.scaffold(ddl, output_dir=tmp_path / ".." / "escape", source_type="ddl")

    with pytest.raises(ScaffoldPathError, match="Unsafe relative path"):
        safe_join(tmp_path, "..", "outside.sql")


def test_scaffold_from_parquet_passes_dbt_build_and_preserves_canonical_keys(
    tmp_path: Path,
) -> None:
    """Parquet scaffold preserves leading zeros, converts sentinels to NULL, and passes dbt build."""
    parquet_file = tmp_path / "orders.parquet"
    table = pa.table(
        {
            "order_id": pa.array(["ord_001", "ord_002"], type=pa.string()),
            "postal_code": pa.array(["01310100", "20040002"], type=pa.string()),
            "region_tag": pa.array(["SOUTH", "N/A"], type=pa.string()),
            "order_status": pa.array(["PAID", "PENDING"], type=pa.string()),
            "amount_usd": pa.array([150.25, 89.0], type=pa.float64()),
            "is_priority": pa.array([True, False], type=pa.bool_()),
        }
    )
    pq.write_table(table, parquet_file)

    out_dir = tmp_path / "lakehouse_parquet"
    result = SCAFFOLDER.scaffold(
        parquet_file,
        output_dir=out_dir,
        source_name="raw_demo",
        table_name="orders",
        project_name="demo_parquet",
        accepted_values={"order_status": ("PAID", "PENDING")},
    )

    assert result.target_model_name == "fct_orders"
    assert "contracts/fct_orders_contract.yaml" in result.generated_files

    build = _run_dbt_build(out_dir)
    assert build.returncode == 0, f"dbt build failed:\nSTDOUT:\n{build.stdout}\nSTDERR:\n{build.stderr}"

    # Verify leading zero and sentinel-to-NULL in built DuckDB table
    db_file = out_dir / "target" / "demo_parquet.duckdb"
    with duckdb.connect(str(db_file), read_only=True) as conn:
        rows = conn.execute(
            "SELECT order_id, postal_code, region_tag FROM fct_orders ORDER BY order_id"
        ).fetchall()
    assert rows == [
        ("ord_001", "01310100", "SOUTH"),
        ("ord_002", "20040002", None),
    ]


def test_scaffold_from_csv_passes_dbt_build(tmp_path: Path) -> None:
    """CSV scaffold handles leading-zero string keys and passes dbt build in DuckDB."""
    csv_file = tmp_path / "customers.csv"
    csv_file.write_text(
        "customer_id,postal_code,segment,lifetime_orders\n"
        "cust_1,01310100,ENTERPRISE,5\n"
        "cust_2,04538132,SMB,-1\n",
        encoding="utf-8",
        newline="\n",
    )

    out_dir = tmp_path / "lakehouse_csv"
    result = SCAFFOLDER.scaffold(
        csv_file,
        output_dir=out_dir,
        source_name="raw_crm",
        table_name="customers",
        project_name="demo_csv",
        accepted_values={"segment": ("ENTERPRISE", "SMB")},
    )

    assert result.target_model_name == "dim_customers"
    build = _run_dbt_build(out_dir)
    assert build.returncode == 0, f"dbt build failed:\nSTDOUT:\n{build.stdout}\nSTDERR:\n{build.stderr}"

    db_file = out_dir / "target" / "demo_csv.duckdb"
    with duckdb.connect(str(db_file), read_only=True) as conn:
        rows = conn.execute(
            "SELECT customer_id, postal_code, lifetime_orders FROM dim_customers ORDER BY customer_id"
        ).fetchall()
    assert rows == [
        ("cust_1", "01310100", 5),
        ("cust_2", "04538132", None),
    ]


def test_scaffold_from_duckdb_table_passes_dbt_build(tmp_path: Path) -> None:
    """DuckDB database table inspection scaffolds Medallion project and passes dbt build."""
    src_db = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(src_db)) as conn:
        conn.execute(
            "CREATE TABLE payments (payment_id VARCHAR, order_id VARCHAR, amount_usd DOUBLE, status VARCHAR)"
        )
        conn.execute(
            "INSERT INTO payments VALUES ('pay_1', 'ord_1', 42.5, 'SETTLED'), ('pay_2', 'ord_2', 19.0, 'SETTLED')"
        )

    out_dir = tmp_path / "lakehouse_duckdb"
    result = SCAFFOLDER.scaffold(
        src_db,
        output_dir=out_dir,
        source_type="duckdb",
        source_name="raw_payments",
        table_name="payments",
        project_name="demo_duckdb",
        accepted_values={"status": ("SETTLED", "REFUNDED")},
    )

    assert result.target_model_name == "fct_payments"
    build = _run_dbt_build(out_dir)
    assert build.returncode == 0, f"dbt build failed:\nSTDOUT:\n{build.stdout}\nSTDERR:\n{build.stderr}"


def test_scaffold_from_ddl_emits_odcs_v31_and_passes_audit_engine(tmp_path: Path) -> None:
    """DDL scaffold generates valid ODCS v3.1 contract, relationships tests, and clean audit score."""
    ddl = """
    CREATE TABLE invoices (
        invoice_id VARCHAR PRIMARY KEY,
        customer_id VARCHAR NOT NULL,
        postal_code BIGINT,
        net_amount DOUBLE,
        issued_date DATE
    );
    """
    out_dir = tmp_path / "lakehouse_ddl"
    result = SCAFFOLDER.scaffold(
        ddl,
        output_dir=out_dir,
        source_type="ddl",
        source_name="raw_billing",
        project_name="demo_ddl",
        relationships={"customer_id": ("dim_customers", "customer_id")},
    )

    assert result.target_model_name == "fct_invoices"
    # Verify canonical postal_code forced to varchar despite BIGINT in DDL
    postal_col = next(c for c in result.table_spec.columns if c.name == "postal_code")  # type: ignore[union-attr]
    assert postal_col.data_type == "varchar"

    # Verify ODCS v3.1 contract structure
    contract = yaml.safe_load((out_dir / "contracts" / "fct_invoices_contract.yaml").read_text(encoding="utf-8"))
    assert contract["dataContractSpecification"] == "3.1.0"
    assert contract["models"]["fct_invoices"]["primaryKey"] == ["invoice_id"]

    # Verify enforced contract and unit_tests in core _models.yml
    core_yml = yaml.safe_load((out_dir / "models" / "core" / "_models.yml").read_text(encoding="utf-8"))
    assert core_yml["models"][0]["config"]["contract"]["enforced"] is True
    assert len(core_yml["unit_tests"]) == 1

    # Verify zero CRITICAL/HIGH findings in AuditEngine
    summary = AuditEngine().audit_path(out_dir, dialect="duckdb")
    severe = [f for f in summary.findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
    assert severe == [], f"Unexpected severe audit findings: {severe}"
