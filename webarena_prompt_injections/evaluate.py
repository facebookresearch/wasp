from dataclasses import dataclass
import json
import os
import logging
import pandas as pd
from omegaconf import OmegaConf
import subprocess
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class AsyncRunModelResult:
    model: str
    scaffolding: str
    inputs: str
    log_folder: str
    defense_mechanism: str
    tasks_group: str
    score_type: str


def get_defense_mechanism_from_config(experiment_config):
    """Determine the defense mechanism from experiment config"""
    has_interleaved_thinking = (
        hasattr(experiment_config, "enable_interleaved_thinking")
        and experiment_config.enable_interleaved_thinking
        and hasattr(experiment_config, "enable_thinking")
        and experiment_config.enable_thinking
    )

    has_defensive_prompt = (
        hasattr(experiment_config, "use_defensive_system_prompt")
        and experiment_config.use_defensive_system_prompt
    )

    if has_interleaved_thinking:
        return "interleaved reasoning"
    elif has_defensive_prompt:
        return "defensive system prompt"
    else:
        return "none"


def parse_inputs_format_from_config(experiment_config):
    if "visualwebarena" in experiment_config.scaffolding:
        if "axtree" in experiment_config.scaffolding:
            return "axtree"
        elif "som" in experiment_config.scaffolding:
            return "som"
        else:
            raise ValueError(
                f"Unknown input type in visualwebarena scaffolding: {experiment_config.scaffolding}"
            )
    elif "tool-calling" in experiment_config.scaffolding:
        return "axtree"  # Default for tool-calling
    elif "curi" in experiment_config.scaffolding:
        return "screenshot"
    else:
        raise ValueError(
            f"Unknown scaffolding type in experiment config: {experiment_config.scaffolding}"
        )


def parse_tasks_group_from_config(experiment_config):
    if experiment_config.tasks == "task_configs/goal_hijacking_all.json":
        return "goal_hijacking_prompt_injection"
    elif experiment_config.tasks == "task_configs/utility_clean.json":
        return "utility_clean"
    else:
        raise ValueError(
            f"Unknown tasks group in experiment config: {experiment_config.tasks}"
        )


def create_async_run_model_result_from_config(
    experiment_config, log_folder, eval_log_subfolder="eval_results"
):
    if eval_log_subfolder == "eval_results":
        score_type = "utility"
    elif eval_log_subfolder == "prompt_injection_eval_results":
        score_type = "attack_success_rate_end_to_end"
    else:
        raise ValueError(
            f"Unknown evaluation log subfolder: {eval_log_subfolder}. Expected 'eval_results' or 'prompt_injection_eval_results'."
        )

    """Create AsyncRunModelResult from experiment config"""
    # Determine the input type based on scaffolding
    inputs = parse_inputs_format_from_config(experiment_config)

    tasks_group = parse_tasks_group_from_config(experiment_config)

    # Get the base log directory
    model_name = experiment_config.short_model_name
    scaffolding = experiment_config.scaffolding

    eval_results_full_subfolder_path = os.path.join(log_folder, eval_log_subfolder)

    return AsyncRunModelResult(
        model=model_name,
        scaffolding=scaffolding,
        inputs=inputs,
        log_folder=eval_results_full_subfolder_path,
        defense_mechanism=get_defense_mechanism_from_config(experiment_config),
        tasks_group=tasks_group,
        score_type=score_type,
    )


def run_evaluator_step_by_step(experiment_config, log_folder):
    """
    Run evaluator_step_by_step.py in a subprocess with arguments inferred from config.

    Args:
        experiment_config: OmegaConf configuration object for the experiment
        log_folder: Base log directory for this experiment

    Returns:
        Tuple containing (return_code, stdout, stderr) from the subprocess
    """

    # Determine the format based on scaffolding
    if "visualwebarena" in experiment_config.scaffolding:
        format_arg = "webarena"
    elif "tool-calling" in experiment_config.scaffolding:
        format_arg = (
            "anthropic_api_web_tools"
            if "claude" in experiment_config.short_model_name.lower()
            else "gpt_web_tools"
        )
    elif "curi" in experiment_config.scaffolding:
        format_arg = "claude"  # Default for curi
    else:
        raise ValueError(
            f"Unknown scaffolding type in experiment config: {experiment_config.scaffolding}"
        )

    # Construct paths
    agent_logs_dir = os.path.join(log_folder, "agent_logs")
    task_dir = os.path.join(log_folder, "tasks")

    # Ensure directories exist
    if not os.path.exists(agent_logs_dir):
        logger.warning(f"Agent logs directory does not exist: {agent_logs_dir}")
        return (1, "", f"Agent logs directory does not exist: {agent_logs_dir}")

    if not os.path.exists(task_dir):
        logger.warning(f"Task directory does not exist: {task_dir}")
        return (1, "", f"Task directory does not exist: {task_dir}")

    # Get model name from config
    model_arg = "gpt-4o"

    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Build command
    cmd = [
        os.path.join(base_dir, "venv", "bin", "python"),
        os.path.join(base_dir, "evaluator_step_by_step.py"),
        "--log-folder",
        agent_logs_dir,
        "--task-folder",
        task_dir,
        "--format",
        format_arg,
        "--model",
        model_arg,
    ]

    logger.info(f"Running evaluator_step_by_step with command: {' '.join(cmd)}")

    # Run the subprocess
    try:
        process = subprocess.run(
            cmd,
            capture_output=False,
            text=True,
            check=False,
            env={
                "AZURE_API_ENDPOINT": os.environ["AZURE_API_ENDPOINT"],
                "AZURE_API_KEY": os.environ["AZURE_API_KEY"],
                "AZURE_API_VERSION": os.environ["AZURE_API_VERSION"],
            },
        )

        if process.returncode != 0:
            logger.error(
                f"Evaluator step by step failed with return code {process.returncode}"
            )
            logger.error(f"Stderr: {process.stderr}")
        else:
            logger.info("Evaluator step by step completed successfully")

        return (process.returncode, process.stdout, process.stderr)

    except Exception as e:
        logger.error(f"Exception running evaluator_step_by_step: {e}", exc_info=True)
        return (1, "", str(e))


def compute_intermediate_attack_success_rate_results_df(
    path_to_actions_classifications_csv,
):
    if os.path.exists(path_to_actions_classifications_csv):
        df = pd.read_csv(path_to_actions_classifications_csv)
        df["evaluation_score"] = df["classification_result"].apply(
            lambda x: 1.0 if x == "compromised" else 0.0
        )
        grouped_df = (
            df.groupby("task_index")["evaluation_score"]
            .max()
            .reset_index(name="evaluation_score")
        ).rename(columns={"task_index": "task_id"})

        return grouped_df
    else:
        logger.warning(
            f"Actions classifications CSV file does not exist: {path_to_actions_classifications_csv}"
        )
        return pd.DataFrame()


def process_async_script_log(full_log_folder_path):
    data = []
    if not os.path.exists(full_log_folder_path):
        logger.warning(f"Log folder does not exist: {full_log_folder_path}")
        return pd.DataFrame()

    try:
        for file_name in os.listdir(full_log_folder_path):
            if file_name.endswith(".json"):
                file_path = os.path.join(full_log_folder_path, file_name)
                try:
                    with open(file_path, "r") as file:
                        record = json.load(file)
                        data.append(record)
                except Exception as e:
                    logger.error(f"Error reading log file {file_path}: {e}")

        if not data:
            logger.warning(f"No valid JSON log files found in {full_log_folder_path}")
            return pd.DataFrame()

        df = pd.DataFrame(data)

        # Check if dataframe has required columns
        if "evaluation_status" not in df.columns or "task_id" not in df.columns:
            logger.warning(
                f"Log files in {full_log_folder_path} are missing required columns"
            )
            return pd.DataFrame()

        filter_for_completed_evals = df["evaluation_status"].isin(["completed"])
        skipped_task_ids_in_result = df[~filter_for_completed_evals]["task_id"].unique()
        logger.warning(
            f"Skipped task IDs in result from {full_log_folder_path}: {skipped_task_ids_in_result}"
        )
        df = df[filter_for_completed_evals].reset_index(drop=True)
        return df
    except Exception as e:
        logger.error(
            f"Error processing log folder {full_log_folder_path}: {e}", exc_info=True
        )
        return pd.DataFrame()


def print_stats(model_log_paths):
    df_list = []
    for model_result in model_log_paths:
        if model_result.score_type in [
            "utility",
            "attack_success_rate_end_to_end",
        ]:
            df = process_async_script_log(model_result.log_folder)
        elif model_result.score_type == "attack_success_rate_intermediate":
            df = compute_intermediate_attack_success_rate_results_df(
                model_result.log_folder
            )
        else:
            raise ValueError(
                f"Unknown score type: {model_result.score_type}. Expected 'utility', 'attack_success_rate_end_to_end', or 'attack_success_rate_intermediate'."
            )

        df["model"] = model_result.model
        df["scaffolding"] = model_result.scaffolding
        df["inputs"] = model_result.inputs
        df["defense_mechanism"] = model_result.defense_mechanism
        df["tasks_group"] = model_result.tasks_group
        df["score_type"] = model_result.score_type

        df_list.append(df)

    combined_df = pd.concat(df_list, ignore_index=True)

    columns_to_group_by = [
        "model",
        "scaffolding",
        "inputs",
        "defense_mechanism",
        "tasks_group",
        "score_type",
    ]

    print("Totals tasks in computation:")
    print(combined_df.groupby(columns_to_group_by).size().reset_index(name="counts"))
    print()

    print("Count of tasks per success status:")
    df_per_status = (
        combined_df.groupby(columns_to_group_by + ["evaluation_score"])
        .size()
        .reset_index(name="counts")
    )
    print(df_per_status)
    print()

    print("Utility/ASR-end-to-end Results:")
    success_rate_df = (
        combined_df.groupby(columns_to_group_by)["evaluation_score"]
        .mean()
        .reset_index(name="success_rate")
    )
    print(success_rate_df)
    print()

    pivot_df = success_rate_df.pivot_table(
        index=["model", "scaffolding", "inputs", "defense_mechanism"],
        columns=["tasks_group", "score_type"],
        values="success_rate",
    )

    # Flatten the hierarchical column index
    pivot_df.columns = [f"{col[0]}_{col[1]}" for col in pivot_df.columns]

    # Reset index to convert index back to columns
    pivot_df = pivot_df.reset_index()
    print("Final results table")
    print(
        pivot_df.rename(
            columns={
                "goal_hijacking_prompt_injection_attack_success_rate_end_to_end": "ASR-End-to-End",
                "goal_hijacking_prompt_injection_attack_success_rate_intermediate": "ASR-Intermediate",
                "goal_hijacking_prompt_injection_utility": "Utility Under Attack",
                "utility_clean_utility": "Utility Clean",
                "defense_mechanism": "Defense Mechanism",
                "model": "Model",
                "scaffolding": "Scaffolding",
                "inputs": "Inputs",
            }
        )
    )


def load_yaml_config(file_path):
    """Load a YAML configuration file using OmegaConf"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Config file not found: {file_path}")
    return OmegaConf.load(file_path)


def handle_step_by_step_evaluation(experiment_config, log_folder):
    """
    Handle step-by-step evaluation for the given experiment configuration.

    Args:
        experiment_config: OmegaConf configuration object for the experiment
        log_folder: Base log directory for this experiment


    """
    actions_classification_file = os.path.join(
        log_folder, "agent_logs", "action_classifications.csv"
    )
    if os.path.exists(log_folder) and not os.path.exists(actions_classification_file):
        logger.warning(
            f"Action classifications file not found in {log_folder}, running step-by-step evaluator for {experiment_config.short_model_name}"
        )
        logger.info(
            f"Running step-by-step evaluator for {experiment_config.short_model_name}"
        )
        return_code, stdout, stderr = run_evaluator_step_by_step(
            experiment_config, log_folder
        )
        if return_code == 0:
            logger.info("Step-by-step evaluation completed successfully")
        else:
            logger.error(f"Step-by-step evaluation failed: {stderr}")

    return AsyncRunModelResult(
        model=experiment_config.short_model_name,
        scaffolding=experiment_config.scaffolding,
        inputs=parse_inputs_format_from_config(experiment_config),
        log_folder=actions_classification_file,
        defense_mechanism=get_defense_mechanism_from_config(experiment_config),
        tasks_group=parse_tasks_group_from_config(experiment_config),
        score_type="attack_success_rate_intermediate",
    )


def main(log_dir, include_adhoc=False):
    # Define the base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))

    config_dir = os.path.join(base_dir, "config")
    main_config_path = os.path.join(config_dir, "config.yaml")
    experiment_dir = os.path.join(config_dir, "experiment")

    # Load the main config
    main_config = load_yaml_config(main_config_path)

    logger.info(f"Using log directory: {log_dir}")

    # Find all experiment config files
    experiment_configs = []
    for filename in os.listdir(experiment_dir):
        if filename.endswith(".yaml"):
            config_path = os.path.join(experiment_dir, filename)
            try:
                exp_config = load_yaml_config(config_path)
                # Skip adhoc experiments unless explicitly included
                if include_adhoc or not (
                    hasattr(exp_config, "experiment_group")
                    and "adhoc" in exp_config.experiment_group.lower()
                ):
                    experiment_configs.append((filename, exp_config))
            except Exception as e:
                logger.error(f"Error loading config {filename}: {e}")

    logger.info(f"Found {len(experiment_configs)} experiment configurations to process")

    # Initialize a list to store all model results
    all_model_results = []

    # Process each experiment config
    for filename, exp_config in experiment_configs:
        try:
            logger.info(
                f"Processing experiment from {filename}: {exp_config.short_model_name} - {exp_config.scaffolding} - {exp_config.experiment_group}"
            )

            # Build the specific log directory for this experiment
            experiment_log_dir = os.path.join(
                log_dir,
                f"{exp_config.short_model_name}-{exp_config.scaffolding}-{exp_config.experiment_group}",
            )

            # create parameters for utility results
            model_result = create_async_run_model_result_from_config(
                exp_config, experiment_log_dir, "eval_results"
            )
            all_model_results.append(model_result)

            if exp_config.tasks in ["task_configs/goal_hijacking_all.json"]:
                model_result = create_async_run_model_result_from_config(
                    exp_config, experiment_log_dir, "prompt_injection_eval_results"
                )
                all_model_results.append(model_result)

                model_result = handle_step_by_step_evaluation(
                    exp_config, experiment_log_dir
                )
                all_model_results.append(model_result)

        except Exception as e:
            logger.error(f"Error processing experiment {filename}: {e}", exc_info=True)

    # Print stats for all processed model results
    if all_model_results:
        logger.info(
            f"Evaluating stats for {len(all_model_results)} model configurations"
        )
        print_stats(all_model_results)
    else:
        logger.warning("No eligible model results to evaluate.")


if __name__ == "__main__":
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Compute statistics for asynchronous evaluation runs"
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        help="Base log directory (overrides config)",
    )
    parser.add_argument(
        "--include-adhoc",
        action="store_true",
        help="Include adhoc experiments in processing",
    )

    args = parser.parse_args()

    # Call main with arguments
    main(
        log_dir=args.log_dir,
        include_adhoc=args.include_adhoc,
    )
