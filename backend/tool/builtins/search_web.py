"""search_web tool — search technical docs via MCP Brave Search."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from tool.base import ToolContext, ToolResult, tool

logger = logging.getLogger(__name__)


class SearchWebArgs(BaseModel):
    """Arguments for search_web tool."""

    query: str  # Search query
    topic: str = "technical"  # technical / general


@tool
async def search_web(args: SearchWebArgs, ctx: ToolContext) -> ToolResult:
    """Search the web for technical documentation to verify answers.

    Use this when you are unsure whether the candidate's answer is correct,
    or when the topic involves technologies after your knowledge cutoff.
    """
    mcp_client = ctx.mcp_clients.get("brave-search")
    if not mcp_client:
        return ToolResult.ok(
            data={"note": "搜索服务不可用，请基于你的知识回答"},
            summary="Search unavailable",
        )

    try:
        # Scope search to technical sites
        if args.topic == "technical":
            query = f"{args.query} site:stackoverflow.com OR site:github.com OR site:developer.mozilla.org OR site:docs.oracle.com"
        else:
            query = args.query

        result = await mcp_client.call_tool("brave_web_search", {"query": query})

        if result.status == "err":
            return ToolResult.ok(
                data={"note": "搜索失败，请基于你的知识回答", "error": result.error},
                summary="Search failed, fallback to LLM knowledge",
            )

        return ToolResult.ok(
            data={"query": args.query, "results": result.data.get("result", "")},
            summary=result.summary[:200] if result.summary else "Search completed",
        )

    except Exception as e:
        logger.warning("search_web failed: %s", e)
        return ToolResult.ok(
            data={"note": "搜索异常，请基于你的知识回答"},
            summary="Search error, fallback to LLM knowledge",
        )
