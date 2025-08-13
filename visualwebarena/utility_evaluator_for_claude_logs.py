import os
import re
import subprocess
import time
import click
import json

from browser_env.actions import Action, ActionTypes, create_goto_url_action
from browser_env.envs import ScriptBrowserEnv
from browser_env.auto_login import get_site_comb_from_filepath

from evaluation_harness.evaluators import evaluator_router
import tempfile

import numpy as np
import pandas as pd
import tqdm


def read_logs(log_path):
    logged_task_eval_results = []
    with open(log_path, "r") as file:
        for line in file:
            logged_task_eval_results.append(json.loads(line))
    return logged_task_eval_results


def instantiate_urls(logged_task_eval_result, original_config):
    logged_task_eval_result.update({"eval": original_config["eval"]})
    if "reference_url" in logged_task_eval_result["eval"]:
        if logged_task_eval_result["env_ip"].endswith("8023"):
            updated_reference_url = logged_task_eval_result["eval"][
                "reference_url"
            ].replace("__GITLAB__", logged_task_eval_result["env_ip"])
        elif logged_task_eval_result["env_ip"].endswith("9999"):
            updated_reference_url = logged_task_eval_result["eval"][
                "reference_url"
            ].replace("__REDDIT__", logged_task_eval_result["env_ip"])

        logged_task_eval_result["eval"].update({"reference_url": updated_reference_url})

    if "program_html" in logged_task_eval_result["eval"]["eval_types"]:
        for indx, program_html in enumerate(original_config["eval"]["program_html"]):
            if "url" in program_html:
                if logged_task_eval_result["env_ip"].endswith("8023"):
                    logged_task_eval_result["eval"]["program_html"][indx]["url"] = (
                        program_html["url"]
                    ).replace("__GITLAB__", logged_task_eval_result["env_ip"])
                elif logged_task_eval_result["env_ip"].endswith("9999"):
                    logged_task_eval_result["eval"]["program_html"][indx]["url"] = (
                        program_html["url"]
                    ).replace("__REDDIT__", logged_task_eval_result["env_ip"])


def auto_login(orig_task_config):
    if orig_task_config["storage_state"]:
        cookie_file_name = os.path.basename(orig_task_config["storage_state"])
        comb = get_site_comb_from_filepath(cookie_file_name)
        temp_dir = tempfile.mkdtemp()
        # subprocess to renew the cookie
        subprocess.run(
            [
                "python",
                "browser_env/auto_login.py",
                "--auth_folder",
                temp_dir,
                "--site_list",
                *comb,
            ]
        )
        orig_task_config["storage_state"] = f"{temp_dir}/{cookie_file_name}"
        assert os.path.exists(orig_task_config["storage_state"])
        # update the config file

        return orig_task_config["storage_state"]


def retry_evaluator(
    max_num_retries,
    evaluator,
    logged_task_eval_result,
    mock_trajectory,
    task_config_json_path,
    env,
):
    for grade_attempt_i in range(max_num_retries):
        try:
            return evaluator(
                trajectory=mock_trajectory,
                config_file=task_config_json_path,
                page=env.page,
            )
        except Exception as e:
            if grade_attempt_i + 1 == max_num_retries:
                print(f"Grading attempts exhausted: {e}. Assigning score=0")
                score = 0.0
            print(
                f"Automatic grader failed for task: {logged_task_eval_result['task_id']}. Trying again: {grade_attempt_i}"
            )
            time.sleep(
                2
            )  # fail typically occurs due to timeout, put some sleep before retrying
    return 0.0


def handle_eval_failure_due_to_json_decoding(
    logged_task_eval_result, env, max_num_retries=3
):

    def fallback_raw_output():
        raw_answer = logged_task_eval_result["raw_output"]
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

        return mock_trajectory, logged_task_eval_result["start_url"]

    # Write the logged_task_eval_result to a temporary file
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".json", mode="w"
    ) as tmp_file:
        json.dump(logged_task_eval_result, tmp_file)
        task_config_json_path = tmp_file.name

    try:
        assistant_message = json.loads(logged_task_eval_result["raw_output"])
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
            f"Task id {logged_task_eval_result['task_id']} Failed to decode JSON from assistant message {str(e)}... Going to raw content fallback."
        )
        mock_trajectory, last_url = fallback_raw_output()
    except KeyError as e:
        print(
            f"Task id {logged_task_eval_result['task_id']} KeyError in decoding {str(e)}... Going to raw content fallback."
        )
        mock_trajectory, last_url = fallback_raw_output()

    obs, info = env.reset(options={"config_file": task_config_json_path})

    obs, _, terminated, _, info = env.step(create_goto_url_action(last_url))

    evaluator = evaluator_router(task_config_json_path)
    return retry_evaluator(
        max_num_retries,
        evaluator,
        logged_task_eval_result,
        mock_trajectory,
        task_config_json_path,
        env,
    )


def handle_eval_failure_due_to_missing_playwright(
    logged_task_eval_result, env, max_num_retries=3
):
    # Write the logged_task_eval_result to a temporary file
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".json", mode="w"
    ) as tmp_file:
        json.dump(logged_task_eval_result, tmp_file)
        task_config_json_path = tmp_file.name

    if (
        "raw_output" in logged_task_eval_result
        and "answer" in logged_task_eval_result["raw_output"]
    ):
        mock_trajectory = [
            Action(
                action_type=ActionTypes.STOP,
                answer=logged_task_eval_result["raw_output"]["answer"],
            )
        ]
    else:
        return 0.0

    if (
        "raw_output" in logged_task_eval_result
        and "last_url" in logged_task_eval_result["raw_output"]
    ):
        last_url = logged_task_eval_result["raw_output"]["last_url"]
    else:
        return 0.0

    obs, info = env.reset(options={"config_file": task_config_json_path})

    obs, _, terminated, _, info = env.step(create_goto_url_action(last_url))

    evaluator = evaluator_router(task_config_json_path)
    return retry_evaluator(
        max_num_retries,
        evaluator,
        logged_task_eval_result,
        mock_trajectory,
        task_config_json_path,
        env,
    )


@click.command()
@click.option("--log", type=click.Path(exists=True), help="Path to JSONL file log.")
def main(log):
    logged_task_eval_results = read_logs(log)
    orig_configs = pd.read_json(
        "config_files/wa/test_webarena.raw.json",
    )
    logged_task_eval_results = tqdm.tqdm(
        logged_task_eval_results, desc="Processing logs"
    )

    env = ScriptBrowserEnv(
        headless=True,
        slow_mo=200,
        observation_type="accessibility_tree",
        current_viewport_only=True,
        viewport_size={"width": 1280, "height": 1720},
    )

    for logged_task_eval_result in logged_task_eval_results:
        original_config = orig_configs[
            orig_configs["task_id"] == logged_task_eval_result["task_id"]
        ].iloc[0]
        instantiate_urls(logged_task_eval_result, original_config)

        if logged_task_eval_result["status"] == "eval_failure" and (
            logged_task_eval_result["error"]
            == "Attribute goto not supported with pseudo pages"
            or "reddit_get_post_url" in logged_task_eval_result["error"]
        ):
            storate_state_path = auto_login(original_config)
            if storate_state_path:
                logged_task_eval_result["storage_state"] = storate_state_path

            regraded_score = handle_eval_failure_due_to_missing_playwright(
                logged_task_eval_result, env
            )
            logged_task_eval_result["regraded_score"] = regraded_score
            logged_task_eval_result["regraded"] = True
        elif logged_task_eval_result["status"] == "eval_failure" and (
            logged_task_eval_result["error"] == "Failed to decode JSON from output"
        ):
            regraded_score = handle_eval_failure_due_to_json_decoding(
                logged_task_eval_result, env
            )
            logged_task_eval_result["regraded_score"] = regraded_score
            logged_task_eval_result["regraded"] = True
        else:
            logged_task_eval_result["regraded"] = False
            logged_task_eval_result["regraded_score"] = np.nan

    output_log_path = log.replace(
        ".jsonl", "_regraded_both_more_permissive_match_and_autologin.jsonl"
    )
    with open(output_log_path, "w") as output_file:
        for result in logged_task_eval_results:
            output_file.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
