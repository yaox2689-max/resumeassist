from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Callable
from trace import (
    span_level_for_result,
    tool_result_output,
    trace_agent_turn,
    trace_compaction,
    trace_llm_call,
    trace_react_step,
    trace_tool,
)

from agent.context.builder import ContextBuilder
from agent.context.compactor import ContextCompactor
from agent.llm.base import BaseLLM
from agent.llm.events import (
    Done,
    LLMEvent,
    ProviderError,
    TextDelta,
    ThinkingDelta,
    ToolCallEnd,
    ToolCallStart,
    Usage,
)
from agent.profile import AgentProfile
from agent.state import AgentState, can_transition
from api.schemas import EventType, FrontendEvent
from storage.session.store import SessionStore
from tool.base import ToolContext, ToolMeta, ToolResult
from tool.executor import ToolCall, ToolExecutor

logger = logging.getLogger(__name__)

# Filler phrases that should NOT trigger scoring
_FILLER_PATTERN = re.compile(
    r'^(嗯|哦|额|啊|呢|吧|嘛|噢|喔|好|好的|对|对的|是|是的|ok|okay|行|行的|知道了|了解|明白|收到|谢谢|感谢|嗯嗯|哈哈|呵呵|emmm?|hmm+|yeah+|yep|nope|sure|right)\s*[!！。.~～]*$',
    re.IGNORECASE,
)


def _is_substantive_answer(text: str) -> bool:
    """Check if user answer has substantive content worth scoring."""
    if not text:
        return False
    stripped = text.strip()
    # Too short (single filler word)
    if _FILLER_PATTERN.match(stripped):
        return False
    # Must be at least 10 chars of actual content
    return len(stripped) >= 10


class CancelToken:
    """Token for signaling cancellation."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_set(self) -> bool:
        return self._cancelled


class ReActAgent:
    """ReAct Agent Loop: Reason -> Act -> Observe."""

    def __init__(
        self,
        profile: AgentProfile,
        llm: BaseLLM,
        context_builder: ContextBuilder,
        compactor: ContextCompactor,
        tool_executor: ToolExecutor,
        tools: dict[str, ToolMeta],
        session_store: SessionStore,
        user_id: str,
        session_id: str,
        cancel_token: CancelToken | None = None,
        resume_content: str = "",
        resume_id: str = "",
        jd_content: str = "",
        mcp_clients: dict | None = None,
        agent_factory: object | None = None,
    ) -> None:
        self.profile = profile
        self.llm = llm
        self.context_builder = context_builder
        self.compactor = compactor
        self.tool_executor = tool_executor
        self.tools = tools
        self.session_store = session_store
        self.user_id = user_id
        self.session_id = session_id
        self.cancel_token = cancel_token or CancelToken()
        self.state = AgentState.IDLE
        self._resume_content = resume_content
        self._resume_id = resume_id
        self._jd_content = jd_content
        self._mcp_clients = mcp_clients or {}
        self._agent_factory = agent_factory
        self._text_buffer: list[str] = []
        self._current_tool_calls: list[ToolCall] = []
        self._session_obj: object | None = None
        self._sandbox_root: str = ""
        self._db_session: object | None = None

    async def run(self, user_input: str) -> AsyncIterator[FrontendEvent]:
        """Run the ReAct loop for a user input.

        Yields FrontendEvents to be sent to the frontend.
        """
        with trace_agent_turn(
            session_id=self.session_id,
            user_id=self.user_id,
            user_input=user_input,
            profile_id=self.profile.id,
        ) as turn:
            turn_output: dict[str, object] = {"stop_reason": "completed", "steps": 0}

            # Transition to thinking
            self._set_state(AgentState.THINKING)
            yield self._make_state_event(AgentState.THINKING)

            # Get session events for context
            events = self.session_store.read_events(self.user_id, self.session_id)

            # Build messages
            messages = self.context_builder.build_messages(
                self.profile, events, user_input,
                resume_content=self._resume_content,
                user_id=self.user_id,
                resume_id=self._resume_id,
                jd_content=self._jd_content,
            )

            # Check if compaction is needed
            if self.compactor.should_compact(self.profile, messages):
                yield self._make_state_event(AgentState.COMPACTING)
                with trace_compaction() as compaction:
                    summary, messages = await self.compactor.compact(
                        self.profile, messages
                    )
                    compaction.update(
                        output={"summary": summary} if summary else {"summary": None}
                    )
                if summary:
                    yield FrontendEvent(
                        type=EventType.SESSION_COMPACTED,
                        payload={"summary_text": summary},
                    )

            # ReAct loop
            steps = 0
            done = False
            while steps < self.profile.policy.max_steps and not done:
                if self.cancel_token.is_set():
                    yield self._make_interrupt_event()
                    turn_output["stop_reason"] = "interrupted"
                    break

                steps += 1
                with trace_react_step(step=steps) as step_span:
                    yield self._make_state_event(AgentState.STREAMING_TEXT)

                    self._react_should_continue = False
                    self._text_buffer = []
                    self._current_tool_calls = []
                    if hasattr(self.llm, "begin_stream_turn"):
                        self.llm.begin_stream_turn()
                    async for fe in self._process_llm_events(
                        messages, self._stream_llm(messages)
                    ):
                        yield fe

                    step_span.update(
                        output={
                            "continued": self._react_should_continue,
                            "tool_calls": len(self._current_tool_calls),
                        }
                    )

                if self._react_should_continue:
                    continue
                done = True

            # Check if max steps exceeded
            if steps >= self.profile.policy.max_steps and not done:
                yield FrontendEvent(
                    type=EventType.ERROR,
                    payload={
                        "code": "max_steps_exceeded",
                        "message": (
                            f"Maximum steps ({self.profile.policy.max_steps}) exceeded"
                        ),
                    },
                )
                yield FrontendEvent(
                    type=EventType.TURN_DONE,
                    payload={"stop_reason": "max_steps"},
                )
                turn_output["stop_reason"] = "max_steps"

            turn_output["steps"] = steps
            if self._text_buffer:
                turn_output["assistant_text"] = "".join(self._text_buffer)
            turn.update(output=turn_output)

            # Fire scoring after AI response — answer is now complete
            if user_input and _is_substantive_answer(user_input):
                self._fire_scoring(user_input)

            # Return to idle
            self._set_state(AgentState.IDLE)
            yield self._make_state_event(AgentState.IDLE)

    def _fire_scoring(self, user_input: str) -> None:
        """Fire background scoring — once per unique user input."""
        # Prevent recursive scoring
        if getattr(self, '_scoring_in_progress', False):
            return
        event_queue = getattr(self, '_event_queue', None)
        if not self._agent_factory or not event_queue:
            return

        # Deduplicate: only score each user input once
        scored = getattr(self, '_scored_inputs', set())
        if user_input in scored:
            return
        scored.add(user_input)
        self._scored_inputs = scored

        try:
            from tool.builtins.trigger_scoring import _run_scoring_async

            # Include the interviewer's last question for context
            events = self.session_store.read_events(self.user_id, self.session_id)
            last_question = ""
            for ev in reversed(events):
                if ev.type in (EventType.ASSISTANT_TEXT_DONE, EventType.ASSISTANT_TRANSCRIPT_DONE):
                    text = (ev.payload.get("text") or "").strip()
                    if text:
                        last_question = text
                        break
            dialogue = f"面试官: {last_question}\n候选人: {user_input}" if last_question else f"候选人: {user_input}"
            self._scoring_in_progress = True

            async def _with_cleanup():
                try:
                    await _run_scoring_async(
                        dimension="technical_depth",
                        dialogue=dialogue,
                        user_id=self.user_id,
                        session_id=self.session_id,
                        resume_id=self._resume_id,
                        memory_root="storage/memory",
                        agent_factory=self._agent_factory,
                        session_store=self.session_store,
                        event_queue=event_queue,
                    )
                finally:
                    self._scoring_in_progress = False

            asyncio.create_task(_with_cleanup())
        except Exception as e:
            logger.warning("Auto-scoring failed to launch: %s", e)
            self._scoring_in_progress = False

    async def _process_llm_events(
        self, messages: list[dict], event_stream: AsyncIterator[LLMEvent]
    ) -> AsyncIterator[FrontendEvent]:
        """Process LLM events, executing tools if needed.

        Sets self._react_should_continue = True when tools were executed
        and the ReAct loop should call the LLM again.
        """
        async for event in event_stream:
            if self.cancel_token.is_set():
                yield self._make_interrupt_event()
                return

            if isinstance(event, TextDelta):
                self._text_buffer.append(event.delta)
                yield FrontendEvent(
                    type=EventType.ASSISTANT_TEXT_DELTA,
                    payload={"delta": event.delta},
                )
            elif isinstance(event, ThinkingDelta):
                yield FrontendEvent(
                    type=EventType.ASSISTANT_THINKING_DELTA,
                    payload={"delta": event.delta},
                )
            elif isinstance(event, ToolCallStart):
                self._current_tool_calls.append(
                    ToolCall(
                        tool_call_id=event.tool_call_id,
                        tool_name=event.tool_name,
                        args={},
                    )
                )
                yield FrontendEvent(
                    type=EventType.TOOL_CALL_START,
                    payload={
                        "tool_call_id": event.tool_call_id,
                        "tool_name": event.tool_name,
                    },
                )
            elif isinstance(event, ToolCallEnd):
                for tc in self._current_tool_calls:
                    if tc.tool_call_id == event.tool_call_id:
                        tc.args = event.args
                        break
            elif isinstance(event, Done):
                if event.stop_reason == "tool_use":
                    yield self._make_state_event(AgentState.EXECUTING_TOOLS)
                    messages.append(self._build_assistant_tool_use_message())
                    async for msg in self._execute_tools_sequential():
                        if isinstance(msg, FrontendEvent):
                            yield msg
                        else:
                            messages.append(msg)
                    yield self._make_state_event(AgentState.AGGREGATING)
                    self._react_should_continue = True
                else:
                    full_text = "".join(self._text_buffer)
                    yield FrontendEvent(
                        type=EventType.ASSISTANT_TEXT_DONE,
                        payload={"text": full_text, "partial": False},
                    )
                    yield FrontendEvent(
                        type=EventType.TURN_DONE,
                        payload={"stop_reason": event.stop_reason},
                    )
                return
            elif isinstance(event, ProviderError):
                yield FrontendEvent(
                    type=EventType.ERROR,
                    payload={
                        "code": event.code,
                        "message": event.message,
                        "retryable": event.retryable,
                    },
                )
                # Retry logic: 2 attempts on main model, then fallback
                if event.retryable:
                    max_retries = 2
                    for retry_attempt in range(max_retries):
                        logger.warning(
                            "LLM error (attempt %s/%s): %s",
                            retry_attempt + 1,
                            max_retries,
                            event.message,
                        )
                        await asyncio.sleep(1)  # Brief backoff
                        try:
                            async for fe in self._process_llm_events(
                                messages, self.llm.stream(messages, self._get_tool_schemas())
                            ):
                                yield fe
                            return  # Success, exit retry loop
                        except Exception as retry_error:
                            logger.error("Retry %s failed: %s", retry_attempt + 1, retry_error)
                            if retry_attempt == max_retries - 1:
                                break  # Exhausted retries, try fallback

                    # If retries exhausted, try fallback
                    if self.profile.llm.fallback:
                        fallback_llm = self._create_fallback_llm()
                        if fallback_llm:
                            logger.info("Switching to fallback model")
                            async for fe in self._process_llm_events(
                                messages, fallback_llm.stream(messages, self._get_tool_schemas())
                            ):
                                yield fe
                            return

                yield FrontendEvent(
                    type=EventType.TURN_DONE,
                    payload={"stop_reason": "error"},
                )
                return

    async def _stream_llm(self, messages: list[dict]) -> AsyncIterator[LLMEvent]:
        """Stream events from the LLM."""
        tool_schemas = self._get_tool_schemas()
        model = self.llm.get_model_name()
        prompt_tokens = 0
        completion_tokens = 0

        with trace_llm_call(model=model, messages=messages) as generation:
            async for event in self.llm.stream(messages, tool_schemas):
                if isinstance(event, Usage):
                    prompt_tokens = event.prompt_tokens
                    completion_tokens = event.completion_tokens
                yield event

            generation.update(
                output="".join(self._text_buffer),
                usage_details={
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total": prompt_tokens + completion_tokens,
                },
            )

    async def _execute_tools_sequential(
        self,
    ) -> AsyncIterator[FrontendEvent | dict]:
        """Execute tool calls one by one, yielding events and tool messages.

        Yields FrontendEvent for frontend display, and dict messages for the
        LLM context. Tools are executed in parallel for speed, with results
        yielded in order after all complete.
        """
        if not self._current_tool_calls:
            return

        # Execute all tools in parallel
        ctx_factory = self._make_ctx_factory()
        tasks = []
        for call in self._current_tool_calls:
            tasks.append(self._execute_one_tool(call, ctx_factory))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Yield events in order
        for call, result in zip(self._current_tool_calls, results):
            if isinstance(result, Exception):
                result = ToolResult.err(
                    code="tool_error",
                    message=str(result),
                    summary="Tool execution failed",
                )

            yield FrontendEvent(
                type=EventType.TOOL_CALL_END,
                payload={
                    "tool_call_id": call.tool_call_id,
                    "tool_name": call.tool_name,
                },
            )
            yield FrontendEvent(
                type=EventType.TOOL_RESULT,
                payload={
                    "tool_call_id": call.tool_call_id,
                    "tool_name": call.tool_name,
                    "status": result.status,
                    "data": result.data,
                    "error": result.error,
                    "summary": result.summary,
                },
            )

            yield {
                "role": "tool",
                "tool_call_id": call.tool_call_id,
                "content": json.dumps(
                    result.data if result.status == "ok" else result.error
                ),
            }

    async def _execute_one_tool(self, call: ToolCall, ctx_factory: Callable) -> ToolResult:
        """Execute a single tool call."""
        with trace_tool(name=call.tool_name, args=call.args) as tool_span:
            batch = await self.tool_executor.run_parallel(
                [call],
                ctx_factory,
                self.tools,
                parallel_limit=1,
                cancel_token=self.cancel_token,
            )
            result = batch[0]
            tool_span.update(
                output=tool_result_output(result),
                level=span_level_for_result(result),
            )
        return result

    def _build_assistant_tool_use_message(self) -> dict:
        """Build assistant message with tool_calls for the next LLM turn."""
        text = "".join(self._text_buffer).strip()
        tool_calls_payload = [
            {
                "id": call.tool_call_id,
                "type": "function",
                "function": {
                    "name": call.tool_name,
                    "arguments": json.dumps(call.args, ensure_ascii=False),
                },
            }
            for call in self._current_tool_calls
        ]
        msg: dict = {
            "role": "assistant",
            "content": text if text else None,
            "tool_calls": tool_calls_payload,
        }
        if hasattr(self.llm, "consume_reasoning_for_message"):
            reasoning = self.llm.consume_reasoning_for_message()
            if reasoning:
                msg["reasoning_content"] = reasoning
        return msg

    def _make_ctx_factory(self) -> Callable[[ToolCall], ToolContext]:
        """Create a context factory for tool execution."""

        def ctx_factory(_call: ToolCall) -> ToolContext:
            return ToolContext(
                session=self._session_obj,
                session_id=self.session_id,
                user_id=self.user_id,
                profile=self.profile,
                cancel_token=self.cancel_token,
                sandbox_root=self._sandbox_root,
                db_session=self._db_session,
                resume_id=self._resume_id,
                memory_root="storage/memory",
                mcp_clients=self._mcp_clients,
                agent_factory=self._agent_factory,
                session_store=self.session_store,
                event_queue=getattr(self, '_event_queue', None),
            )

        return ctx_factory

    def _get_tool_schemas(self) -> list[dict]:
        """Get tool schemas for the LLM."""
        tool_metas = list(self.tools.values())
        schemas = []
        for meta in tool_metas:
            schemas.append({
                "type": "function",
                "function": {
                    "name": meta.name,
                    "description": meta.description,
                    "parameters": meta.args_model.model_json_schema(),
                },
            })
        return schemas

    def _create_fallback_llm(self) -> BaseLLM | None:
        """Create a fallback LLM instance from profile config."""
        from agent.llm.factory import LLMFactory

        if not self.profile.llm.fallback:
            return None

        fallback_config = self.profile.llm.fallback
        try:
            return LLMFactory.create(
                fallback_config.provider,
                {
                    "api_key": self._get_api_key(fallback_config.provider),
                    "model": fallback_config.model,
                    "temperature": fallback_config.temperature,
                },
            )
        except Exception:
            return None

    def _get_api_key(self, provider: str) -> str:
        from config.settings import settings

        return settings.get_api_key(provider)

    def _set_state(self, new_state: AgentState) -> None:
        """Set agent state with validation."""
        if can_transition(self.state, new_state):
            self.state = new_state
        else:
            # Force transition on interrupt
            if new_state == AgentState.INTERRUPTED:
                self.state = new_state

    def _make_state_event(self, state: AgentState) -> FrontendEvent:
        """Create a state.changed event."""
        return FrontendEvent(
            type=EventType.STATE_CHANGED,
            payload={"state": state.value},
        )

    def _make_interrupt_event(self) -> FrontendEvent:
        """Create interrupt event and partial commit."""
        self._set_state(AgentState.INTERRUPTED)

        # Partial commit - combine buffered text
        full_text = "".join(self._text_buffer)
        if full_text:
            return FrontendEvent(
                type=EventType.ASSISTANT_TEXT_DONE,
                payload={"text": full_text, "partial": True},
            )

        return FrontendEvent(
            type=EventType.STATE_CHANGED,
            payload={"state": AgentState.INTERRUPTED.value},
        )

    def interrupt(self) -> None:
        """Signal interruption."""
        self.cancel_token.cancel()
