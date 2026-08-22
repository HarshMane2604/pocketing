"""
Qwen AI agent for Pocketing — uses the MCP server in this directory.

Standalone usage (original):
    python ai_client.py

As a library (called from telegram.py):
    from mcp_pocketing.ai_client import run_ai_agent
    answer = await run_ai_agent("find my Redis note", chat_id="12345")
"""

from json import JSONDecodeError
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logger = logging.getLogger(__name__)

# MCP server lives alongside this file
_SERVER_PATH = str(Path(__file__).parent / "server.py")

# ── Ollama settings ────────────────────────────────────────────────────────────
# When imported by the backend, read from app config.
# When run standalone (python ai_client.py), fall back to these defaults.
_OLLAMA_URL_DEFAULT = "http://127.0.0.1:11434/api/chat"
_MODEL_DEFAULT = "qwen3.5:4b"


def _get_ollama_settings() -> tuple[str, str]:
    """Return (ollama_url, model). Reads from app config when available."""
    try:
        from app.config import get_settings
        s = get_settings()
        return s.ollama_url, s.ollama_model
    except Exception:
        return _OLLAMA_URL_DEFAULT, _MODEL_DEFAULT


def _get_ai_logger():
    """Return the dedicated AI file logger. Falls back to module logger if unavailable."""
    try:
        from pocketing_logging.logger import get_ai_logger
        return get_ai_logger()
    except Exception:
        return logger


# ── Helpers ────────────────────────────────────────────────────────────────────

def convert_mcp_tools_to_ollama(mcp_tools):
    tools = []
    for tool in mcp_tools:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.input_schema,
                }
            }
        )
    return tools


async def ask_qwen(messages, tools):
    url, model = _get_ollama_settings()
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "think": False,
        "stream": False,
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=300)
        response.raise_for_status()
        return response.json()


def extract_tool_output(results):
    if results.structured_content:
        return results.structured_content
    output = []
    for item in results.content:
        if hasattr(item, "text"):
            try:
                output.append(json.loads(item.text))
            except json.JSONDecodeError:
                output.append(item.text)
        elif hasattr(item, "model_dump"):
            output.append(item.model_dump())
        else:
            output.append(str(item))
    return output


# ── DB persistence (only when running inside the backend) ─────────────────────

async def _save_conversation(chat_id: str, user_query: str, ai_response: str) -> int | None:
    """Persist the AI conversation to ai_conversations table. Returns row ID or None."""
    try:
        from app.database import SessionLocal
        from app.models import AiConversation
        async with SessionLocal() as session:
            record = AiConversation(
                chat_id=chat_id,
                user_query=user_query,
                ai_response=ai_response,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record.id
    except Exception as exc:
        logger.warning("Could not save AI conversation to DB: %s", exc)
        return None


# ── Core agent loop ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are the Pocketing AI assistant. "
    "You have access to Pocketing through MCP tools. "
    "Use tools whenever they are required. "
    "Never invent note IDs or note contents. "
    "When searching for a note, extract a concise keyword from the user's request. "
    "If a search returns no results, reconsider the search query and try a broader "
    "relevant keyword before concluding that nothing exists. "
    "When a search returns a note ID and the user wants to modify that note, "
    "use the returned ID with update_note. "
    "You may call multiple tools sequentially. "
    "After every tool result, decide whether another tool is required. "
    "Only provide a final answer when the user's request has been completed "
    "or when the available tools cannot accomplish it. "
    "Keep responses concise and friendly — they will be sent to Telegram."
)

_SEPARATOR = "═" * 65
_LINE = "─" * 65


async def run_ai_agent(user_message: str, chat_id: str = "") -> str:
    """
    Run the Qwen AI agent for a single user message.

    Spawns mcp_pocketing/server.py as a stdio subprocess, runs the full
    tool-calling agent loop, and returns the final response string.

    Args:
        user_message: The user's request (suffix /ai already stripped).
        chat_id:      Telegram chat ID — used to persist the conversation
                      to the ai_conversations table. Leave empty to skip saving.

    Returns:
        The AI's final answer as a plain string. Never raises.
    """
    ai_log = _get_ai_logger()
    start_time = time.time()

    ai_log.info(_SEPARATOR)
    ai_log.info("NEW AI REQUEST")
    ai_log.info("  Chat ID:  %s", chat_id or "(standalone)")
    ai_log.info("  User:     \"%s\"", user_message)
    ai_log.info(_LINE)

    server_params = StdioServerParameters(
        command=sys.executable,   # same venv Python — all packages resolve correctly
        args=[_SERVER_PATH],
    )

    answer = "⚠️ The agent reached its iteration limit without a final answer."
    status = "ITERATION_LIMIT"

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                tools_result = await session.list_tools()
                mcp_tools = tools_result.tools
                available_tools = {tool.name for tool in mcp_tools}
                ollama_tools = convert_mcp_tools_to_ollama(mcp_tools)

                tool_names = [t.name for t in mcp_tools]
                ai_log.info("MCP SESSION STARTED")
                ai_log.info("  Server:   mcp_pocketing/server.py")
                ai_log.info("  Tools:    %s", ", ".join(tool_names))
                ai_log.info(_LINE)

                messages = [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ]

                for iteration in range(10):
                    iter_start = time.time()
                    response = await ask_qwen(messages, ollama_tools)
                    qwen_ms = int((time.time() - iter_start) * 1000)
                    assistant_message = response["message"]
                    tool_calls = assistant_message.get("tool_calls", [])
                    thought = assistant_message.get("content", "").strip()

                    ai_log.info("QWEN ITERATION %d  (%dms)", iteration + 1, qwen_ms)

                    if thought:
                        # Truncate very long thoughts for the log
                        display = thought[:500] + ("..." if len(thought) > 500 else "")
                        ai_log.info("  Thought:  %s", display)

                    # No tool call → final answer
                    if not tool_calls:
                        answer = thought or "✅ Done."
                        status = "SUCCESS"
                        ai_log.info("  Final Answer: %s", answer[:300])
                        break

                    # Process tool calls
                    messages.append(assistant_message)

                    for tool_call in tool_calls:
                        function  = tool_call["function"]
                        tool_name = function["name"]
                        arguments = function["arguments"]

                        ai_log.info("  Tool Call: %s", tool_name)
                        ai_log.info("  Arguments: %s", json.dumps(arguments, ensure_ascii=False))

                        if tool_name not in available_tools:
                            ai_log.warning("  ⚠ UNKNOWN TOOL: %s", tool_name)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.get("id", ""),
                                "content": json.dumps({"error": f"Unknown tool: {tool_name}"}),
                            })
                            continue

                        tool_start = time.time()
                        result      = await session.call_tool(tool_name, arguments)
                        tool_ms = int((time.time() - tool_start) * 1000)
                        tool_output = extract_tool_output(result)

                        # Log tool result — truncate if huge
                        output_str = json.dumps(tool_output, ensure_ascii=False)
                        display_output = output_str[:1000] + ("..." if len(output_str) > 1000 else "")

                        ai_log.info("  MCP RESULT (%dms):", tool_ms)
                        ai_log.info("    Tool:   %s", tool_name)
                        ai_log.info("    Output: %s", display_output)

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": json.dumps(tool_output),
                        })

                    ai_log.info(_LINE)

    except Exception as exc:
        status = "ERROR"
        answer = f"⚠️ AI error: {type(exc).__name__}: {exc}"
        ai_log.error("AI AGENT ERROR")
        ai_log.error("  Type:      %s", type(exc).__name__)
        ai_log.error("  Message:   %s", exc)
        import traceback
        ai_log.error("  Traceback:\n%s", traceback.format_exc())

    # Save to DB
    db_id = None
    if chat_id:
        db_id = await _save_conversation(chat_id, user_message, answer)

    elapsed = round(time.time() - start_time, 2)

    ai_log.info("AI REQUEST COMPLETE")
    ai_log.info("  Status:   %s", status)
    ai_log.info("  Duration: %ss", elapsed)
    if db_id:
        ai_log.info("  Saved to DB: yes (ai_conversations.id = %d)", db_id)
    elif chat_id:
        ai_log.info("  Saved to DB: failed")
    else:
        ai_log.info("  Saved to DB: skipped (no chat_id)")
    ai_log.info(_SEPARATOR)

    return answer


# ── Standalone entry point (original behaviour preserved) ─────────────────────

async def main():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[_SERVER_PATH],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            print("\nConnected to Pocketing MCP server.")

            tools_result = await session.list_tools()
            mcp_tools = tools_result.tools
            available_tools = {tool.name for tool in mcp_tools}
            print("\nTools discovered from MCP:")
            for tool in mcp_tools:
                print(f"  - {tool.name}")

            ollama_tools = convert_mcp_tools_to_ollama(mcp_tools)

            # ── Change this to test different requests ──────────────────
            user_request = "Show me all my unfinished notes."
            # user_request = "Find my MCP resource and give me its full details."
            # user_request = "Find my note related to mcp and please find my resume"
            # user_request = "Whats is in my resume."
            # user_request = "Send me the PDF I uploaded today"
            # user_request = "Remember that I need to learn Redis for backend development."
            # ───────────────────────────────────────────────────────────

            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_request},
            ]
            print(f"\nUser Request: {user_request}")

            while True:
                response = await ask_qwen(messages, ollama_tools)
                assistant_message = response["message"]
                tool_calls = assistant_message.get("tool_calls", [])

                if not tool_calls:
                    print("\nFinal Answer:")
                    print(assistant_message.get("content", ""))
                    break

                print("\nQwen selected tools:")
                messages.append(assistant_message)

                for tool_call in tool_calls:
                    function  = tool_call["function"]
                    tool_name = function["name"]
                    arguments = function["arguments"]
                    print(f"  Tool = {tool_name}")
                    print(f"  Args = {arguments}")

                    if tool_name not in available_tools:
                        print(f"  Error: unknown tool {tool_name}")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.get("id", ""),
                            "content": json.dumps({"error": f"Unknown tool: {tool_name}"}),
                        })
                        continue

                    result      = await session.call_tool(tool_name, arguments)
                    tool_output = extract_tool_output(result)
                    print(f"\nMCP returned:\n{json.dumps(tool_output, indent=2)}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": json.dumps(tool_output),
                    })


if __name__ == "__main__":
    asyncio.run(main())
