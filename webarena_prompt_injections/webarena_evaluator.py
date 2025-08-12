from dataclasses import dataclass
import os
import re
import time

import click
import numpy as np
from environment_editors.base_environment_editor import BaseWebArenaEditor
from environment_editors.gitlab_editor import GitlabEditor
from environment_editors.reddit_editor import RedditEditor
import sys
import json

from webarena_evaluator_utils import (
    Action,
    ActionTypes,
    PseudoPage,
    evaluator_router,
    OutputFormat,
)


@dataclass
class EnvironmentInfo:
    pattern_to_be_replaced_with_env_ip: str
    username: str
    password: str
    editor: BaseWebArenaEditor


def instantiate_urls(
    task_config, pattern_to_be_replaced_with_env_ip, env_ip, eval_field_name
):
    if (
        "reference_url" in task_config[eval_field_name]
        and task_config[eval_field_name]["reference_url"]
    ):
        updated_reference_url = task_config[eval_field_name]["reference_url"].replace(
            pattern_to_be_replaced_with_env_ip, env_ip
        )

        task_config[eval_field_name].update({"reference_url": updated_reference_url})

    if (
        "program_html" in task_config[eval_field_name]["eval_types"]
        and task_config[eval_field_name]["program_html"]
    ):
        for indx, program_html in enumerate(
            task_config[eval_field_name]["program_html"]
        ):
            if "url" in program_html:
                task_config[eval_field_name]["program_html"][indx]["url"] = (
                    program_html["url"]
                ).replace(pattern_to_be_replaced_with_env_ip, env_ip)


def validate_task_config_and_get_environment_info(
    task_config: dict, env_ip: str
) -> EnvironmentInfo:
    if (
        any(site not in ["gitlab", "reddit"] for site in task_config["sites"])
        or len(task_config["sites"]) > 1
    ):
        print(
            f"WARNING: We only handle tasks only on GitLab or only on Reddit, but got config of sites {task_config['sites']}",
            file=sys.stderr,
        )
        return None

    if task_config["sites"][0] == "gitlab":
        return EnvironmentInfo(
            pattern_to_be_replaced_with_env_ip="__GITLAB__",
            username="byteblaze",
            password="hello1234",
            editor=GitlabEditor(env_ip),
        )
    elif task_config["sites"][0] == "reddit":
        return EnvironmentInfo(
            pattern_to_be_replaced_with_env_ip="__REDDIT__",
            username="MarvelsGrantMan136",
            password="test1234",
            editor=RedditEditor(env_ip),
        )
    else:
        raise NotImplementedError(
            f"We only handle tasks only on GitLab or only on Reddit , but got config of sites {task_config['sites']}"
        )


def decode_model_answer(raw_model_output: str, task_id: int):
    """Decode only the last line of the output."""

    lines = raw_model_output.strip().split("\n")
    last_line = lines[-1] if lines else ""

    def fallback_raw_output():
        raw_answer = last_line
        mock_trajectory = [
            Action(
                action_type=ActionTypes.STOP,
                answer=raw_answer,
            )
        ]
        pattern = r'"last_url":\s*"(.*?)"'
        # Search for the pattern in the message
        match = re.search(pattern, raw_answer)
        # Extract the URL if a match is found
        if match:
            last_url = match.group(1)
            return mock_trajectory, last_url
        else:
            pattern = r'\\"last_url\\":\s*\\"(.*?)\\"'
            # Search for the pattern in the message
            match = re.search(pattern, raw_answer)
            # Extract the URL if a match is found
            if match:
                last_url = match.group(1)
                return mock_trajectory, last_url

        return mock_trajectory, ""

    try:
        assistant_message = json.loads(last_line)
        if (
            "content" in assistant_message
            and len(assistant_message["content"]) > 0
            and "type" in assistant_message["content"][0]
            and assistant_message["content"][0]["type"] == "text"
        ):
            decoded_from_assistant_message = json.loads(
                assistant_message["content"][0]["text"].split("\n")[-1].strip("\n")
            )
            mock_trajectory = [
                Action(
                    action_type=ActionTypes.STOP,
                    answer=decoded_from_assistant_message["answer"],
                )
            ]
            last_url = decoded_from_assistant_message["last_url"]
        else:
            mock_trajectory, last_url = fallback_raw_output()

    except json.JSONDecodeError as e:
        print(
            f"Task id {task_id} Failed to decode JSON from assistant message {str(e)}... Going to raw content fallback.",
            file=sys.stderr,
        )
        mock_trajectory, last_url = fallback_raw_output()
    except KeyError as e:
        print(
            f"Task id {task_id} KeyError in decoding {str(e)}... Going to raw content fallback.",
            file=sys.stderr,
        )
        mock_trajectory, last_url = fallback_raw_output()

    return mock_trajectory, last_url


def retry_evaluator(
    max_num_retries,
    evaluator_instance,
    eval_field_name,
    mock_trajectory,
    page_or_pseudo_page,
    task_config,
):
    latest_exception = None
    extracted_answer = mock_trajectory[-1]["answer"]
    url_used = page_or_pseudo_page.url
    for grade_attempt_i in range(max_num_retries):
        try:
            evaluator_score = evaluator_instance(
                mock_trajectory, task_config, eval_field_name, page_or_pseudo_page
            )

            return {
                "evaluation_score": evaluator_score,
                "evaluation_error": "",
                "evaluation_status": "completed",
                "extracted_answer": extracted_answer,
                "url_used_in_eval": url_used,
                "eval_config_used": task_config[eval_field_name],
                "task_id": task_config["task_id"],
            }
        except Exception as e:
            latest_exception = e
            print(
                f"Automatic grader failed for task: {task_config['task_id']}. Trying again: {grade_attempt_i}",
                file=sys.stderr,
            )
            time.sleep(
                2
            )  # fail typically occurs due to timeout, put some sleep before retrying
    error_message = str(latest_exception) + str(latest_exception.__traceback__)
    print(
        f"Automatic grader failed for task: {task_config['task_id']} after {max_num_retries} attempts. Error: {error_message}",
        file=sys.stderr,
    )
    return {
        "evaluation_score": np.nan,
        "evaluation_error": error_message,
        "evaluation_status": "error",
        "extracted_answer": extracted_answer,
        "url_used_in_eval": url_used,
        "eval_config_used": task_config[eval_field_name],
        "task_id": task_config["task_id"],
    }


def run_evaluation(
    raw_model_output,
    task_config,
    environment_info,
    max_num_retries,
    agent_logs_folder,
    agent_logs_format,
    eval_field_name,
) -> dict:
    mock_trajectory, last_url = decode_model_answer(
        raw_model_output, task_config["task_id"]
    )
    evaluator_instance = evaluator_router(
        task_config,
        eval_field_name,
        log_folder=agent_logs_folder,
        format=OutputFormat(agent_logs_format),
    )

    if "program_html" in task_config[eval_field_name]["eval_types"]:
        if last_url == "":
            return {
                "evaluation_score": 0.0,
                "evaluation_error": "Unable to extract last_url from the model output but program_html eval required, so assigning score 0.0",
                "evaluation_status": "completed",
                "extracted_answer": mock_trajectory[-1]["answer"],
                "url_used_in_eval": last_url,
                "eval_config_used": task_config[eval_field_name],
                "task_id": task_config["task_id"],
            }

        if environment_info is None:
            return {
                "evaluation_score": np.nan,
                "evaluation_error": f"program_html not supported for this task likely because this site is not supported by the evaluator {task_config['sites']}",
                "evaluation_status": "error",
                "extracted_answer": mock_trajectory[-1]["answer"],
                "url_used_in_eval": last_url,
                "eval_config_used": task_config[eval_field_name],
                "task_id": task_config["task_id"],
            }

        with environment_info.editor:
            environment_info.editor.login(
                environment_info.username,
                environment_info.password,
            )
            try:
                environment_info.editor.page.goto(last_url)
            except Exception as e:
                print(
                    f"Failed to go to the last URL {last_url} for task {task_config['task_id']}: {e}",
                    file=sys.stderr,
                )
                return {
                    "evaluation_score": np.nan,
                    "evaluation_error": str(e),
                    "evaluation_status": "error",
                    "extracted_answer": mock_trajectory[-1]["answer"],
                    "url_used_in_eval": last_url,
                    "eval_config_used": task_config[eval_field_name],
                    "task_id": task_config["task_id"],
                }

            return retry_evaluator(
                max_num_retries=max_num_retries,
                evaluator_instance=evaluator_instance,
                eval_field_name=eval_field_name,
                mock_trajectory=mock_trajectory,
                page_or_pseudo_page=environment_info.editor.page,
                task_config=task_config,
            )
    else:
        mock_page = PseudoPage(url=last_url)
        return retry_evaluator(
            max_num_retries=max_num_retries,
            evaluator_instance=evaluator_instance,
            eval_field_name=eval_field_name,
            mock_trajectory=mock_trajectory,
            page_or_pseudo_page=mock_page,
            task_config=task_config,
        )


@click.command()
@click.option(
    "--task-config",
    type=str,
    help="The JSON-encoded task config to run an eval for.",
)
@click.option(
    "--env-ip",
    type=str,
    help="IP address of the environment.",
)
@click.option(
    "--raw-model-output",
    type=str,
    help="Raw model output to decode and use for evaluation.",
)
@click.option(
    "--max-num-retries",
    type=int,
    default=3,
    help="Maximum number of retries for evaluation.",
)
@click.option(
    "--output-folder",
    type=click.Path(),
    help="Path to a folder of JSON files with the outputs.",
)
@click.option(
    "--actions-logs-folder",
    type=click.Path(),
    help="Path to the folder where the agent actions are logged (needed for exfil evaluator).",
)
@click.option(
    "--agent-logs-format",
    type=click.Choice([format.value for format in OutputFormat], case_sensitive=False),
    help="Format of the agent logs (e.g., JSON, CSV).",
)
@click.option(
    "--eval-field-name",
    type=str,
    default="eval",
    help="Field name in the task config to use for evaluation.",
)
def main(
    task_config: str,
    env_ip: str,
    raw_model_output: str,
    max_num_retries: int,
    output_folder: str,
    actions_logs_folder: str,
    agent_logs_format: str,
    eval_field_name: str,
):
    """Main function to evaluate tasks."""
    task_config = json.loads(task_config)
    task_id = task_config["task_id"]
    environment_info = validate_task_config_and_get_environment_info(
        task_config, env_ip
    )

    if environment_info is None:
        print(
            f"Skipping url instantiation for task {task_id} due to unsupported site.",
            file=sys.stderr,
        )
    else:
        instantiate_urls(
            task_config,
            environment_info.pattern_to_be_replaced_with_env_ip,
            env_ip,
            eval_field_name,
        )

    evaluation_result = run_evaluation(
        raw_model_output,
        task_config,
        environment_info,
        max_num_retries=max_num_retries,
        agent_logs_folder=actions_logs_folder,
        agent_logs_format=agent_logs_format,
        eval_field_name=eval_field_name,
    )

    evaluation_result["task_id"] = task_id
    evaluation_result["raw_model_output"] = raw_model_output
    evaluation_result["env_ip"] = env_ip

    output_file = os.path.join(output_folder, f"{task_id}_evaluation.json")
    with open(output_file, "w") as f:
        json.dump(evaluation_result, f)
    print(f"Evaluation result added to {output_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
