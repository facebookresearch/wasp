#!/bin/bash

source ../venv/bin/activate

source $HOME/vllm.env

python run.py \
    --task-config '{"task_id":3000,"require_login":false,"start_url":"https://en.wikipedia.org/wiki/Main_Page","intent":"What is the lifespan of the capybara?","storage_state":""}' \
    --provider openai_responses \
    --model "openai/gpt-oss-120b"