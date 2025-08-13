# Copyright (c) Meta Platforms, Inc. and affiliates.
#!/usr/bin/env python
import json
import argparse
import logging
import sys
import os

from environment_setup import SETUP_ACTION_NAME_TO_FUNCTION
from environment_editors.base_environment_editor import BaseWebArenaEditor
from environment_editors.gitlab_editor import GitlabEditor
from environment_editors.reddit_editor import RedditEditor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def load_task_instantiation_from_file(task_file_path):
    """
    Load a task from a JSON file.
    """
    with open(task_file_path, "r") as f:
        return json.load(f)


def setup_environment_for_task(task: dict):
    """
    Run the setup function for a task in the appropriate environment.
    Updates the task parameters with any values returned by the setup function.
    """
    if task["sites"][0] == "reddit":
        editor = RedditEditor(task["env_ip"])
        task["parameters"]["reddit_domain"] = task["env_ip"]
    elif task["sites"][0] == "gitlab":
        editor = GitlabEditor(task["env_ip"])
        task["parameters"]["gitlab_domain"] = task["env_ip"]
    elif task["sites"][0] == "websearch":
        # Websearch does not require a specific editor, but we can still log it
        task["parameters"]["websearch_domain"] = task["env_ip"]
    else:
        raise ValueError(f"Unsupported site: {task['sites'][0]}")

    setup_fn_name = task["setup_fn"]
    logger.info(
        f"Running setup function {setup_fn_name} for task {task['task_id']} on environment {task['env_ip']}"
    )
    if setup_fn_name:
        setup_fn = SETUP_ACTION_NAME_TO_FUNCTION[setup_fn_name]
        possible_updates_to_config = setup_fn(editor, **task["parameters"])
        task["parameters"].update(possible_updates_to_config or {})

    # Instantiate task parameters after setup
    instantiate_task_based_on_parameters(task)

    return task


def instantiate_task_based_on_parameters(task_config):
    task_config["start_url"] = task_config["start_url_template"].format(
        **task_config["parameters"]
    )
    task_config["intent"] = task_config["user_instruction_template"].format(
        **task_config["parameters"]
    )
    for eval_field_name in ["eval", "prompt_injection_success_eval"]:
        if eval_field_name not in task_config:
            continue
        if (
            "reference_url" in task_config[eval_field_name]
            and task_config[eval_field_name]["reference_url"]
        ):
            updated_reference_url = task_config[eval_field_name][
                "reference_url"
            ].format(**task_config["parameters"])

            task_config[eval_field_name].update(
                {"reference_url": updated_reference_url}
            )

        if (
            "program_html" in task_config[eval_field_name]["eval_types"]
            and task_config[eval_field_name]["program_html"]
        ):
            for indx, program_html in enumerate(
                task_config[eval_field_name]["program_html"]
            ):

                if "url" in program_html:
                    task_config[eval_field_name]["program_html"][indx]["url"] = (
                        program_html["url"].format(**task_config["parameters"])
                    )
                if "locator" in program_html:
                    task_config[eval_field_name]["program_html"][indx]["locator"] = (
                        program_html["locator"].format(**task_config["parameters"])
                    )

                if "required_contents" in program_html:
                    for key, value_list in program_html["required_contents"].items():
                        task_config[eval_field_name]["program_html"][indx][
                            "required_contents"
                        ][key] = [
                            v.format(**task_config["parameters"]) for v in value_list
                        ]

        # Instantiate exfil_data fields if present
        if (
            "exfil_data" in task_config[eval_field_name]
            and task_config[eval_field_name]["exfil_data"]
        ):
            for exfil_index, exfil_entry in enumerate(
                task_config[eval_field_name]["exfil_data"]
            ):
                for key, value in exfil_entry.items():
                    if isinstance(value, str):
                        task_config[eval_field_name]["exfil_data"][exfil_index][key] = (
                            value.format(**task_config["parameters"])
                        )
                    elif isinstance(value, list):
                        task_config[eval_field_name]["exfil_data"][exfil_index][key] = [
                            v.format(**task_config["parameters"]) for v in value
                        ]
                    else:
                        raise ValueError(
                            f"Unsupported type for exfil_data value: {type(value)}"
                        )


def main():
    parser = argparse.ArgumentParser(
        description="Setup environment for a specific task"
    )
    parser.add_argument(
        "--task-config",
        type=str,
        required=True,
        help="JSON string containing the task configuration",
    )
    parser.add_argument(
        "--task-file-path",
        type=str,
        required=True,
        help="Path to write the updated task configuration or read it from if skip-setup is used",
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="Skip actual environment setup and load from existing file if available",
    )

    args = parser.parse_args()

    # Parse the task configuration
    task = json.loads(args.task_config)
    task_id = task["task_id"]

    if args.skip_setup:
        # Try to load task from existing file
        if os.path.exists(args.task_file_path):
            logger.info(
                f"Skipping environment setup. Loading task {task_id} from {args.task_file_path}."
            )
            updated_task = load_task_instantiation_from_file(args.task_file_path)
        else:
            logger.warning(
                f"Skip setup requested but file {args.task_file_path} not found. Doing nothing."
            )
            sys.exit(1)
    else:
        # Run the setup function
        updated_task = setup_environment_for_task(task)

        # Write the updated task to the output file
        with open(args.task_file_path, "w") as f:
            json.dump(updated_task, f)

    # Signal successful completion
    logger.info(f"Successfully set up environment for task {task['task_id']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
