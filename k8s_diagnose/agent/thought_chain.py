"""Thought chain: records each reasoning step during diagnosis."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ThoughtType(str, Enum):
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    VERIFICATION = "verification"
    CONCLUSION = "conclusion"
    ACTION = "action"


_ICONS = {
    ThoughtType.OBSERVATION: "👁",
    ThoughtType.HYPOTHESIS: "💡",
    ThoughtType.VERIFICATION: "🔍",
    ThoughtType.CONCLUSION: "✅",
    ThoughtType.ACTION: "⚡",
}


@dataclass
class ThoughtNode:
    id: int
    type: ThoughtType
    content: str
    tool_called: str | None = None
    tool_result_summary: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def render(self) -> str:
        icon = _ICONS.get(self.type, "•")
        line = f"  {icon} [{self.type.value}] {self.content}"
        if self.tool_called:
            line += f"\n    → 执行: {self.tool_called}"
        return line


class ThoughtChain:
    """Records all reasoning steps during a diagnosis session."""

    def __init__(self):
        self.nodes: list[ThoughtNode] = []
        self._counter = 0

    def add(
        self,
        thought_type: ThoughtType,
        content: str,
        tool_called: str | None = None,
        tool_result_summary: str | None = None,
    ) -> ThoughtNode:
        self._counter += 1
        node = ThoughtNode(
            id=self._counter,
            type=thought_type,
            content=content,
            tool_called=tool_called,
            tool_result_summary=tool_result_summary,
        )
        self.nodes.append(node)
        return node

    def render(self) -> str:
        """Render thought chain as human-readable text."""
        lines = ["## 排查思维链", ""]
        for node in self.nodes:
            lines.append(node.render())
        lines.append("")
        return "\n".join(lines)

    def to_llm_context(self) -> str:
        """Convert thought chain to LLM-friendly context for next-round reasoning."""
        type_labels = {
            ThoughtType.OBSERVATION: "[观察]",
            ThoughtType.HYPOTHESIS: "[假设]",
            ThoughtType.VERIFICATION: "[验证]",
            ThoughtType.CONCLUSION: "[结论]",
            ThoughtType.ACTION: "[行动]",
        }
        parts = []
        for node in self.nodes:
            label = type_labels.get(node.type, "")
            text = f"{label} {node.content}"
            if node.tool_result_summary:
                text += f" → 结果: {node.tool_result_summary}"
            parts.append(text)
        return "\n".join(parts)

    def to_compressed_llm_context(self) -> str:
        """Compressed context: pair ACTION+OBSERVATION, use compact symbols.
        Preserves all information but reduces token usage by ~40-50%.
        Symbols: > observation  · tool call+result  ? hypothesis  ✓ conclusion  → verification
        """
        parts = []
        i = 0
        while i < len(self.nodes):
            node = self.nodes[i]

            # Pair ACTION with following OBSERVATION
            if node.type == ThoughtType.ACTION and node.tool_called:
                tool_call = node.content
                if i + 1 < len(self.nodes) and self.nodes[i + 1].type == ThoughtType.OBSERVATION:
                    result = self.nodes[i + 1].tool_result_summary or self.nodes[i + 1].content
                    parts.append(f"· {tool_call} → {result}")
                    i += 2
                    continue
                # ACTION without paired observation
                parts.append(f"· {tool_call}")
                i += 1
                continue

            # Unpaired OBSERVATION (e.g. initial user request)
            if node.type == ThoughtType.OBSERVATION:
                parts.append(f"> {node.content}")
                i += 1
                continue

            if node.type == ThoughtType.HYPOTHESIS:
                parts.append(f"? {node.content}")
                i += 1
                continue

            if node.type == ThoughtType.CONCLUSION:
                parts.append(f"✓ {node.content}")
                i += 1
                continue

            if node.type == ThoughtType.VERIFICATION:
                parts.append(f"→ {node.content}")
                i += 1
                continue

            # Fallback
            parts.append(node.content)
            i += 1

        return "\n".join(parts)

    @property
    def last_node(self) -> ThoughtNode | None:
        return self.nodes[-1] if self.nodes else None
