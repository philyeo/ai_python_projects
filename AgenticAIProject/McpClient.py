
# ============================================================
# MODULE 25 - RAG + GEOGRAPHY + WEATHER AI AGENT
# CONNECTING TO MAIN MCP AGGREGATOR
# ============================================================

import os
import asyncio

from dotenv import load_dotenv

from langchain_openrouter import ChatOpenRouter
from langchain.agents import create_agent
from langchain.mcp import MCPAdapter

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage
)


# ============================================================
# STEP 1 - LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

llm = ChatOpenRouter(
    model=os.getenv("MODEL", "openai/gpt-oss-20b:free"),
    api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0
)


# ============================================================
# STEP 2 - MAIN MCP SERVER URL
# ============================================================

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"


# ============================================================
# STEP 3 - SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an intelligent AI Agent connected to three MCP servers:

1. RAG MCP SERVER
   - Search uploaded CSV and Excel datasets.
   - Retrieve relevant records.
   - Inspect dataset information.
   - Answer questions based on uploaded documents.

2. OPENSTREETMAP MCP SERVER
   - Search geographical locations.
   - Find addresses and coordinates.
   - Search nearby facilities.
   - Retrieve geographical information.

3. OPENWEATHER MCP SERVER
   - Retrieve current weather information.
   - Retrieve weather forecasts.
   - Provide weather information for locations.

INSTRUCTIONS:

- Understand the user's question before selecting tools.
- Use RAG tools when questions relate to uploaded datasets.
- Use OpenStreetMap when geographical information is required.
- Use OpenWeather when weather information is required.
- Combine multiple MCP tools when necessary.
- For weather questions involving uploaded locations,
  retrieve the locations from RAG first.
- Use OpenStreetMap to resolve coordinates when necessary.
- Then use OpenWeather to retrieve weather information.
- Never invent dataset records, coordinates or weather data.
- Clearly explain when information is unavailable.
- Present results in clear natural language.
"""


# ============================================================
# STEP 4 - CONNECT TO MAIN MCP SERVER
# ============================================================

async def connect_mcp():

    print("\nConnecting to Main MCP Aggregator...")

    adapter = MCPAdapter(MCP_SERVER_URL)

    await adapter.__aenter__()

    tools = await adapter.list_tools()

    print("\n====================================")
    print("AVAILABLE AGGREGATED MCP TOOLS")
    print("====================================")

    for tool in tools:

        print("Tool:", tool.name)

    # Create LLM Agent
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT
    )

    print("\nAI Agent successfully initialized!")

    return adapter, agent, tools


# ============================================================
# STEP 5 - ASK AI AGENT
# ============================================================

async def ask_agent(query, messages=None):

    if messages is None:
        messages = []

    adapter = None

    try:

        adapter, agent, tools = await connect_mcp()

        messages.append(
            HumanMessage(content=query)
        )

        previous_count = len(messages)

        response = await agent.ainvoke({
            "messages": messages
        })

        new_messages = response["messages"][previous_count:]

        messages = response["messages"]

        # ====================================================
        # DISPLAY TOOL EXECUTION
        # ====================================================

        execution_details = []

        for message in new_messages:

            if isinstance(message, AIMessage):

                for call in message.tool_calls:

                    detail = {
                        "type": "tool_call",
                        "tool": call["name"],
                        "arguments": call["args"]
                    }

                    execution_details.append(detail)

                    print("\n[TOOL CALL]")
                    print("Tool:", call["name"])
                    print("Arguments:", call["args"])

            elif isinstance(message, ToolMessage):

                detail = {
                    "type": "tool_result",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content
                }

                execution_details.append(detail)

                print("\n[TOOL RESULT]")
                print(message.content)

        # ====================================================
        # EXTRACT FINAL AI RESPONSE
        # ====================================================

        answer = ""

        for message in reversed(new_messages):

            if (
                isinstance(message, AIMessage)
                and not message.tool_calls
            ):

                answer = message.content
                break

        print("\n[FINAL ANSWER]")
        print(answer)

        return {
            "question": query,
            "answer": answer,
            "messages": messages,
            "execution_details": execution_details
        }

    finally:

        if adapter is not None:
            await adapter.__aexit__(None, None, None)


# ============================================================
# STEP 6 - TERMINAL CONVERSATION
# ============================================================

async def main():

    messages = []

    print("\n====================================")
    print("RAG + GEOGRAPHY + WEATHER AI AGENT")
    print("====================================")

    while True:

        user_input = input("\nYou: ").strip()

        if user_input.lower() in [
            "exit",
            "quit",
            "bye"
        ]:

            print("Goodbye!")
            break

        if not user_input:
            continue

        try:

            result = await ask_agent(
                user_input,
                messages
            )

            messages = result["messages"]

        except Exception as e:

            print("\nAgent Error:", str(e))


# ============================================================
# STEP 7 - RUN
# ============================================================

if __name__ == "__main__":

    asyncio.run(main())
