# Copyright (c) Meta Platforms, Inc. and affiliates.
import json
import sys
import click
from openai_api_agent import OpenAIAPIWebAgent, OpenAIResponsesAPIWebAgent
from anthropic_api_agent import AnthropicAPIWebAgent
from constants import SYSTEM_PROMPT, Provider


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
@click.option(
    "--enable-thinking",
    is_flag=True,
    default=False,
    help="Enable agent thinking process",
)
@click.option(
    "--thinking-budget-tokens",
    type=int,
    default=10000,
    help="The budget for thinking in Claude agents",
)
@click.option(
    "--enable-interleaved-thinking",
    is_flag=True,
    default=False,
    help="Enable interleaved thinking in agent responses",
)
@click.option(
    "--provider",
    type=click.Choice([member.value for member in Provider]),
    default=Provider.OPENAI_CHAT_COMPLETIONS,
    help="The LLM provider to use",
)
def main(
    task_config,
    model,
    trace_log_filepath,
    max_actions,
    max_observations_to_keep,
    system_objective_message_role,
    enable_thinking,
    thinking_budget_tokens,
    enable_interleaved_thinking,
    provider,
):
    task_config = json.loads(task_config)

    start_url = task_config["start_url"]
    user_objective = task_config["intent"]
    env_ip = task_config.get("env_ip", None)

    agent_creator_params = {
        "model": model,
        "filepath_to_trace_log": trace_log_filepath,
        "provider": Provider(provider),
        "system_prompt": SYSTEM_PROMPT,
    }

    if provider in [
        Provider.AZURE_CHAT_COMPLETIONS,
        Provider.OPENAI_CHAT_COMPLETIONS,
        Provider.OPENAI_CUSTOM_CHAT_COMPLETIONS,
    ]:
        agent_class = OpenAIAPIWebAgent
        if enable_thinking:
            raise ValueError(
                "Thinking is not supported for OpenAI API. Please use Anthropic API instead."
            )
        if enable_interleaved_thinking:
            raise ValueError(
                "Interleaved thinking is not supported for OpenAI API. Please use Anthropic API instead."
            )
        agent_creator_params.update(
            {
                "system_objective_message_role": system_objective_message_role,
            }
        )
    elif provider in [Provider.OPENAI_RESPONSES, Provider.OPENAI_CUSTOM_RESPONSES, Provider.AZURE_RESPONSES]:
        agent_class = OpenAIResponsesAPIWebAgent
        if enable_thinking:
            raise ValueError(
                "Thinking is not supported for OpenAI Responses API. Please use Anthropic API instead."
            )
        if enable_interleaved_thinking:
            raise ValueError(
                "Interleaved thinking is not supported for OpenAI Responses API. Please use Anthropic API instead."
            )
        agent_creator_params.update(
            {
                "system_objective_message_role": system_objective_message_role,
            }
        )
    elif provider in [Provider.ANTHROPIC, Provider.BEDROCK]:
        agent_class = AnthropicAPIWebAgent
        agent_creator_params.update(
            {
                "enable_thinking": enable_thinking,
                "thinking_budget_tokens": thinking_budget_tokens,
                "enable_interleaved_thinking": enable_interleaved_thinking,
            }
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    with agent_class(
        **agent_creator_params,
    ) as agent:
        if env_ip:
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
            user_objective=f"Start on {start_url} {user_objective}",
            max_actions=max_actions,
            max_observations_to_keep=max_observations_to_keep,
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
