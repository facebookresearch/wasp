# Copyright (c) Meta Platforms, Inc. and affiliates.
import os
import sys

from base_agent import BaseToolCallingAgent, EmailMixin, WebAgentMixin
from constants import (
    EMAIL_TOOLS_DEFINITION_IN_OPENAI_FORMAT,
    Provider,
    WEB_TOOLS_DEFINITION_IN_OPENAI_FORMAT,
)
from openai import AzureOpenAI, OpenAI
import json


class OpenAIAPIGenericToolCallingAgent(BaseToolCallingAgent):
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
        system_objective_message_role: str,
    ):
        super().__init__(model, system_prompt, filepath_to_trace_log, provider)

        self.system_objective_message_role = system_objective_message_role

        if provider == Provider.AZURE_CHAT_COMPLETIONS:
            self.client = AzureOpenAI(
                azure_endpoint=os.environ["AZURE_API_ENDPOINT"],
                api_key=os.environ["AZURE_API_KEY"],
                api_version=os.environ["AZURE_API_VERSION"],
            )
        elif provider == Provider.OPENAI_CHAT_COMPLETIONS:
            self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        elif provider == Provider.OPENAI_CUSTOM_CHAT_COMPLETIONS:
            self.client = OpenAI(
                api_key=os.environ["OPENAI_API_KEY"],
                base_url=os.environ["OPENAI_API_BASE_URL"],
            )
        else:
            raise ValueError(f"Unsupported provider for OpenAI models: {provider}")

    def _call_model(self, messages: list[dict]):
        if (
            not messages[0]["role"] == "system"
            or not messages[0]["content"] == self.system_prompt
        ):
            system_message = {
                "role": self.system_objective_message_role,
                "content": self.system_prompt,
            }

            messages.insert(0, system_message)

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tools_definitions,
        )
        print(
            f"Received model response. Used {completion.usage.prompt_tokens} prompt tokens and {completion.usage.completion_tokens} completion tokens",
            file=sys.stderr,
        )
        return self._parse_model_response(completion.choices[0].message)

    def _create_user_message(self, content):
        """Create a user message with the given content."""
        return {
            "role": "user",
            "content": content,
        }

    def _create_tool_message(self, tool_call, content):
        """Create a tool message with the given ID and content."""
        return {
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": content,
        }

    def _format_tool_response_message(self, tool_call_results):
        return tool_call_results

    def _get_tool_name(self, tool_use_message: dict) -> list[str]:
        return tool_use_message["function"]["name"]

    def _get_tool_arguments(self, tool_use_message: dict) -> dict:
        return json.loads(tool_use_message["function"]["arguments"])

    def _extract_tool_calls(self, response_message: dict) -> list[dict]:
        return response_message["tool_calls"]

    def _create_stop_message(self, answer):
        """Create a stop message with the given answer."""
        return {"role": "stop", "answer": answer}

    def _check_for_stop_action_in_result_of_execution(self, result_of_execution):
        if result_of_execution[0]["role"] == "stop":
            return result_of_execution[0]["answer"]
        return None

    def _parse_model_response(self, response_message):
        """Parse the model response into a standardized format."""
        parsed_message = {
            "role": response_message.role,
            "content": response_message.content,
            "tool_calls": [],
        }

        print(f"Text response: {response_message.content}\n", file=sys.stderr)

        if response_message.tool_calls:
            parsed_message["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in response_message.tool_calls
            ]

            for tool_call in parsed_message["tool_calls"]:
                print(
                    f"Tool call: {tool_call['function']['name']} {tool_call['function']['arguments']}\n",
                    file=sys.stderr,
                )

        return parsed_message

    def _maybe_filter_tool_call_results(
        self, messages: list[dict], max_observations_to_keep: int
    ):
        counter = 0
        indices_of_removal = []
        tool_call_ids_to_remove = set()
        for original_index, message in reversed(list(enumerate(messages))):
            if message["role"] == "tool":
                if "ERROR" in message["content"]:
                    continue
                counter += 1
                if counter > max_observations_to_keep:
                    indices_of_removal.append(original_index)
                    tool_call_ids_to_remove.add(message["tool_call_id"])
            elif message["role"] == "assistant":
                if message["tool_calls"] and any(
                    [
                        tool_call["id"] in tool_call_ids_to_remove
                        for tool_call in message["tool_calls"]
                    ]
                ):
                    indices_of_removal.append(original_index)

        for index_to_remove in indices_of_removal:
            messages.pop(index_to_remove)


class OpenAIResponsesAPIGenericToolCallingAgent(BaseToolCallingAgent):
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
        system_objective_message_role: str,
    ):
        super().__init__(model, system_prompt, filepath_to_trace_log, provider)

        self.system_objective_message_role = system_objective_message_role

        if provider == Provider.OPENAI_RESPONSES:
            self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        elif provider == Provider.OPENAI_CUSTOM_RESPONSES:
            self.client = OpenAI(
                api_key=os.environ["OPENAI_API_KEY"],
                base_url=os.environ["OPENAI_API_BASE_URL"],
            )
        elif provider == Provider.AZURE_RESPONSES:
            self.client = AzureOpenAI(
                azure_endpoint=os.environ["AZURE_API_ENDPOINT"],
                api_key=os.environ["AZURE_API_KEY"],
                api_version=os.environ["AZURE_API_VERSION"],
            )
        else:
            raise ValueError(f"Unsupported provider for OpenAI models: {provider}")

    def _convert_chat_tools_to_responses_format(self, chat_tools):
        """Convert Chat Completions API tool format to Responses API tool format."""
        responses_tools = []
        for tool in chat_tools:
            if tool["type"] == "function":
                # Flatten the structure - move function properties to top level
                responses_tool = {
                    "type": "function",
                    "name": tool["function"]["name"],
                    "description": tool["function"]["description"],
                    "parameters": tool["function"]["parameters"],
                }
                responses_tools.append(responses_tool)
        return responses_tools

    def _call_model(self, messages: list[dict]):
        if (
            not messages[0]["role"] == "system"
            or not messages[0]["content"] == self.system_prompt
        ):
            system_message = {
                "role": self.system_objective_message_role,
                "content": self.system_prompt,
            }

            messages.insert(0, system_message)

        response = self.client.responses.create(
            model=self.model,
            input=messages,
            tools=self.tools_definitions,
            truncation="auto",
        )

        print(f"Received model response from Responses API", file=sys.stderr)
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
            "type": "function_call_output",
            "call_id": tool_call["call_id"],
            "output": content,
        }

    def _format_tool_response_message(self, tool_call_results):
        return tool_call_results

    def _get_tool_name(self, tool_use_message: dict) -> str:
        return tool_use_message["name"]

    def _get_tool_arguments(self, tool_use_message: dict) -> dict:
        return json.loads(tool_use_message["arguments"])

    def _extract_tool_calls(self, response_message: list[dict]) -> list[dict]:
        # response_message is now a list of parsed messages from _parse_model_response
        return [
            message
            for message in response_message
            if message.get("type") == "function_call"
        ]

    def _create_stop_message(self, answer):
        """Create a stop message with the given answer."""
        return {"type": "stop", "answer": answer}

    def _check_for_stop_action_in_result_of_execution(self, result_of_execution):
        if result_of_execution and result_of_execution[0]["type"] == "stop":
            return result_of_execution[0]["answer"]
        return None

    def _parse_model_response(self, response):
        """Parse the Responses API response into a standardized format."""

        print(f"Response output: {response.output}\n", file=sys.stderr)
        parsed_messages = []

        for response_item in response.output:
            if response_item.type == "function_call":
                print(
                    f"Tool call: {response_item.name} {response_item.arguments}\n",
                    file=sys.stderr,
                )
                parsed_message = {
                    "type": response_item.type,
                    "id": response_item.id,
                    "call_id": response_item.call_id,
                    "name": response_item.name,
                    "arguments": response_item.arguments,
                }
                parsed_messages.append(parsed_message)
            elif response_item.type == "message":
                # Output message from the model
                parsed_message = {
                    "type": response_item.type,
                    "id": response_item.id,
                    "role": response_item.role,
                    "content": [],
                }
                for content_item in response_item.content:
                    if content_item.type == "refusal":
                        parsed_message["content"].append(
                            {"type": "refusal", "text": content_item.refusal}
                        )
                        print(f"Refusal: {content_item.refusal}\n", file=sys.stderr)
                    elif content_item.type == "output_text":
                        parsed_message["content"].append(
                            {"type": "output_text", "text": content_item.text}
                        )
                        print(f"Text output: {content_item.text}\n", file=sys.stderr)
                    else:
                        raise ValueError(
                            f"Unsupported content type: {content_item['type']}"
                        )
                if hasattr(response_item, "status"):
                    parsed_message["status"] = response_item.status
                parsed_messages.append(parsed_message)
            elif response_item.type == "reasoning":
                # Reasoning content
                parsed_message = {
                    "type": response_item.type,
                    "id": response_item.id,
                    "content": response_item.content,
                    "summary": response_item.summary,
                }
                print(f"Reasoning: {response_item.content}\n", file=sys.stderr)
                if hasattr(response_item, "status"):
                    parsed_message["status"] = response_item.status
                if hasattr(response_item, "encrypted_content"):
                    parsed_message["encrypted_content"] = (
                        response_item.encrypted_content
                    )
                # note that we do NOT attach the reasoning message to the parsed messages
                # as it is not part of the final output, but rather an internal reasoning step
            else:
                raise ValueError(
                    f"Unsupported response item type: {response_item.type}"
                )

        return parsed_messages

    def _maybe_filter_tool_call_results(
        self, messages: list[dict], max_observations_to_keep: int
    ):
        counter = 0
        indices_of_removal = []
        tool_call_ids_to_remove = set()
        for original_index, message in reversed(list(enumerate(messages))):
            if "type" not in message:
                continue

            if message["type"] == "function_call_output":
                counter += 1
                if counter > max_observations_to_keep:
                    indices_of_removal.append(original_index)
                    tool_call_ids_to_remove.add(message["call_id"])
            elif message["type"] == "function_call":
                if message["call_id"] in tool_call_ids_to_remove:
                    indices_of_removal.append(original_index)

        for index_to_remove in indices_of_removal:
            messages.pop(index_to_remove)


class OpenAIAPIWebAgent(OpenAIAPIGenericToolCallingAgent, WebAgentMixin):
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
        system_objective_message_role: str,
    ):
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            filepath_to_trace_log=filepath_to_trace_log,
            provider=provider,
            system_objective_message_role=system_objective_message_role,
        )
        self.tools_definitions = WEB_TOOLS_DEFINITION_IN_OPENAI_FORMAT


class OpenAIResponsesAPIWebAgent(
    OpenAIResponsesAPIGenericToolCallingAgent, WebAgentMixin
):
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
        system_objective_message_role: str,
    ):
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            filepath_to_trace_log=filepath_to_trace_log,
            provider=provider,
            system_objective_message_role=system_objective_message_role,
        )
        self.tools_definitions = self._convert_chat_tools_to_responses_format(
            WEB_TOOLS_DEFINITION_IN_OPENAI_FORMAT
        )


class OpenAIAPIEmailAgent(OpenAIAPIGenericToolCallingAgent, EmailMixin):
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
        system_objective_message_role: str,
    ):
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            filepath_to_trace_log=filepath_to_trace_log,
            provider=provider,
            system_objective_message_role=system_objective_message_role,
        )
        self.tools_definitions = EMAIL_TOOLS_DEFINITION_IN_OPENAI_FORMAT


class OpenAIResponsesAPIEmailAgent(
    OpenAIResponsesAPIGenericToolCallingAgent, EmailMixin
):
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
        system_objective_message_role: str,
    ):
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            filepath_to_trace_log=filepath_to_trace_log,
            provider=provider,
            system_objective_message_role=system_objective_message_role,
        )
        self.tools_definitions = self._convert_chat_tools_to_responses_format(
            EMAIL_TOOLS_DEFINITION_IN_OPENAI_FORMAT
        )
