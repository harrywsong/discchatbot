from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from groq import AsyncGroq, RateLimitError as GroqRateLimit

from .base import ImageContent, LLMError, LLMProvider, Message, RateLimitError

logger = logging.getLogger(__name__)

# Tool definitions in OpenAI-compatible format
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information. Use this when you need up-to-date "
                "facts, recent news, or any information that may have changed after your "
                "training cutoff."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (1-10, default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read content from a file that has been uploaded/indexed in this channel."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename to read"},
                    "query": {
                        "type": "string",
                        "description": "What information to look for in the file",
                    },
                },
                "required": ["filename"],
            },
        },
    },
]


def _build_messages(
    messages: list[Message], system_prompt: Optional[str]
) -> list[dict]:
    result = []
    if system_prompt:
        result.append({"role": "system", "content": system_prompt})
    for msg in messages:
        if msg.role == "system":
            result.append({"role": "system", "content": msg.content})
        else:
            # Groq doesn't support vision - strip images, keep text
            result.append({"role": msg.role, "content": msg.content})
    return result


class GroqProvider(LLMProvider):
    name = "groq"
    supports_vision = False
    supports_tools = True

    def __init__(self, api_key: str, model: str = "meta-llama/llama-4-scout-17b-16e-instruct") -> None:
        self._client = AsyncGroq(api_key=api_key)
        self._model = model

    async def complete(
        self,
        messages: list[Message],
        system_prompt: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ) -> str:
        msgs = _build_messages(messages, system_prompt)
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=msgs,
                temperature=0.7,
                max_tokens=4096,
            )
            return response.choices[0].message.content or ""
        except GroqRateLimit as e:
            raise RateLimitError(f"Groq rate limit: {e}") from e
        except Exception as e:
            raise LLMError(f"Groq error: {e}") from e

    async def complete_with_tools(
        self,
        messages: list[Message],
        tools: list[dict],
        system_prompt: Optional[str] = None,
    ) -> tuple[str, list[dict]]:
        msgs = _build_messages(messages, system_prompt)
        tool_calls_made: list[dict] = []

        for _ in range(10):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=msgs,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    temperature=0.7,
                    max_tokens=4096,
                )
            except GroqRateLimit as e:
                raise RateLimitError(f"Groq rate limit: {e}") from e
            except Exception as e:
                raise LLMError(f"Groq error: {e}") from e

            choice = response.choices[0]
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                # Add assistant message with tool calls
                msgs.append({
                    "role": "assistant",
                    "content": choice.message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in choice.message.tool_calls
                    ],
                })

                for tc in choice.message.tool_calls:
                    tool_name = tc.function.name
                    try:
                        tool_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}

                    result = await self._execute_tool(tool_name, tool_args, tools)
                    tool_calls_made.append({"name": tool_name, "args": tool_args, "result": result})

                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                return choice.message.content or "", tool_calls_made

        return choice.message.content or "", tool_calls_made

    async def _execute_tool(self, name: str, args: dict, tools: list[dict]) -> str:
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
