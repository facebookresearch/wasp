import json
import os
import sys
from typing import Any, Dict, List

from anthropic import Anthropic, AnthropicBedrock
from anthropic.types.beta import (
    BetaToolUnionParam,
)

from base_agent import BaseToolCallingAgent, WebAgentMixin, EmailMixin
from constants import (
    Provider,
    WEB_TOOLS_DEFINITION_IN_OPENAI_FORMAT,
    EMAIL_TOOLS_DEFINITION_IN_OPENAI_FORMAT,
)


class AnthropicAPIGenericToolCallingAgent(BaseToolCallingAgent):
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
        enable_thinking: bool = False,
        thinking_budget_tokens: int = 10000,
        enable_interleaved_thinking: bool = False,
        max_tokens: int = 4096,
        temperature: float = 1.0,
    ):
        super().__init__(model, system_prompt, filepath_to_trace_log, provider)

        # Initialize the appropriate client based on provider
        if provider == Provider.ANTHROPIC:
            self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        elif provider == Provider.BEDROCK:
            self.client = AnthropicBedrock(
                aws_access_key=os.environ["AWS_ACCESS_KEY_ID"],
                aws_secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
                aws_session_token=os.environ["AWS_SESSION_TOKEN"],
                aws_region=os.environ["AWS_REGION"],
            )
        else:
            raise ValueError(f"Unsupported provider for Anthropic models: {provider}")

        self.max_tokens = max_tokens
        self.temperature = temperature
        self.enable_thinking = enable_thinking

        if self.enable_thinking:
            self.thinking_parameter_for_model_call = {
                "type": "enabled",
                "budget_tokens": thinking_budget_tokens,
            }
            self.max_tokens = self.max_tokens + thinking_budget_tokens

        if enable_interleaved_thinking:
            self.extra_headers_parameter_for_model_call = {
                "anthropic-beta": "interleaved-thinking-2025-05-14"
            }
        else:
            self.extra_headers_parameter_for_model_call = {}

    def _convert_to_anthropic_tool_format(self, openai_tools):
        """Convert OpenAI tool definitions to Anthropic format."""
        anthropic_tools: List[BetaToolUnionParam] = []
        for tool in openai_tools:
            if tool["type"] == "function":
                function_info = tool["function"]
                anthropic_tool: BetaToolUnionParam = {
                    "name": function_info["name"],
                    "description": function_info.get("description", ""),
                    "input_schema": function_info["parameters"],
                }
                anthropic_tools.append(anthropic_tool)
        return anthropic_tools

    def _call_model(self, messages: List[Dict[str, Any]]):
        """Call the Anthropic API with the given messages and tools."""

        if self.enable_thinking:
            response = self.client.messages.create(
                model=self.model,
                messages=messages,
                tools=self.tools_definitions,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.system_prompt,
                thinking=self.thinking_parameter_for_model_call,
                extra_headers=self.extra_headers_parameter_for_model_call,
            )
        else:
            response = self.client.messages.create(
                model=self.model,
                messages=messages,
                tools=self.tools_definitions,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.system_prompt,
            )

        return self._parse_model_response(response)

    def _create_user_message(self, content):
        """Create a user message with the given content."""
        return {
            "role": "user",
            "content": content,
        }

    def _create_tool_message(self, tool_call, content):
        """Create a tool message with the given ID and content."""
        return {
            "type": "tool_result",
            "tool_use_id": tool_call["id"],
            "content": content,
        }

    def _format_tool_response_message(self, tool_call_results) -> list[dict]:
        return [
            {
                "role": "user",
                "content": tool_call_results,
            }
        ]

    def _get_tool_name(self, tool_use_message: dict) -> list[str]:
        return tool_use_message["name"]

    def _get_tool_arguments(self, tool_use_message: dict) -> dict:
        return tool_use_message["input"]

    def _extract_tool_calls(self, response_message: dict) -> list[dict]:
        return [
            block
            for block in response_message["content"]
            if block["type"] == "tool_use"
        ]

    def _check_for_stop_action_in_result_of_execution(self, result_of_execution):
        for action in result_of_execution:
            if "role" in action and action["role"] == "stop":
                return action["answer"]
        return None

    def _create_stop_message(self, answer):
        """Create a stop message with the given answer."""
        return {"role": "stop", "answer": answer}

    def _parse_model_response(self, response_message):
        """Parse the Anthropic API response into a standardized format."""
        parsed_message = {
            "role": "assistant",
            "content": [],
        }

        # Extract text content and tool use blocks
        for content_block in response_message.content:
            if content_block.type == "text":
                print(f"Text response: {content_block.text}\n", file=sys.stderr)

                parsed_message["content"].append(
                    {
                        "type": "text",
                        "text": content_block.text,
                    }
                )
            elif content_block.type == "tool_use":
                print(
                    f"Tool call: {content_block.name} {content_block.input}\n",
                    file=sys.stderr,
                )

                tool_call = {
                    "type": "tool_use",
                    "id": content_block.id,
                    "name": content_block.name,
                    "input": content_block.input,
                }
                parsed_message["content"].append(tool_call)
            elif content_block.type == "thinking":
                print(f"Thinking: {content_block.thinking}\n", file=sys.stderr)

                parsed_message["content"].append(
                    {
                        "type": "thinking",
                        "thinking": content_block.thinking,
                        "signature": content_block.signature,
                    }
                )
            elif content_block.type == "redacted_thinking":
                print(f"Thinking: [redacted by API]\n", file=sys.stderr)

                parsed_message["content"].append(
                    {
                        "type": "redacted_thinking",
                        "data": content_block.data,
                    }
                )
            else:
                raise NotImplementedError(
                    f"Unsupported content block type: {content_block.type}"
                )

        return parsed_message

    def _maybe_filter_tool_call_results(
        self, messages: List[Dict[str, Any]], max_observations_to_keep: int
    ):
        """Filter out old tool call results to keep the context window manageable."""
        counter = 0
        indices_of_removal = []
        tool_call_ids_to_remove = set()

        for original_index, message in reversed(list(enumerate(messages))):
            if message["role"] == "user" and any(
                [
                    isinstance(x, dict) and x["type"] == "tool_result"
                    for x in message.get("content", [])
                ]
            ):
                counter += 1
                if counter > max_observations_to_keep:
                    indices_of_removal.append(original_index)
                    for content_block in message["content"]:
                        if content_block["type"] == "tool_result":
                            tool_call_ids_to_remove.add(content_block["tool_use_id"])
            elif message["role"] == "assistant":
                if any(
                    [
                        content_block["id"] in tool_call_ids_to_remove
                        for content_block in message["content"]
                        if content_block["type"] == "tool_use"
                    ]
                ):
                    indices_of_removal.append(original_index)

        for index_to_remove in sorted(indices_of_removal, reverse=True):
            messages.pop(index_to_remove)


class AnthropicAPIWebAgent(AnthropicAPIGenericToolCallingAgent, WebAgentMixin):
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
        enable_thinking: bool = False,
        thinking_budget_tokens: int = 10000,
        enable_interleaved_thinking: bool = False,
    ):
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            filepath_to_trace_log=filepath_to_trace_log,
            provider=provider,
            enable_thinking=enable_thinking,
            thinking_budget_tokens=thinking_budget_tokens,
            enable_interleaved_thinking=enable_interleaved_thinking,
        )

        self.tools_definitions = self._convert_to_anthropic_tool_format(
            WEB_TOOLS_DEFINITION_IN_OPENAI_FORMAT
        )


class AnthropicEmailAgent(AnthropicAPIGenericToolCallingAgent, EmailMixin):
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
        enable_thinking: bool = False,
        thinking_budget_tokens: int = 10000,
        enable_interleaved_thinking: bool = False,
    ):
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            filepath_to_trace_log=filepath_to_trace_log,
            provider=provider,
            enable_thinking=enable_thinking,
            thinking_budget_tokens=thinking_budget_tokens,
            enable_interleaved_thinking=enable_interleaved_thinking,
        )

        self.tools_definitions = self._convert_to_anthropic_tool_format(
            EMAIL_TOOLS_DEFINITION_IN_OPENAI_FORMAT
        )
