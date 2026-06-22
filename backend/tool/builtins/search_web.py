"""search_web tool — search technical docs via MCP Brave Search or DuckDuckGo fallback."""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel

from tool.base import ToolContext, ToolResult, tool

logger = logging.getLogger(__name__)

_TECH_SITES = "site:stackoverflow.com OR site:github.com OR site:developer.mozilla.org"


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
    # Priority 1: MCP Brave Search (if configured)
    mcp_client = ctx.mcp_clients.get("brave-search")
    if mcp_client:
        return await _search_via_mcp(mcp_client, args)

    # Priority 2: DuckDuckGo (free, no API key)
    return await _search_via_ddg(args)


async def _search_via_mcp(mcp_client, args: SearchWebArgs) -> ToolResult:
    """Search via MCP Brave Search."""
    try:
        query = f"{args.query} {_TECH_SITES}" if args.topic == "technical" else args.query
        result = await mcp_client.call_tool("brave_web_search", {"query": query})

        if result.status == "err":
            return ToolResult.ok(
                data={"note": "Brave Search 失败，降级到 DuckDuckGo"},
                summary="Brave Search failed, fallback to DDG",
            )

        return ToolResult.ok(
            data={"query": args.query, "results": result.data.get("result", ""), "source": "brave"},
            summary=result.summary[:200] if result.summary else "Search completed",
        )
    except Exception as e:
        logger.warning("MCP search failed: %s", e)
        return ToolResult.ok(
            data={"note": "Brave Search 异常，降级到 DuckDuckGo"},
            summary="Brave Search error, fallback to DDG",
        )


async def _search_via_ddg(args: SearchWebArgs) -> ToolResult:
    """Search via DuckDuckGo (free, no API key required)."""
    try:
        from duckduckgo_search import DDGS

        query = f"{args.query} site:stackoverflow.com OR site:github.com" if args.topic == "technical" else args.query

        # Run sync DDGS in thread pool to avoid blocking
        def _do_search():
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            return results

        results = await asyncio.get_event_loop().run_in_executor(None, _do_search)

        if not results:
            return ToolResult.ok(
                data={"query": args.query, "results": "未找到相关结果", "source": "duckduckgo"},
                summary="No results found",
            )

        # Format results
        formatted = []
        for r in results:
            formatted.append(f"- {r.get('title', '')}: {r.get('body', '')} ({r.get('href', '')})")

        return ToolResult.ok(
            data={"query": args.query, "results": "\n".join(formatted), "source": "duckduckgo"},
            summary=formatted[0][:200] if formatted else "Search completed",
        )

    except Exception as e:
        logger.warning("DuckDuckGo search failed: %s", e)
        return ToolResult.ok(
            data={"note": "搜索服务不可用，请基于你的知识回答"},
            summary="Search unavailable, fallback to LLM knowledge",
        )
