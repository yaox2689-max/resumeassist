"""get_strategy tool — trigger a strategy sub-agent for follow-up suggestions."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from api.schemas import EventType
from tool.base import ToolContext, ToolResult, tool

logger = logging.getLogger(__name__)


class GetStrategyArgs(BaseModel):
    """Arguments for get_strategy tool."""

    current_topic: str  # Current technical topic being discussed


@tool
async def get_strategy(args: GetStrategyArgs, ctx: ToolContext) -> ToolResult:
    """Trigger the strategy agent to suggest the next follow-up direction.

    Use this when you need guidance on what to ask next based on the
    candidate's performance so far.
    """
    if not ctx.agent_factory:
        return ToolResult.err(
            code="no_factory",
            message="AgentFactory not available",
            summary="Cannot create strategy agent",
        )

    try:
        # Read dialogue and scores
        events = ctx.session_store.read_events(ctx.user_id, ctx.session_id)
        dialogue = _extract_full_dialogue(events)
        scores = _extract_scores(ctx)

        # Create strategy sub-agent
        agent = ctx.agent_factory.create_text_agent(
            profile_id="strategy-agent",
            session_id=f"{ctx.session_id}:strategy",
            user_id=ctx.user_id,
            resume_id=ctx.resume_id,
        )

        prompt = (
            f"当前话题：{args.current_topic}\n\n"
            f"已有评分：\n{scores}\n\n"
            f"对话历史：\n{dialogue}\n\n"
            f"请建议下一步追问方向。"
        )

        result_text = ""
        async for event in agent.run(prompt):
            if event.type == EventType.ASSISTANT_TEXT_DONE:
                result_text = event.payload.get("text", "")

        # Parse result
        try:
            strategy_data = json.loads(result_text)
        except json.JSONDecodeError:
            strategy_data = {
                "next_direction": "继续当前话题",
                "reason": "策略结果解析失败",
                "suggested_topic": args.current_topic,
            }

        return ToolResult.ok(
            data=strategy_data,
            summary=f"Strategy: {strategy_data.get('next_direction', '')[:80]}",
        )

    except Exception as e:
        logger.error("get_strategy failed: %s", e)
        return ToolResult.err(
            code="strategy_error",
            message=str(e),
            summary="Strategy generation failed",
        )


def _extract_full_dialogue(events: list) -> str:
    """Extract full dialogue from events."""
    lines = []
    for event in events:
        if event.type in (EventType.USER_TEXT, EventType.USER_TRANSCRIPT):
            text = (event.payload.get("text") or "").strip()
            if text:
                lines.append(f"候选人: {text}")
        elif event.type in (EventType.ASSISTANT_TEXT_DONE, EventType.ASSISTANT_TRANSCRIPT_DONE):
            text = (event.payload.get("text") or "").strip()
            if text:
                lines.append(f"面试官: {text}")
    return "\n".join(lines[-20:])  # Last 20 turns to avoid context overflow


def _extract_scores(ctx: ToolContext) -> str:
    """Extract existing scores from INTERVIEW_NOTE.md."""
    try:
        from storage.memory.store import MemoryStore

        store = MemoryStore(root_dir=ctx.memory_root or "storage/memory")
        note = store.read_interview_note(ctx.user_id, ctx.resume_id)

        # Extract score lines
        score_lines = [
            line for line in note.split("\n")
            if "[评分]" in line
        ]
        return "\n".join(score_lines[-10:]) if score_lines else "暂无评分记录"
    except Exception:
        return "暂无评分记录"
