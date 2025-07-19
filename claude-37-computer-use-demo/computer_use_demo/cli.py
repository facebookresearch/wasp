# Copyright (c) Meta Platforms, Inc. and affiliates.
import asyncio
from enum import StrEnum
import json
import os
import sys

import click
from computer_use_demo.loop import sampling_loop
from anthropic.types.beta import BetaContentBlockParam, BetaTextBlockParam
from computer_use_demo.tools import ToolResult
import httpx


class Sender(StrEnum):
    USER = "user"
    BOT = "assistant"
    TOOL = "tool"


def _output_callback(message: BetaContentBlockParam):
    pass


def _tool_callback(message: ToolResult, some_other_str: str):
    pass


class APIRequestsLogger:
    def __init__(self, file_path_to_write_to: str):
        self.file_path_to_write_to = file_path_to_write_to
        self.turn = 0

    def log_claude(
        self,
        request: httpx.Request,
        response: httpx.Response | object | None,
        error: Exception | None,
    ):
        with open(self.file_path_to_write_to, "a") as f:
            latest_request = json.loads(request.content.decode("utf-8"))

            latest_messages = latest_request["messages"]
            system_message_content = latest_request["system"]
            system_message = {"role": "system", "content": system_message_content}
            latest_messages.insert(0, system_message)
            f.write(json.dumps(latest_messages) + "\n")

            if not error:
                latest_response = json.loads(response.content)["content"]

                latest_response_first_text = ""
                for member in latest_response:
                    if member["type"] == "text":
                        latest_response_first_text = member["text"]
                print(
                    f"[Model response number {self.turn}] {latest_response_first_text}",
                    file=sys.stderr,
                )
                self.turn += 1

            else:
                raise error


def load_json_file(config_file_path: str):
    with open(config_file_path, "r") as config_file:
        config_data = json.load(config_file)

    return config_data


@click.command()
@click.option(
    "--user-prompt",
    required=True,
    help="The user prompt to give to the agent",
)
@click.option(
    "--conversation-log-file-path",
    default="computer_use_demo/conversation_logs.json",
    help="Where to write the conversation log, in the container's filesystem",
)
@click.option(
    "--max-actions",
    type=int,
    default=100,
    help="The maximum number of loop iterations (each of which is roughly an action by the agent)",
)
@click.option(
    "--model",
    default="arn:aws:bedrock:us-west-2:302263051492:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    help="The model to run that will back the agent",
)
@click.option(
    "--system-prompt-suffix",
    default="",
    help="A suffix to add to the defaul system prompt",
)
@click.option(
    "--only-n-most-recent-images",
    default=10,
    help="how many images to include at most in a request to the agent",
)
@click.option(
    "--max_tokens",
    default=9048,
    help="Maximum number of tokens",
)
@click.option(
    "--thinking_budget",
    default=4096,
    help="Number of token (out of max_tokens) to allocate for reasoning",
)
@click.option(
    "--autologin-tool-calls",
    type=click.Path(),
    default="",
    help="Optional path to a file for autologin tool calls",
)
@click.option(
    "--login-url",
    type=str,
    default="",
    help="The URL to log in to, if using the autologin tool calls",
)
def main(
    user_prompt: str,
    conversation_log_file_path: str,
    max_actions: int,
    system_prompt_suffix: str,
    model: str,
    only_n_most_recent_images: int,
    max_tokens: int,
    thinking_budget: int,
    autologin_tool_calls: str,
    login_url,
):
    if "3-7" not in model and "3.7" not in model:
        raise ValueError(
            "This script is only valid for claude sonnet-3.7-cua, exiting..."
        )

    logged_login_tool_calls_sequence = []
    if autologin_tool_calls:
        with open(autologin_tool_calls, "r") as f:
            logged_login_tool_calls_sequence = json.loads(f.read())
        print(
            f"Will attempt automatic log-in at {login_url} from logged actions at {autologin_tool_calls}",
            file=sys.stderr,
        )
        assert (
            login_url != ""
        ), "You must provide a login URL if you are using autologin tool calls"

    initial_messages = [
        {
            "role": Sender.USER,
            "content": [BetaTextBlockParam(type="text", text=user_prompt)],
        }
    ]

    api_requests_accumulator = APIRequestsLogger(conversation_log_file_path)

    final_messages = asyncio.run(
        sampling_loop(
            system_prompt_suffix=system_prompt_suffix,
            model=model,
            provider=os.getenv("API_PROVIDER", "bedrock"),
            messages=initial_messages,
            output_callback=_output_callback,
            tool_output_callback=_tool_callback,
            api_response_callback=api_requests_accumulator.log_claude,
            api_key="",
            only_n_most_recent_images=only_n_most_recent_images,
            tool_version="computer_use_20250124",
            max_actions=max_actions,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            autologin_tool_calls_sequence=logged_login_tool_calls_sequence,
            login_url=login_url,
        )
    )
    with open(api_requests_accumulator.file_path_to_write_to, "a") as f:
        f.write(json.dumps(final_messages) + "\n")


main()
