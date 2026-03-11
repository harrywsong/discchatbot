from __future__ import annotations

import asyncio
import base64
import logging
from typing import Optional

import google.genai as genai
import google.genai.types as gtypes

from .base import ImageContent, LLMError, LLMProvider, Message, RateLimitError

logger = logging.getLogger(__name__)

# Tool definitions exposed to Gemini
TOOL_DEFINITIONS = gtypes.Tool(
    function_declarations=[
        gtypes.FunctionDeclaration(
            name="web_search",
            description=(
                "Search the web for current information. Use this when you need up-to-date "
                "facts, recent news, or any information that may have changed after your "
                "training cutoff."
            ),
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={
                    "query": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description="The search query",
                    ),
                    "num_results": gtypes.Schema(
                        type=gtypes.Type.INTEGER,
                        description="Number of results to return (1-10, default 5)",
                    ),
                },
                required=["query"],
            ),
        ),
        gtypes.FunctionDeclaration(
            name="read_file",
            description=(
                "Read content from a file that has been uploaded/indexed in this channel. "
                "Use this to answer questions about uploaded documents."
            ),
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={
                    "filename": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description="The filename to read",
                    ),
                    "query": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description="What information to look for in the file",
                    ),
                },
                required=["filename"],
            ),
        ),
        gtypes.FunctionDeclaration(
            name="get_weather",
            description="Get the current weather and today's forecast for any location.",
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={
                    "location": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description="City name, e.g. 'London', 'New York', 'Tokyo'",
                    ),
                },
                required=["location"],
            ),
        ),
        gtypes.FunctionDeclaration(
            name="calculate",
            description=(
                "Evaluate a mathematical expression. Supports arithmetic, math functions "
                "(sqrt, sin, cos, log, etc.), and constants (pi, e). "
                "Use this for any calculation rather than doing it mentally."
            ),
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={
                    "expression": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description="The math expression to evaluate, e.g. 'sqrt(2) * pi'",
                    ),
                },
                required=["expression"],
            ),
        ),
        gtypes.FunctionDeclaration(
            name="get_current_time",
            description="Get the current date and time in any timezone.",
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={
                    "timezone": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description=(
                            "IANA timezone name, e.g. 'America/New_York', 'Europe/London', "
                            "'Asia/Tokyo', or abbreviations like 'EST', 'PST', 'UTC'."
                        ),
                    ),
                },
                required=["timezone"],
            ),
        ),
        gtypes.FunctionDeclaration(
            name="fetch_webpage",
            description=(
                "Fetch and extract the text content of a webpage. "
                "Use this to read articles, documentation, or any URL the user shares."
            ),
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={
                    "url": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description="The full URL to fetch",
                    ),
                },
                required=["url"],
            ),
        ),
        gtypes.FunctionDeclaration(
            name="run_python",
            description=(
                "Execute Python code in a sandboxed environment and return the output. "
                "Use this for complex calculations, data processing, string manipulation, "
                "or anything that benefits from running actual code. "
                "Available modules: math, random, json, datetime, re, string, collections, "
                "itertools, functools."
            ),
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={
                    "code": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description="Python code to execute",
                    ),
                },
                required=["code"],
            ),
        ),
        gtypes.FunctionDeclaration(
            name="get_server_info",
            description="Get information about this Discord server (member count, channels, etc.).",
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={},
            ),
        ),
        gtypes.FunctionDeclaration(
            name="get_user_info",
            description=(
                "Look up a Discord user in this server by their username, display name, or ID. "
                "Returns their mention format, roles, and join date. "
                "Use this to find a user's ID before mentioning them."
            ),
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={
                    "username_or_id": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description="Username, display name, or numeric user ID",
                    ),
                },
                required=["username_or_id"],
            ),
        ),
        gtypes.FunctionDeclaration(
            name="set_reminder",
            description=(
                "Set a reminder that will ping the user in this channel after a delay. "
                "Use this when the user asks to be reminded about something."
            ),
            parameters=gtypes.Schema(
                type=gtypes.Type.OBJECT,
                properties={
                    "message": gtypes.Schema(
                        type=gtypes.Type.STRING,
                        description="What to remind the user about",
                    ),
                    "delay_minutes": gtypes.Schema(
                        type=gtypes.Type.NUMBER,
                        description="How many minutes from now to send the reminder",
                    ),
                },
                required=["message", "delay_minutes"],
            ),
        ),
    ]
)


def _build_contents(messages: list[Message]) -> list[gtypes.Content]:
    contents = []
    for msg in messages:
        if msg.role == "system":
            # Gemini doesn't have system role in contents - handled via system_instruction
            continue
        parts: list[gtypes.Part] = []
        if msg.images:
            for img in msg.images:
                parts.append(
                    gtypes.Part.from_bytes(data=img.data, mime_type=img.mime_type)
                )
        if msg.content:
            parts.append(gtypes.Part.from_text(text=msg.content))
        if parts:
            role = "user" if msg.role == "user" else "model"
            contents.append(gtypes.Content(role=role, parts=parts))
    return contents


class GeminiProvider(LLMProvider):
    name = "gemini"
    supports_vision = True
    supports_tools = True

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def complete(
        self,
        messages: list[Message],
        system_prompt: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ) -> str:
        contents = _build_contents(messages)
        config = gtypes.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
        )
        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model,
                contents=contents,
                config=config,
            )
            return response.text or ""
        except Exception as e:
            self._handle_error(e)

    async def complete_with_tools(
        self,
        messages: list[Message],
        tools: list[dict],  # tool executor callables keyed by name
        system_prompt: Optional[str] = None,
    ) -> tuple[str, list[dict]]:
        contents = _build_contents(messages)
        config = gtypes.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            tools=[TOOL_DEFINITIONS],
        )
        tool_calls_made: list[dict] = []

        for _ in range(10):  # max tool call rounds
            try:
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=self._model,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                self._handle_error(e)

            # Check for function calls
            fn_calls = []
            for candidate in response.candidates or []:
                for part in candidate.content.parts or []:
                    if part.function_call:
                        fn_calls.append(part.function_call)

            if not fn_calls:
                return response.text or "", tool_calls_made

            # Execute each tool call
            fn_responses = []
            for fc in fn_calls:
                tool_name = fc.name
                tool_args = dict(fc.args) if fc.args else {}

                # Find and execute the tool
                result = await self._execute_tool(tool_name, tool_args, tools)
                tool_calls_made.append({"name": tool_name, "args": tool_args, "result": result})

                fn_responses.append(
                    gtypes.Part.from_function_response(
                        name=tool_name,
                        response={"result": result},
                    )
                )

            # Add model response and tool results to conversation
            contents.append(response.candidates[0].content)
            contents.append(gtypes.Content(role="user", parts=fn_responses))

        return response.text or "", tool_calls_made

    async def _execute_tool(
        self, name: str, args: dict, tools: list[dict]
    ) -> str:
        for tool in tools:
            if tool.get("name") == name:
                fn = tool.get("fn")
                if fn:
                    try:
                        result = await fn(**args)
                        return str(result)
                    except Exception as e:
                        return f"Tool error: {e}"
        return f"Unknown tool: {name}"

    def _handle_error(self, e: Exception) -> None:
        msg = str(e).lower()
        if "429" in msg or "quota" in msg or "resource exhausted" in msg or "rate" in msg:
            raise RateLimitError(f"Gemini rate limit: {e}") from e
        raise LLMError(f"Gemini error: {e}") from e
