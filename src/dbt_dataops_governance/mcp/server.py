"""Model Context Protocol (MCP) JSON-RPC 2.0 stdio server with untrusted-data framing."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from dbt_dataops_governance import __version__
from dbt_dataops_governance.auditor import ClientPathShieldError
from dbt_dataops_governance.scaffolder import ScaffoldPathError
from dbt_dataops_governance.sdk import DbtGovernance

MCP_PROTOCOL_VERSION = "2024-11-05"
_UNTRUSTED_TAG_RE = re.compile(r"</?untrusted_data\b", re.IGNORECASE)


def wrap_untrusted_data(payload: Any, source: str = "dge") -> str:
    """Serialize payload inside <untrusted_data> delimiters per OWASP LLM01 / POP_T_175."""
    serialized = payload if isinstance(payload, str) else json.dumps(payload, indent=2, ensure_ascii=False)
    neutralized = _UNTRUSTED_TAG_RE.sub("[redacted_untrusted_tag", serialized)
    safe_source = re.sub(r"[^a-zA-Z0-9_.-]", "_", source)
    return f'<untrusted_data source="{safe_source}">\n{neutralized}\n</untrusted_data>'


TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "dge_list_rules",
        "description": "List governance rules from catalog/governance_rules.yaml with optional filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "family": {"type": "string"},
                "severity": {"type": "string"},
                "dialect": {"type": "string"},
            },
        },
    },
    {
        "name": "dge_audit",
        "description": "Run zero-execution static SQL/dbt AST audit on a file, directory, or inline SQL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_path": {"type": "string"},
                "sql": {"type": "string"},
                "file_path": {"type": "string"},
                "dialect": {"type": "string", "default": "duckdb"},
                "output_path": {"type": "string"},
                "output_format": {"type": "string", "default": "json"},
            },
        },
    },
    {
        "name": "dge_scaffold",
        "description": "Generate Medallion dbt project & ODCS v3.1 contract into an explicit output_dir.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_source": {"type": "string"},
                "output_dir": {"type": "string"},
                "source_type": {"type": "string"},
                "project_name": {"type": "string"},
                "source_name": {"type": "string"},
                "table_name": {"type": "string"},
                "dialect": {"type": "string", "default": "duckdb"},
                "entity_kind": {"type": "string"},
            },
            "required": ["input_source", "output_dir"],
        },
    },
    {
        "name": "dge_transpile",
        "description": "Transpile SQL/dbt across DuckDB, Spark SQL (Databricks), Snowflake, and BigQuery.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string"},
                "source_dialect": {"type": "string"},
                "target_dialect": {"type": "string"},
                "preserve_dbt_jinja": {"type": "boolean", "default": True},
                "check_roundtrip": {"type": "boolean", "default": False},
            },
            "required": ["sql", "source_dialect", "target_dialect"],
        },
    },
    {
        "name": "dge_lineage",
        "description": "Extract static dbt ref/source lineage graph and Mermaid diagram.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_path": {"type": "string"},
            },
            "required": ["target_path"],
        },
    },
]


class MCPDispatcher:
    """In-memory testable JSON-RPC 2.0 dispatcher for dge-mcp."""

    def __init__(self, governance: DbtGovernance | None = None) -> None:
        self.gov = governance or DbtGovernance()

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any] | None:
        """Process one JSON-RPC 2.0 request and return response dict (or None for notifications)."""
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        if not method:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": "Invalid Request: missing method"},
            }

        if method == "notifications/initialized":
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "dge-mcp", "version": __version__},
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_SCHEMA}}

        if method == "tools/call":
            return self._handle_tool_call(req_id, params)

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _handle_tool_call(self, req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tools/call invocation and wrap output in <untrusted_data>."""
        tool_name = str(params.get("name", ""))
        args = params.get("arguments") or {}

        try:
            payload = self._execute_tool(tool_name, args)
            wrapped = wrap_untrusted_data(payload, source=tool_name)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": wrapped}],
                    "isError": False,
                },
            }
        except (ClientPathShieldError, ScaffoldPathError, FileNotFoundError, ValueError) as exc:
            wrapped_err = wrap_untrusted_data({"error": str(exc)}, source=f"{tool_name}_error")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": wrapped_err}],
                    "isError": True,
                },
            }

    def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Route tool name to DbtGovernance SDK method."""
        if tool_name == "dge_list_rules":
            rules = self.gov.list_rules(
                family=args.get("family"),
                severity=args.get("severity"),
                dialect=args.get("dialect"),
            )
            return {"total": len(rules), "rules": rules}

        if tool_name == "dge_audit":
            if args.get("target_path"):
                return self.gov.audit(
                    args["target_path"],
                    dialect=args.get("dialect", "duckdb"),
                    output_path=args.get("output_path"),
                    output_format=args.get("output_format", "json"),
                )
            if args.get("sql"):
                return self.gov.audit_sql(
                    args["sql"],
                    dialect=args.get("dialect", "duckdb"),
                    file_path=args.get("file_path", "inline.sql"),
                )
            raise ValueError("Either 'target_path' or 'sql' must be provided to dge_audit.")

        if tool_name == "dge_scaffold":
            if not args.get("input_source") or not args.get("output_dir"):
                raise ValueError("'input_source' and 'output_dir' are required for dge_scaffold.")
            return self.gov.scaffold(
                args["input_source"],
                output_dir=args["output_dir"],
                source_type=args.get("source_type"),
                project_name=args.get("project_name", "scaffolded_lakehouse"),
                source_name=args.get("source_name"),
                table_name=args.get("table_name"),
                dialect=args.get("dialect", "duckdb"),
                entity_kind=args.get("entity_kind"),
            )

        if tool_name == "dge_transpile":
            return self.gov.transpile(
                args.get("sql", ""),
                source_dialect=args.get("source_dialect", ""),
                target_dialect=args.get("target_dialect", ""),
                preserve_dbt_jinja=args.get("preserve_dbt_jinja", True),
                check_roundtrip=args.get("check_roundtrip", False),
            )

        if tool_name == "dge_lineage":
            if not args.get("target_path"):
                raise ValueError("'target_path' is required for dge_lineage.")
            return self.gov.lineage(args["target_path"])

        raise ValueError(f"Unknown MCP tool: {tool_name}")


def main() -> int:
    """Run JSON-RPC 2.0 stdio loop for dge-mcp."""
    dispatcher = MCPDispatcher()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
            continue

        resp = dispatcher.handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
