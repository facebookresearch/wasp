import re
import subprocess
import json
import tempfile
import os
import time
from browser_env import ActionTypes, ScriptBrowserEnv, Action
from browser_env.auto_login import get_site_comb_from_filepath
import click

from evaluation_harness.evaluators import evaluator_router
from tool_calling_agent import GPTWebAgent


def parse_task_id_from_log_line(log_line):
    pattern = r"test_id\s*=\s*(\d+).*?passed\s*=\s*([\d.]+)"

    # Search for the pattern in the text
    match = re.search(pattern, log_line)
    # Extract and print the task ID if a match is found
    if match:
        task_id = match.group(1)
        score = match.group(2)

        return {int(task_id): float(score)}
    return None


def get_completed_tasks(log_file_path):
    completed_tasks = {}
    if  os.path.exists(log_file_path):
        with open(log_file_path, "r") as log_file:
            for line in log_file:
                task_info = parse_task_id_from_log_line(line)
                if task_info:
                    completed_tasks.update(task_info)
    return completed_tasks


def parse_config_and_autologin(webarena_config_path):
    with open(webarena_config_path) as f:
        _c = json.load(f)
        start_url = _c["start_url"]
        user_objective = _c["intent"]
        task_id = _c["task_id"]

        if "gitlab" not in _c["sites"] and "reddit" not in _c["sites"]:
            raise Exception("Purposefully skipping sites: " + str(_c["sites"]))

        # try automatically login, ignore if error occurs since agent has credentials in the system_prompt
        if _c["storage_state"]:
            try:
                cookie_file_name = os.path.basename(_c["storage_state"])
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
                _c["storage_state"] = f"{temp_dir}/{cookie_file_name}"
                assert os.path.exists(_c["storage_state"])
                # update the config file
                config_file = f"{temp_dir}/{os.path.basename(webarena_config_path)}"
                with open(config_file, "w") as f:
                    json.dump(_c, f)
            except Exception as e:
                print(f"Failed to automatically log in: {e}")
                print(
                    "Ignore this failure since agent has credentials in the system_prompt"
                )
    return start_url, user_objective, task_id


def evaluate(task_config_json_path, log_file, agent, agent_answer, max_num_retries=3):
    mock_trajectory = []
    if agent_answer:
        mock_trajectory = [Action(action_type=ActionTypes.STOP, answer=agent_answer)]
    evaluator = evaluator_router(
        task_config_json_path,
    )

    for grade_attempt_i in range(max_num_retries):
        try:
            score = evaluator(
                trajectory=mock_trajectory,
                config_file=task_config_json_path,
                page=agent.browser_env.page,
            )
            break
        except Exception as e:
            if grade_attempt_i + 1 == max_num_retries:
                print(f"Grading attempts exhausted: {e}. Assigning score=0")
                score = 0.0
            # print(
            #     f"Automatic grader failed for json_file: {task_config_json}. Trying again: {grade_attempt_i}"
            # )
            time.sleep(
                2
            )  # fail typically occurs due to timeout, put some sleep before retrying

    with open(task_config_json_path, "r", encoding="utf-8") as task_file:
        task_json = json.load(task_file)
        log_message = f"test_id = {task_json['task_id']} | start_url = {task_json['start_url']} | passed = {score}"
        print(log_message)
        log_file.write(log_message + "\n")
        log_file.flush()
    return score


@click.command()
@click.option(
    "--task-folder",
    type=str,
    help="path to the folder containing jsons describing the task",
)
@click.option(
    "--specific-task-id-override", type=int, help="only run this task", default=-1
)
@click.option("--model", type=str, default="gpt-4o", help="The model backing the agent")
@click.option(
    "--log-folder",
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
    task_folder,
    specific_task_id_override,
    model,
    log_folder,
    max_actions,
    max_observations_to_keep,
    system_objective_message_role,
):

    total_scores = 0.0
    cnt_tasks = 0.0

    log_filepath = os.path.join(log_folder, "eval_logs.txt")
    completed_tasks = get_completed_tasks(log_filepath)
    print("Completed tasks: ", completed_tasks)

    trace_logs_file_path = os.path.join(log_folder, "agent_logs")
    os.makedirs(trace_logs_file_path, exist_ok=True)

    for task_config_json in sorted(os.listdir(task_folder)):
        if (
            specific_task_id_override > -1
            and str(specific_task_id_override) != task_config_json.split(".")[0]
        ):
            print(
                f"Skipping task {task_config_json} because it does not match the specific task ID override."
            )
            continue
        try:
            task_config_json_path = os.path.join(task_folder, task_config_json)

            start_url, user_objective, task_id = parse_config_and_autologin(
                task_config_json_path
            )

            if task_id in completed_tasks:
                print(
                    f"Skipping task {task_id} because it is already done with score {completed_tasks[task_id]}. Check the log file at {log_filepath}."
                )
                score = completed_tasks[task_id]
                total_scores += score
                cnt_tasks += 1
                continue

            print(f"Running task {task_id} with config: {task_config_json_path}")
            with open(log_filepath, "a") as log_file:
                task_config_name = task_config_json.split(".")[0]

                trace_log_filepath = os.path.join(
                    trace_logs_file_path,
                    f"text_loop_agent_logs_{task_config_name}.jsonl",
                )
                with GPTWebAgent(
                    model,
                    trace_log_filepath,
                ) as agent:
                    agent_answer = agent.loop(
                        start_url=start_url,
                        user_objective=user_objective,
                        max_actions=max_actions,
                        max_observations_to_keep=max_observations_to_keep,
                        system_objective_message_role=system_objective_message_role,
                    )
                    score = evaluate(
                        task_config_json_path, log_file, agent, agent_answer
                    )
                    total_scores += score
                    cnt_tasks += 1

            time.sleep(1)

        except Exception as e:
            print(f"[Unhandled Error] {repr(e)}]")
            print
            import traceback

            # write to error file
            with open(os.path.join(log_folder, "error.txt"), "a") as f:
                f.write(f"[Config file]: {task_config_json_path}\n")
                f.write(f"[Unhandled Error] {repr(e)}\n")
                f.write(traceback.format_exc())  # write stack trace to file

    with open(log_filepath, "a") as log_file:
        log_message = "\nTotal scores: {score} / out of: {total}".format(
            score=total_scores, total=cnt_tasks
        )
        print(log_message)
        log_file.write(log_message + "\n")
        log_file.flush()


if __name__ == "__main__":
    main()
