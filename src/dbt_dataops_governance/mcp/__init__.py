"""MCP JSON-RPC 2.0 stdio server package for dbt-dataops-governance-engine."""

from dbt_dataops_governance.mcp.server import MCPDispatcher, main, wrap_untrusted_data

__all__ = ["MCPDispatcher", "main", "wrap_untrusted_data"]
