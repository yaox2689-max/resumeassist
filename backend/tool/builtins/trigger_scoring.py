"""trigger_scoring tool — async scoring, fires background task and returns immediately."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from pydantic import BaseModel

from api.schemas import EventType, FrontendEvent
from tool.base import ToolContext, ToolResult, tool

logger = logging.getLogger(__name__)


class TriggerScoringArgs(BaseModel):
    """Arguments for trigger_scoring tool."""

    dimension: str  # technical_depth / expression_clarity / logical_completeness


@tool
async def trigger_scoring(args: TriggerScoringArgs, ctx: ToolContext) -> ToolResult:
    """Trigger async scoring — returns immediately, score pushed via SCORE_UPDATE event later.

    Use this after the candidate gives a substantive technical answer (≥3 sentences).
    Do NOT use for greetings, acknowledgments, or short confirmations.
    """
    if not ctx.agent_factory:
        return ToolResult.err(
            code="no_factory",
            message="AgentFactory not available",
            summary="Cannot create scoring agent",
        )

    # Read recent dialogue synchronously (fast, just reading JSONL)
    events = ctx.session_store.read_events(ctx.user_id, ctx.session_id)
    recent_dialogue = _extract_recent_dialogue(events)

    if not recent_dialogue.strip():
        return ToolResult.ok(
            data={"score": None, "reason": "没有可评分的对话"},
            summary="No dialogue to score",
        )

    # Fire and forget — run scoring in background
    asyncio.create_task(
        _run_scoring_async(
            dimension=args.dimension,
            dialogue=recent_dialogue,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            resume_id=ctx.resume_id,
            memory_root=ctx.memory_root,
            agent_factory=ctx.agent_factory,
            session_store=ctx.session_store,
            event_queue=ctx.event_queue,
        )
    )

    # Return immediately, don't block the interview
    return ToolResult.ok(
        data={"status": "scoring_in_progress"},
        summary="评分已启动，结果将异步推送",
    )


async def _run_scoring_async(
    dimension: str,
    dialogue: str,
    user_id: str,
    session_id: str,
    resume_id: str,
    memory_root: str,
    agent_factory: object,
    session_store: object,
    event_queue: object = None,
) -> None:
    """Run scoring in background via sub-agent, push result via SCORE_UPDATE event."""
    try:
        # Create lightweight scoring sub-agent (no tools, no history, fast)
        agent = agent_factory.create_lightweight_agent(
            profile_id="scoring-agent",
            session_id=f"{session_id}:scoring",
            user_id=user_id,
        )

        prompt = (
            f"请对以下回答进行评分，评分维度：{dimension}\n\n"
            f"对话内容：\n{dialogue}"
        )

        result_text = ""
        async for event in agent.run(prompt):
            if event.type == EventType.ASSISTANT_TEXT_DONE:
                result_text = event.payload.get("text", "")

        # Parse result — strip markdown fences if present
        try:
            raw = result_text.strip()
            if raw.startswith("```"):
                raw = re.sub(r'^```(?:json)?\s*\n?', '', raw)
                raw = re.sub(r'\n?\s*```$', '', raw)
                raw = raw.strip()
            score_data = json.loads(raw)
        except json.JSONDecodeError:
            brace = re.search(r'\{.*\}', result_text, re.DOTALL)
            if brace:
                try:
                    score_data = json.loads(brace.group())
                except json.JSONDecodeError:
                    score_data = {"score": None, "reason": "评分结果解析失败"}
            else:
                score_data = {"score": None, "reason": "评分结果解析失败"}

        # Write to memory
        if score_data.get("score") is not None:
            _write_score_to_memory(user_id, resume_id, memory_root, score_data)

        # Push SCORE_UPDATE event to session store (frontend picks it up)
        score_event = FrontendEvent(
            type=EventType.SCORE_UPDATE,
            payload=score_data,
        )
        session_store.append_event(user_id, session_id, score_event)

        # Push to active SSE stream so frontend sees it in real-time
        if event_queue is not None:
            try:
                await event_queue.put(score_event)
            except Exception:
                pass

        logger.info("Async scoring completed: %s", score_data)

    except Exception as e:
        logger.error("Async scoring failed: %s", e)


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
                break

    return "\n".join(lines)


def _write_score_to_memory(user_id: str, resume_id: str, memory_root: str, score_data: dict) -> None:
    """Append score to INTERVIEW_NOTE.md."""
    try:
        from storage.memory.store import MemoryStore

        store = MemoryStore(root_dir=memory_root or "storage/memory")
        existing = store.read_interview_note(user_id, resume_id)

        entry = (
            f"\n- [评分] {score_data.get('dimension', 'unknown')}: "
            f"{score_data.get('score', 'N/A')}/10 — {score_data.get('reason', '')}"
        )

        content = existing + entry if existing else f"# 面试官笔记\n{entry.lstrip(chr(10))}"
        store.write_interview_note(user_id, resume_id, content)
    except Exception as e:
        logger.warning("Failed to write score to memory: %s", e)
