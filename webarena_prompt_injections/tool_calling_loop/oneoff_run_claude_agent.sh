#!/bin/bash

source ../venv/bin/activate

source $HOME/bedrock.env

python run.py \
    --task-config '{"task_id":3000,"require_login":false,"start_url":"https://en.wikipedia.org/wiki/Main_Page","intent":"What is the lifespan of the capybara?","storage_state":""}' \
    --provider bedrock \
    --model "your_claude_deployment_model_name_here" \
    --enable-thinking \
    --enable-interleaved-thinking