# Copyright (c) Meta Platforms, Inc. and affiliates.
import os


yaml_config_base = """
short_model_name: "o1"
skip_docker_build: true 
max_actions: 20
system_objective_message_role: "{system_objective_message_role}"  
max_observations_to_keep: 3
scaffolding: "tool-calling"
use_defensive_system_prompt: False
experiment_group: "prompt-injections-goal-hijacking-{prompt_injection_type}-comment"
tasks: "task_configs/prompt_injections_goal_hijacking_{prompt_injection_type}_comment.json" 
"""


def main():
    prompt_injection_types = [
        "plain",
        "url",
    ]
    for prompt_injection_type in prompt_injection_types:
        for system_objective_message_role in ["system", "developer"]:
            config_for_this = yaml_config_base.format(
                prompt_injection_type=prompt_injection_type,
                system_objective_message_role=system_objective_message_role,
            )

            file_name = f"o1-tool-calling-{system_objective_message_role}-prompt-injection-{prompt_injection_type}-comment.yaml"

            with open(
                os.path.join("config", "experiment", file_name), "w"
            ) as config_file:
                config_file.write(config_for_this)


if __name__ == "__main__":
    main()
