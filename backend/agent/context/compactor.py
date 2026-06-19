from __future__ import annotations

from agent.llm.base import BaseLLM
from agent.llm.events import TextDelta
from agent.profile import AgentProfile


class ContextCompactor:
    """Compacts conversation history when it exceeds token threshold."""

    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm

    async def compact(
        self,
        profile: AgentProfile,
        messages: list[dict],
        kept_recent_turns: int = 3,
    ) -> tuple[str, list[dict]]:
        """Compact conversation history by summarizing older messages.

        Retains recent turns dynamically: keeps going back until at least
        ``_MIN_KEEP_CHARS`` characters of meaningful content are accumulated,
        so that short filler turns (e.g. "嗯", "好的") don't waste the
        retention quota.

        Args:
            profile: Agent profile with context config
            messages: Current message list
            kept_recent_turns: Minimum number of recent turns to keep (floor)

        Returns:
            Tuple of (summary_text, compacted_messages)
        """
        if len(messages) <= kept_recent_turns + 1:  # +1 for system message
            return "", messages

        # Split into old messages (to summarize) and recent messages (to keep)
        system_message = messages[0] if messages[0]["role"] == "system" else None
        non_system_messages = [m for m in messages if m["role"] != "system"]

        if len(non_system_messages) <= kept_recent_turns:
            return "", messages

        old_messages, recent_messages = self._split_messages(
            non_system_messages, min_turns=kept_recent_turns
        )

        if not old_messages:
            return "", messages

        # Build summary prompt
        summary_prompt = self._build_summary_prompt(old_messages)

        # Call LLM to generate summary
        summary_text = await self._generate_summary(summary_prompt)

        # Rebuild messages with summary
        compacted = []
        if system_message:
            compacted.append(system_message)
        compacted.append({
            "role": "system",
            "content": f"Previous conversation summary:\n{summary_text}",
        })
        compacted.extend(recent_messages)

        return summary_text, compacted

    _SUMMARY_MAX_CHARS = 3000
    _MIN_KEEP_CHARS = 500

    def _split_messages(
        self, non_system_messages: list[dict], min_turns: int = 3
    ) -> tuple[list[dict], list[dict]]:
        """Split messages into old (to summarize) and recent (to keep).

        Keeps recent messages until at least ``_MIN_KEEP_CHARS`` characters
        of content are accumulated, with ``min_turns`` as the floor.
        """
        kept: list[dict] = []
        char_count = 0

        for msg in reversed(non_system_messages):
            kept.insert(0, msg)
            char_count += len(msg.get("content", "") or "")
            if len(kept) >= min_turns and char_count >= self._MIN_KEEP_CHARS:
                break

        old = non_system_messages[: -len(kept)] if kept else non_system_messages
        return old, kept

    def _build_summary_prompt(self, messages: list[dict]) -> str:
        """Build a prompt for summarizing old messages."""
        conversation = ""
        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")
            if not content:
                continue
            conversation += f"{role}: {content}\n\n"

        return f"""请用不超过500字概括以下对话，保留关键事实、技术细节和用户立场：

{conversation}

Summary:"""

    async def _generate_summary(self, prompt: str) -> str:
        """Generate a summary using the LLM, with hard length cap."""
        messages = [{"role": "user", "content": prompt}]
        summary_parts = []

        async for event in self.llm.stream(messages):
            if isinstance(event, TextDelta):
                summary_parts.append(event.delta)

        summary = "".join(summary_parts)
        if len(summary) > self._SUMMARY_MAX_CHARS:
            summary = summary[: self._SUMMARY_MAX_CHARS] + "\n...(摘要已截断)"
        return summary

    def estimate_tokens(self, messages: list[dict]) -> int:
        """Estimate token count for messages.

        Uses 2 chars ≈ 1 token for Chinese-dominant content (more accurate
        than the English heuristic of 4 chars ≈ 1 token).
        """
        total_chars = 0
        for msg in messages:
            total_chars += len(msg.get("role", ""))
            total_chars += len(msg.get("content", ""))

        return total_chars // 2

    def should_compact(self, profile: AgentProfile, messages: list[dict]) -> bool:
        """Check if messages exceed the compact threshold."""
        estimated_tokens = self.estimate_tokens(messages)
        return estimated_tokens > profile.context.compact_threshold
