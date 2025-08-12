#!/usr/bin/env python
import json
import argparse
import logging
import sys

from environment_cleanup import CLEANUP_ACTION_NAME_TO_FUNCTION
from environment_editors.base_environment_editor import BaseWebArenaEditor
from environment_editors.gitlab_editor import GitlabEditor
from environment_editors.reddit_editor import RedditEditor
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def cleanup_environment_for_task(task: dict):
    """
    Run the cleanup function for a task in the appropriate environment.
    """
    if task["sites"][0] == "reddit":
        editor = RedditEditor(task["env_ip"])
    elif task["sites"][0] == "gitlab":
        editor = GitlabEditor(task["env_ip"])
    else:
        print("Unsupported site type for cleanup:", task["sites"], file=sys.stderr)
        return False

    cleanup_fn_name = task["cleanup_fn"]
    logger.info(
        f"Running cleanup function {cleanup_fn_name} for task {task['task_id']} on environment {task['env_ip']}"
    )
    if cleanup_fn_name:
        cleanup_fn = CLEANUP_ACTION_NAME_TO_FUNCTION[cleanup_fn_name]
        cleanup_fn(editor, **task["parameters"])

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Cleanup environment for a specific task"
    )
    parser.add_argument(
        "--task-config",
        type=str,
        required=True,
        help="JSON string containing the task configuration",
    )

    args = parser.parse_args()

    try:
        # Parse the task configuration
        task = json.loads(args.task_config)

        # Run the cleanup function
        success = cleanup_environment_for_task(task)

        if success:
            # Signal successful completion
            logger.info(
                f"Successfully cleaned up environment for task {task['task_id']}"
            )
            sys.exit(0)
        else:
            logger.error(f"Failed to clean up environment for task {task['task_id']}")
            sys.exit(1)

    except Exception as e:
        logger.error(
            f"Error cleaning up environment: {str(e)}\n{traceback.format_exc()}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
