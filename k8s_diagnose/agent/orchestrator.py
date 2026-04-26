"""DiagnoseAgent: native ReAct loop using OpenAI-compatible API with thought chain."""
import json
import logging
import time
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from k8s_diagnose.config import Config
from k8s_diagnose.agent.tools import ALL_TOOLS, tools_to_openai_format, execute_tool
from k8s_diagnose.agent.prompts import build_system_prompt
from k8s_diagnose.agent.thought_chain import ThoughtChain, ThoughtType
from k8s_diagnose.knowledge.retriever import KnowledgeRetriever

logger = logging.getLogger(__name__)


@dataclass
class AgentStats:
    """Telemetry collected during a diagnosis run."""
    llm_calls: int = 0
    tool_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_llm_time_ms: int = 0
    total_tool_time_ms: int = 0


class DiagnoseAgent:
    """Main diagnosis agent using ReAct pattern with thought chain tracking."""

    def __init__(self, config: Config):
        self.config = config
        self.thought_chain = ThoughtChain()
        self.stats = AgentStats()

        # OpenAI-compatible client (lazy init)
        self._client: AsyncOpenAI | None = None
        self._client_kwargs = {}
        if config.llm.api_key:
            self._client_kwargs["api_key"] = config.llm.api_key
        if config.llm.base_url:
            self._client_kwargs["base_url"] = config.llm.base_url
        self.model = config.llm.model
        self.temperature = config.llm.temperature

        # Build system prompt with tool descriptions
        tool_descriptions = "\n".join(
            f"- {t.name}: {t.description}" for t in ALL_TOOLS
        )
        self.system_prompt = build_system_prompt(tool_descriptions)

        # Pre-convert tools to OpenAI API format
        self.openai_tools = tools_to_openai_format(ALL_TOOLS)

        # Initialize knowledge retriever
        if self.config.knowledge.enabled:
            self.retriever = KnowledgeRetriever(
                knowledge_dir=self.config.knowledge.knowledge_dir,
                max_injected_chars=self.config.knowledge.max_injected_chars,
            )
            self.retriever.load()
            logger.info(f"知识库已加载: {len(self.retriever.documents)} 个文档")
        else:
            self.retriever = None

    @property
    def client(self) -> AsyncOpenAI:
        """Lazy-init the OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(**self._client_kwargs)
        return self._client

    def _summarize_tool_result(self, content: str, max_lines: int = 30) -> str:
        """Extract key information from tool result for the thought chain."""
        if not content:
            return "(无输出)"
        lines = content.strip().split("\n")
        summary_lines = lines[:max_lines]
        if len(lines) > max_lines:
            summary_lines.append(f"... (共 {len(lines)} 行)")
        return "\n".join(summary_lines)

    async def _run_react(
        self,
        messages: list[dict],
        max_iterations: int = 20,
    ) -> tuple[list[dict], AgentStats]:
        """Native ReAct loop using OpenAI-compatible Messages API.

        Args:
            messages: List of message dicts in OpenAI format.
            max_iterations: Maximum tool-call iterations before stopping.

        Returns:
            Tuple of (final messages list, stats).
        """
        stats = AgentStats()

        for iteration in range(max_iterations):
            # Call LLM
            start = time.monotonic()
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    *messages,
                ],
                tools=self.openai_tools,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            stats.llm_calls += 1
            stats.total_llm_time_ms += elapsed_ms
            if response.usage:
                stats.total_input_tokens += response.usage.prompt_tokens or 0
                stats.total_output_tokens += response.usage.completion_tokens or 0

            logger.debug(
                f"LLM call #{stats.llm_calls}: {elapsed_ms}ms, "
                f"input_tokens={response.usage.prompt_tokens if response.usage else '?'}, "
                f"output_tokens={response.usage.completion_tokens if response.usage else '?'}"
            )

            choice = response.choices[0]
            msg = choice.message

            # Check for tool calls
            if not msg.tool_calls:
                # No tool calls — final answer
                messages.append({"role": "assistant", "content": msg.content})
                return messages, stats

            # Record assistant's response with tool_calls
            assistant_msg = {"role": "assistant", "content": msg.content, "tool_calls": []}
            for tc in msg.tool_calls:
                assistant_msg["tool_calls"].append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                })
            messages.append(assistant_msg)

            # Execute each tool call
            for tc in msg.tool_calls:
                stats.tool_calls += 1
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                start = time.monotonic()
                try:
                    result = execute_tool(ALL_TOOLS, tool_name, tool_args)
                except Exception as e:
                    logger.exception(f"工具执行异常: {tool_name}")
                    result = f"工具执行异常: {type(e).__name__}: {e}"
                elapsed_ms = int((time.monotonic() - start) * 1000)
                stats.total_tool_time_ms += elapsed_ms

                logger.debug(f"Tool call #{stats.tool_calls}: {tool_name} ({elapsed_ms}ms)")

                # Record in thought chain
                self.thought_chain.add(
                    ThoughtType.ACTION,
                    f"调用工具 {tool_name}",
                    tool_called=f"{tool_name}({json.dumps(tool_args)})",
                )
                summary = self._summarize_tool_result(result)
                self.thought_chain.add(
                    ThoughtType.OBSERVATION,
                    summary[:200],
                    tool_result_summary=summary[:200],
                )

                # Append tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        # Max iterations reached
        messages.append({
            "role": "assistant",
            "content": "诊断达到最大工具调用次数限制，未能得出结论。",
        })
        return messages, stats

    def _build_report(self, query: str, final_content: str) -> str:
        """Build structured diagnosis report."""
        report_parts = [
            "# 诊断报告",
            "",
            f"## 问题\n{query}",
            "",
            self.thought_chain.render(),
            "## 诊断结果",
            final_content,
            "",
        ]

        # Add command history
        report_parts.append("## 执行过的 kubectl 命令")
        report_parts.append("")
        for node in self.thought_chain.nodes:
            if node.type == ThoughtType.ACTION and node.tool_called:
                report_parts.append(f"- `{node.tool_called}`")

        report_parts.append("")

        # Append stats
        report_parts.append("## 诊断统计")
        report_parts.append("")
        report_parts.append(
            f"- LLM 调用: {self.stats.llm_calls} 次"
        )
        report_parts.append(
            f"- 工具调用: {self.stats.tool_calls} 次"
        )
        report_parts.append(
            f"- Token 用量: 输入 {self.stats.total_input_tokens}, 输出 {self.stats.total_output_tokens}"
        )
        report_parts.append(
            f"- 耗时: LLM {self.stats.total_llm_time_ms}ms, 工具 {self.stats.total_tool_time_ms}ms"
        )
        report_parts.append("")

        return "\n".join(report_parts)

    async def run(
        self,
        user_query: str,
        namespace: str = "default",
    ) -> str:
        """Run diagnosis and return structured report."""
        logger.info(f"开始诊断: {user_query}")
        self.stats = AgentStats()  # Reset per-run stats

        # Record initial observation
        self.thought_chain.add(
            ThoughtType.OBSERVATION,
            f"用户请求: {user_query}",
        )

        # Get thought chain context
        if self.config.agent.context_compression:
            thought_context = self.thought_chain.to_compressed_llm_context()
        else:
            thought_context = self.thought_chain.to_llm_context()

        # Retrieve relevant knowledge
        knowledge_context = ""
        if self.retriever:
            docs = self.retriever.retrieve(
                user_query,
                top_k=self.config.knowledge.max_results,
                min_score=self.config.knowledge.min_score,
            )
            if docs:
                knowledge_context = self.retriever.format_retrieved(docs)
                logger.info(f"RAG: 检索到 {len(docs)} 篇相关文档")

        # Build initial messages
        parts = []
        if knowledge_context:
            parts.append(f"<knowledge>\n{knowledge_context}\n</knowledge>")
        if thought_context:
            parts.append(f"问题: {user_query}\n\n已收集的信息:\n{thought_context}")
        else:
            parts.append(user_query)

        messages = [{"role": "user", "content": "\n\n".join(parts)}]

        # Run ReAct loop
        final_messages, self.stats = await self._run_react(
            messages,
            max_iterations=self.config.agent.max_tool_calls,
        )

        # Extract final answer
        last_msg = final_messages[-1]
        final_content = last_msg.get("content", "")

        # Build report
        report = self._build_report(user_query, final_content)

        # Log stats
        total_ms = self.stats.total_llm_time_ms + self.stats.total_tool_time_ms
        logger.info(
            f"诊断完成: {self.stats.llm_calls}次LLM调用, "
            f"{self.stats.tool_calls}次工具调用, "
            f"总耗时={total_ms}ms"
        )
        return report
