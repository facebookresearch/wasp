# Copyright (c) Meta Platforms, Inc. and affiliates.
import json
import os
import sys
import click
from openai import AzureOpenAI, OpenAI
from browser_env import ScriptBrowserEnv
from browser_env.env_config import ACCOUNTS
from tool_calling_utils import (
    SYSTEM_PROMPT,
    WEB_TOOLS_DEFINITION,
    TOOL_NAME_TO_CREATE_ACTION_FUNCTION,
)


class GPTWebAgent:
    def __init__(self, model: str, filepath_to_trace_log: str):
        if "AZURE_API_ENDPOINT" in os.environ and "AZURE_API_KEY" in os.environ:
            client = AzureOpenAI(
                azure_endpoint=os.environ["AZURE_API_ENDPOINT"],
                api_key=os.environ["AZURE_API_KEY"],
                api_version=os.environ["AZURE_API_VERSION"],
            )
        elif "OPENAI_API_KEY" in os.environ:
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        else:
            raise ValueError("Missing OpenAI API key")
        self.client = client
        self.model = model
        self.tools_definitions = WEB_TOOLS_DEFINITION

        self.browser_env = ScriptBrowserEnv(
            headless=True,
            slow_mo=0,
            observation_type="accessibility_tree",
            current_viewport_only=False,
            viewport_size={
                "width": 1280,
                "height": 2048,
            },
            save_trace_enabled=False,
            sleep_after_execution=0.0,
            captioning_fn=None,
        )

        self.filepath_to_trace_log = filepath_to_trace_log

    def __enter__(
        self,
    ):
        self.browser_env.reset()
        self.trace_log_file = open(self.filepath_to_trace_log, "w")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.browser_env.close()
        self.trace_log_file.close()

    def _login_to_gitlab(self, env_ip: str):
        page = self.browser_env.page
        username = ACCOUNTS["gitlab"]["username"]
        password = ACCOUNTS["gitlab"]["password"]
        page.goto(f"{env_ip}/users/sign_in")
        page.get_by_test_id("username-field").click()
        page.get_by_test_id("username-field").fill(username)
        page.get_by_test_id("username-field").press("Tab")
        page.get_by_test_id("password-field").fill(password)
        page.get_by_test_id("sign-in-button").click()

    def _login_to_reddit(self, env_ip: str):
        page = self.browser_env.page
        username = ACCOUNTS["reddit"]["username"]
        password = ACCOUNTS["reddit"]["password"]
        page.goto(f"{env_ip}/login")
        page.get_by_label("Username").fill(username)
        page.get_by_label("Password").fill(password)
        page.get_by_role("button", name="Log in").click()

    def login(self, sites: list[str], env_ip: str):
        if "gitlab" in sites:
            self._login_to_gitlab(env_ip)

        if "reddit" in sites:
            self._login_to_reddit(env_ip)

    def _call_model(self, messages: list[dict]):
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tools_definitions,
        )
        print(
            f"Received model response. Used {completion.usage.prompt_tokens} prompt tokens and {completion.usage.completion_tokens} completion tokens",
            file=sys.stderr,
        )
        return _parse_response_to_json(completion.choices[0].message)

    def _execute_requested_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        # we will consistently return a list of dicitonaries in the message format
        # even though in non-error cases that list will be of length 1
        if len(tool_calls) > 1:
            return [
                _get_tool_message_with_id_and_content(
                    tool_call["id"],
                    "ERROR: Multiple tool calls provided. You MUST respond with ONLY one tool call!",
                )
                for tool_call in tool_calls
            ]

        if len(tool_calls) < 1:
            return []

        tool_call = tool_calls[0]

        tool_name = tool_call["function"]["name"]
        if tool_name not in TOOL_NAME_TO_CREATE_ACTION_FUNCTION:
            return [
                _get_tool_message_with_id_and_content(
                    tool_call["id"],
                    f"ERROR: {tool_name} is not a valid function! You must pick one of {','.join(TOOL_NAME_TO_CREATE_ACTION_FUNCTION.keys())}",
                )
            ]

        args = json.loads(tool_call["function"]["arguments"])

        if tool_name == "stop":
            return [{"role": "stop", "answer": args["answer"]}]

        create_action_function = TOOL_NAME_TO_CREATE_ACTION_FUNCTION[tool_name]
        try:
            action = create_action_function(**args)
        except TypeError as e:
            return [
                _get_tool_message_with_id_and_content(tool_call["id"], f"ERROR: {e}")
            ]

        browser_execution_result = self.browser_env.step(action)
        # the step function returns a tuple but we are only interested in the observation, which is in the first position
        # the Observation object is then keyed by modality, which is always text
        observation_text = browser_execution_result[0]["text"]

        formatted_tool_call_result = f"""OBSERVATION:
{observation_text}
URL: {self.browser_env.page.url}
"""

        return [
            _get_tool_message_with_id_and_content(
                tool_call["id"], formatted_tool_call_result
            )
        ]

    def _log_messages(self, messages):
        self.trace_log_file.write(json.dumps(messages) + "\n")

    def loop(
        self,
        start_url: str,
        user_objective: str,
        max_actions: int,
        max_observations_to_keep: int,
        system_objective_message_role: str = "system",
    ):
        messages = []
        print(
            f"Now using {system_objective_message_role} role for system message.",
            file=sys.stderr,
        )
        system_message = {
            "role": system_objective_message_role,
            "content": SYSTEM_PROMPT,
        }
        messages.append(system_message)

        user_intent_message = {
            "role": "user",
            "content": f"Start on {start_url} {user_objective}",
        }
        messages.append(user_intent_message)

        for action_number in range(max_actions):
            model_response_message = self._call_model(messages)

            print(
                f"Model [{self.model}] response {action_number} {model_response_message['content']}",
                file=sys.stderr,
            )

            result_of_execution = self._execute_requested_tool_calls(
                model_response_message["tool_calls"]
            )

            messages.append(model_response_message)

            if len(result_of_execution) < 1:
                print("Agent did not call any tools; exiting.", file=sys.stderr)
                break

            messages.extend(result_of_execution)

            self._log_messages(messages)

            if result_of_execution[0]["role"] == "stop":
                print(
                    f"Agent finished with stop action and answer {result_of_execution[0]['answer']}",
                    file=sys.stderr,
                )
                return result_of_execution[0]["answer"]

            _maybe_filter_tool_call_results(messages, max_observations_to_keep)


def _get_tool_message_with_id_and_content(id, content):
    return {
        "role": "tool",
        "tool_call_id": id,
        "content": content,
    }


def _maybe_filter_tool_call_results(
    messages: list[dict], max_observations_to_keep: int
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


def _parse_response_to_json(response_message):
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


@click.command()
@click.option(
    "--task-config",
    type=str,
    help="The JSON-encoded task config to run the agent for.",
)
@click.option("--model", type=str, default="gpt-4o", help="The model backing the agent")
@click.option(
    "--trace-log-filepath",
    type=str,
    default="/tmp/gpt_text_loop_agent_logs.jsonl",
    help="Where to store the trajectories",
)
@click.option(
    "--max_actions", type=int, default=20, help="The cap on actions by the agent"
)
@click.option(
    "--max_observations_to_keep",
    type=int,
    default=3,
    help="The maximum number of past tool call results to keep",
)
@click.option(
    "--system_objective_message_role",
    type=click.Choice(["system", "developer"]),
    default="system",
    help="The role for the system objective message",
)
def main(
    task_config,
    model,
    trace_log_filepath,
    max_actions,
    max_observations_to_keep,
    system_objective_message_role,
):
    task_config = json.loads(task_config)

    start_url = task_config["start_url"]
    user_objective = task_config["intent"]
    env_ip = task_config["env_ip"]

    with GPTWebAgent(
        model,
        trace_log_filepath,
    ) as agent:
        print(
            f"Setting up tool-calling agent by logging into {task_config['sites']} on {env_ip}",
            file=sys.stderr,
        )
        agent.login(task_config["sites"], env_ip)

        print(
            f"Starting tool-calling agent with intent: {user_objective} on {start_url}",
            file=sys.stderr,
        )
        answer = agent.loop(
            start_url=start_url,
            user_objective=user_objective,
            max_actions=max_actions,
            max_observations_to_keep=max_observations_to_keep,
            system_objective_message_role=system_objective_message_role,
        )
        print(
            json.dumps(
                {
                    "answer": answer,
                    "last_url": agent.browser_env.page.url,
                }
            )
        )


if __name__ == "__main__":
    main()
