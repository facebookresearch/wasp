import os
import sys

from base_agent import BaseWebAgent
from constants import Provider, WEB_TOOLS_DEFINITION_IN_OPENAI_FORMAT
from openai import AzureOpenAI, OpenAI


class OpenAIAPIWebAgent(BaseWebAgent):
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

        if provider == Provider.AZURE:
            self.client = AzureOpenAI(
                azure_endpoint=os.environ["AZURE_API_ENDPOINT"],
                api_key=os.environ["AZURE_API_KEY"],
                api_version=os.environ["AZURE_API_VERSION"],
            )
        elif provider == Provider.OPENAI:
            self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        elif provider == Provider.GOOGLE_OPENAI:
            self.client = OpenAI(
                api_key=os.environ["GCP_API_KEY"],
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
        else:
            raise ValueError(f"Unsupported provider for OpenAI models: {provider}")

        self.tools_definitions = WEB_TOOLS_DEFINITION_IN_OPENAI_FORMAT

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

    def _create_tool_message(self, tool_call_id, content):
        """Create a tool message with the given ID and content."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }

    def _format_tool_response_message(self, tool_call_results):
        return tool_call_results

    def _get_tool_name(self, tool_use_message: dict) -> list[str]:
        return tool_use_message["function"]["name"]

    def _get_tool_arguments(self, tool_use_message: dict) -> dict:
        return tool_use_message["function"]["arguments"]

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

        return parsed_message

    def _maybe_filter_tool_call_results(
        self, messages: list[dict], max_observations_to_keep: int
    ):
        counter = 0
        indices_of_removal = []
        tool_call_ids_to_remove = set()
        for original_index, message in reversed(list(enumerate(messages))):
            if message["role"] == "tool":
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
