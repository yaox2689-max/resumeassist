"""trigger_scoring tool — trigger a scoring sub-agent to evaluate the latest answer."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from tool.base import ToolContext, ToolResult, tool

logger = logging.getLogger(__name__)


class TriggerScoringArgs(BaseModel):
    """Arguments for trigger_scoring tool."""

    dimension: str  # technical_depth / expression_clarity / logical_completeness


@tool
async def trigger_scoring(args: TriggerScoringArgs, ctx: ToolContext) -> ToolResult:
    """Trigger the scoring agent to evaluate the candidate's latest answer.

    Use this after the candidate gives a substantive technical answer (≥3 sentences).
    Do NOT use for greetings, acknowledgments, or short confirmations.
    """
    if not ctx.agent_factory:
        return ToolResult.err(
            code="no_factory",
            message="AgentFactory not available",
            summary="Cannot create scoring agent",
        )

    try:
        # Read recent dialogue from session store
        events = ctx.session_store.read_events(ctx.user_id, ctx.session_id)
        recent_dialogue = _extract_recent_dialogue(events)

        if not recent_dialogue.strip():
            return ToolResult.ok(
                data={"score": None, "reason": "没有可评分的对话"},
                summary="No dialogue to score",
            )

        # Create scoring sub-agent
        agent = ctx.agent_factory.create_text_agent(
            profile_id="scoring-agent",
            session_id=f"{ctx.session_id}:scoring",
            user_id=ctx.user_id,
            resume_id=ctx.resume_id,
        )

        # Run scoring agent
        prompt = (
            f"请对以下回答进行评分，评分维度：{args.dimension}\n\n"
            f"对话内容：\n{recent_dialogue}"
        )
        result_text = ""
        async for event in agent.run(prompt):
            if event.type == EventType.ASSISTANT_TEXT_DONE:
                result_text = event.payload.get("text", "")

        # Parse result
        try:
            score_data = json.loads(result_text)
        except json.JSONDecodeError:
            score_data = {"score": None, "reason": "评分结果解析失败"}

        # Write to memory
        if score_data.get("score") is not None:
            _write_score_to_memory(ctx, score_data)

        return ToolResult.ok(
            data=score_data,
            summary=f"Score: {score_data.get('score', 'N/A')}/10 - {score_data.get('reason', '')[:50]}",
        )

    except Exception as e:
        logger.error("trigger_scoring failed: %s", e)
        return ToolResult.err(
            code="scoring_error",
            message=str(e),
            summary="Scoring failed",
        )


def _extract_recent_dialogue(events: list) -> str:
    """Extract the most recent user + assistant turn from events."""
    lines = []
    for event in reversed(events):
        if event.type in (EventType.ASSISTANT_TEXT_DONE, EventType.ASSISTANT_TRANSCRIPT_DONE):
            text = (event.payload.get("text") or "").strip()
            if text:
                lines.insert(0, f"面试官: {text}")
        elif event.type in (EventType.USER_TEXT, EventType.USER_TRANSCRIPT):
            text = (event.payload.get("text") or "").strip()
            if text:
                lines.insert(0, f"候选人: {text}")
                break  # Only get the last user turn

    return "\n".join(lines)


def _write_score_to_memory(ctx: ToolContext, score_data: dict) -> None:
    """Append score to INTERVIEW_NOTE.md."""
    try:
        from storage.memory.store import MemoryStore

        store = MemoryStore(root_dir=ctx.memory_root or "storage/memory")
        existing = store.read_interview_note(ctx.user_id, ctx.resume_id)

        entry = (
            f"\n- [评分] {score_data.get('dimension', 'unknown')}: "
            f"{score_data.get('score', 'N/A')}/10 — {score_data.get('reason', '')}"
        )

        content = existing + entry if existing else f"# 面试官笔记\n{entry.lstrip(chr(10))}"
        store.write_interview_note(ctx.user_id, ctx.resume_id, content)
    except Exception as e:
        logger.warning("Failed to write score to memory: %s", e)
