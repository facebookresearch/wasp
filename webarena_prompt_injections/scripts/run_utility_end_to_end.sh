#!/bin/bash
# Copyright (c) Meta Platforms, Inc. and affiliates.
# Prerequisite 1: python virtual environment and built Docker container
# Prerequisite 2: set the required authentication environment variables (AZURE_API_ENDPOINT and AZURE_API_KEY for GPT/WebArena and AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN for Claude)

set -e

export OUTPUT_DIR=${1:-/tmp/computer-use-agent-utility-logs/}
export MODEL=${2:-gpt-4o}
export SYSTEM_PROMPT=${3:-configs/system_prompts/wa_p_som_cot_id_actree_3s.json}
export CONFIG_PATH=${4:-configs/utility_config.raw.json}
export OUTPUT_FORMAT=${5:-webarena}

if [[ "${OUTPUT_DIR}" != */ ]]; then
    OUTPUT_DIR="${OUTPUT_DIR}/"
fi

if [ -d "$OUTPUT_DIR" ]; then
  echo "Deleting existing OUTPUT_DIR=${OUTPUT_DIR}"
  rm -rf "$OUTPUT_DIR"
fi

echo "Creating the new OUTPUT_DIR=${OUTPUT_DIR}"
mkdir "$OUTPUT_DIR"

echo "OUTPUT_DIR: $OUTPUT_DIR"
echo "CONFIG_PATH: $CONFIG_PATH"
echo "GITLAB_DOMAIN: $GITLAB"
echo "REDDIT_DOMAIN: $REDDIT"
echo "Model: $MODEL"
echo "SYSTEM_PROMPT: $SYSTEM_PROMPT"
echo "OUTPUT_FORMAT: $OUTPUT_FORMAT"

##### STEP 1: Instantiate webarena tasks and prepare environment ######
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
echo "SCRIPT_DIR: $SCRIPT_DIR"
cd $SCRIPT_DIR/..
cp $CONFIG_PATH "${OUTPUT_DIR}utility_config.json"
echo "step 1 | preparing environments and tasks for utility evaluation..."
source venv/bin/activate
python webarena_evaluator_setup.py --config $CONFIG_PATH \
                          --gitlab-domain $GITLAB \
                          --reddit-domain $REDDIT \
                          --model $MODEL \
                          --system_prompt $SYSTEM_PROMPT \
                          --output-dir $OUTPUT_DIR \
                          --output-format $OUTPUT_FORMAT
deactivate
##### -----------


##### STEP 2: Run agents on tasks ######
echo "SCRIPT_DIR: $SCRIPT_DIR"
cd $SCRIPT_DIR/../../visualwebarena/
source venv/bin/activate
chmod -R 777 $OUTPUT_DIR
AGENT_RUN_SCRIPT="${OUTPUT_DIR}run_agent.sh"
echo "step 2 | Executing agent script at $AGENT_RUN_SCRIPT"
bash "$AGENT_RUN_SCRIPT"
deactivate
##### -----------


##### STEP 3: Run evaluations ######
echo "SCRIPT_DIR: $SCRIPT_DIR"
cd $SCRIPT_DIR/..
LOG_DIR="${OUTPUT_DIR}agent_logs/"
TASK_DIR="${OUTPUT_DIR}webarena_utility_tasks/"
ATTACKER_TASK_DIR="${OUTPUT_DIR}webarena_tasks_attacker/"
echo "step 3 | OUTPUT_DIR: $OUTPUT_DIR"
echo "step 3 | OUTPUT_FORMAT: $OUTPUT_FORMAT"
cd ../visualwebarena/
source venv/bin/activate
bash prepare.sh
# evaluate user task performance
python evaluator_final_step.py --log-folder $LOG_DIR --task-folder $TASK_DIR --format $OUTPUT_FORMAT
echo "Done evaluating utility evaluation! Above score is a generic utility performance on the given environments."
deactivate
##### -----------


##### STEP 4: Cleanup environment ######
echo "SCRIPT_DIR: $SCRIPT_DIR"
cd $SCRIPT_DIR/..
INSTANTIATED_CONFIG="${OUTPUT_DIR}instantiated_webarena_utility_config.json"
echo "step 4 | OUTPUT_DIR: $OUTPUT_DIR"
echo "step 4 | INSTANTIATED_CONFIG: $INSTANTIATED_CONFIG"
source venv/bin/activate
python environment_cleanup.py --prompt-injection-config-path "$INSTANTIATED_CONFIG" --gitlab-domain $GITLAB --reddit-domain $REDDIT
deactivate
##### -----------