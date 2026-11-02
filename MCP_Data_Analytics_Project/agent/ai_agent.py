"""
LangChain AI agent: LLM configuration and tool-calling workflow.

The agent connects to the MCP aggregator, retrieves the combined MCP tools,
and answers user questions by selecting and calling the appropriate tools.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from agent import mcp_client
from config import prompts, settings


class AIAgent:
    """Wraps the LLM + MCP tools and exposes an async ``ainvoke``."""

    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model=settings.MODEL,
            base_url=settings.OPENROUTER_BASE_URL,
            api_key=settings.OPENROUTER_API_KEY,
            temperature=0,
        )
        self._adapter = None
        self._agent = None
        self._tools = []

    @property
    def is_initialized(self) -> bool:
        return self._agent is not None

    @property
    def tools(self):
        return self._tools

    async def initialize(self) -> None:
        """Connect to the aggregator and create the LangChain agent once."""
        if self._agent is not None:
            return

        adapter, tools = await mcp_client.connect(settings.AGGREGATOR_URL)

        agent = create_agent(
            model=self._llm,
            tools=tools,
            system_prompt=prompts.SYSTEM_PROMPT,
        )

        self._adapter = adapter
        self._tools = tools
        self._agent = agent

    async def ainvoke(self, messages):
        """Run the agent with a LangChain-style ``messages`` list."""
        return await self._agent.ainvoke({"messages": messages})

    async def close(self) -> None:
        if self._adapter is not None:
            await self._adapter.__aexit__(None, None, None)
            self._adapter = None
            self._agent = None
