# WASP: Benchmarking Web Agent Security Against Prompt Injection Attacks
[Ivan Evtimov](https://ivanevtimov.eu/),
[Arman Zharmagambetov](https://arman-z.github.io),
[Aaron Grattafiori](https://scholar.google.com/citations?user=j8PDwLwAAAAJ),
[Chuan Guo](https://sites.google.com/view/chuanguo),
[Kamalika Chaudhuri](https://cseweb.ucsd.edu/~kamalika)


This repo is an official implementation of the **WASP** ([arxiv:xxxx.xxxxx](https://arxiv.org/abs/xxxx.xxxxx)). 

Autonomous web navigation agents hold great potential for unlocking human productivity by automating mundane tasks on the internet. However, these agents can also be taken advantage of as new attack vectors for adversaries when deployed without proper mitigation. One emerging threat &mdash; prompt injection attacks, where the adversary embeds malicious instructions in the web environment that divert the agent to instead perform tasks for the adversary. To measure the extent of this risk, we construct this new benchmark that simulates real world attacks in a highly realistic, end-to-end executable web environment, without exposing the agent to real harm. 

Who did we develop this benchmark for?
- Developers of autonomous web navigation agents, broadly defined: engineers, researchers, and startups who want to evaluate their agentic systems against prompt injection attacks.
- Red-teamers and security researchers who want to test novel prompt injection attack mechanisms designed for such agents.


Please 🌟star🌟 this repo and cite our paper 📜 if you like (and/or use) our work, thank you!


## Installation

What our set up does not handle (you need to do this yourself before beginning setup):
* Install docker (required for the Claude Computer Use only)
* Install python 3.10 (required by the `visualwebarena` codebase's dependencies). It needs to be available as a `python3.10` command
* `playwright` installations often require system dependencies to be installed after running `playwright install`. We run this command in our script but check the stdout in case it is asking you to manually finish the dependency setup

We provide a setup script to install all required packages:   
```bash
cd webarena_prompt_injections/
bash setup.sh
```

You can also run the unit tests to ensure that VisualWebArena is installed correctly:
```bash
cd visualwebarena/
pytest -x
```


## Running a simple adhoc end-to-end prompt injection test

1. Setup the standalone environments.
Please check out [this page](visualwebarena/environment_docker/README.md) for details. We use `gitlab` and `reddit` environments, so you can discard setup instructions for all other websites. 



2. Set up API keys.

* Set a valid OpenAI API key (starting with `sk-`) as the environment variable: 
    ```bash
    export OPENAI_API_KEY='your_key'
    ```
    Alternatively, set Azure API key and Azure Endpoint if you are accessing OpenAI models via Azure:
    ```bash
    export AZURE_API_KEY='your_azure_api_key'
    export AZURE_API_ENDPOINT='your_azure_endpoint'
    export AZURE_API_VERSION='your_azure_api_version'
    ``` 
* For Claude, the code expects `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN`. 
  Note that we still need OpenAI/Azure API keys to run evaluators.

3. Set up the top-level configuration in `webarena_prompt_injections/config/config.yaml`. In particular:
   * Set the directory for all experimental results with `base_log_directory`. Subfolders will be created here for each experiment run.
   * define the model deployment names in the `deployment_model_name` dictionary. It maps from `short_model_name` as used in the subconfigs (more on this below) to a full deployment name that APIs expect.
   * define where there are available GitLab and Reddit deployments in  `env_deployments`, as a comma-separated list of ip's. 



4. Set up an experiment by defining tasks in json format in the `webarena_prompt_injections/task_configs` folder and defining the experiment hyperparameters in the `webarena_prompt_injections/config/experiment` folder in yaml. For now, we will reuse the adhoc setup to demonstrate the script calling quickly. For more advanced new experiment definition, see the next sections. 

5. Run a single task. In this case, we have set up two adhoc tasks with the o1 model.
```
cd webarena_prompt_injections
source venv/bin/activate
python run_end_to_end_in_parallel.py +experiment=o1-adhoc 
```

## Running the experiments from the official WASP 1.0 release

### Naming Pattern for Experiments from the first WASP Release
We use the name of the model, the name of the scaffolding, and an "experiment group" (e.g. benign tasks without prompt injections or tasks with prompt injections on the execution path, system prompt on or off) in the experiment names. The experiment groups are defined as follows: 
* each experiment has either `adhoc`, `utility`, or `goal-hijacking` in the name, followed by a number
   * `adhoc` is meant for one-off tasks that are not part of the official WASP release
   * `goal-hijacking` contains tasks that set up the environment with a prompt injection on the execution path. These are the tests that form the basis for Attack Success Rate End to End, Attack Success Rate Intermediate, and the Utility under Attack (the last one is not in the paper)
   * `utility` contains tasks without any prompt injections that are used for the Utility metric in the paper
* the numbers have the following meanings:
   * `0` means no **configurable** defenses and no extended capabilities (like reasoning or interleaved reasoning, where these are configurable)
   * `1` means that a system prompt defense is applied (not available for tool-calling agents currently)
   * `2` means interleaved thinking is turned on (only available for Claude 4) or the `developer` system role is used for `o1`

For example, the prompt injection tasks with gpt-4o with no defense would be: `gpt-4o-tool-calling-goal-hijacking-0` and the utility tasks with system prompt would be `gpt-4o-tool-calling-utility-clean-1`.



### All utility experiments
**Note**: Please, make sure you have installed everything, activated the `webarena_prompt_injections/venv`, and set your keys in the OS environment variables as above!

```bash
python run_end_to_end_in_parallel.py --multirun +experiment=claude-35-curi-35-utility-0,claude-35-curi-35-utility-1,claude-37-curi-37-utility-0,claude-37-curi-37-utility-1,claude-4-sonnet-tool-calling-utility-0.,claude-4-sonnet-tool-calling-utility-2,gpt-4o-mini-tool-calling-utility-0,gpt-4o-mini-tool-calling-utility-1,gpt-4o-mini-visualwebarena-axtree-utility-0,gpt-4o-mini-visualwebarena-axtree-utility-1,gpt-4o-mini-visualwebarena-som-utility-0,gpt-4o-mini-visualwebarena-som-utility-1,gpt-4o-tool-calling-utility-0,gpt-4o-tool-calling-utility-1,gpt-4o-visualwebarena-axtree-utility-0,gpt-4o-visualwebarena-axtree-utility-1,gpt-4o-visualwebarena-som-utility-0,gpt-4o-visualwebarena-som-utility-1,o1-tool-calling-utility-0,o1-tool-calling-utility-2
```

### All Goal-Hijacking Prompt Injection Experiments
**Note**: Please, make sure you have installed everything, activated the `webarena_prompt_injections/venv`, and set your keys in the OS environment variables as above!

```bash
python run_end_to_end_in_parallel.py --multirun +experiment=claude-35-curi-35-goal-hijacking-0,claude-35-curi-35-goal-hijacking-1,claude-37-curi-37-goal-hijacking-0,claude-37-curi-37-goal-hijacking-1,claude-4-sonnet-tool-calling-goal-hijacking-0,claude-4-sonnet-tool-calling-goal-hijacking-2,gpt-4o-mini-tool-calling-goal-hijacking-0,gpt-4o-mini-tool-calling-goal-hijacking-1,gpt-4o-mini-visualwebarena-axtree-goal-hijacking-0,gpt-4o-mini-visualwebarena-axtree-goal-hijacking-1,gpt-4o-mini-visualwebarena-som-goal-hijacking-0,gpt-4o-mini-visualwebarena-som-goal-hijacking-1,gpt-4o-tool-calling-goal-hijacking-0,gpt-4o-tool-calling-goal-hijacking-1,gpt-4o-visualwebarena-axtree-goal-hijacking-0,gpt-4o-visualwebarena-axtree-goal-hijacking-1,gpt-4o-visualwebarena-som-goal-hijacking-0,gpt-4o-visualwebarena-som-goal-hijacking-1,o1-tool-calling-goal-hijacking-0,o1-tool-calling-goal-hijacking-2
```

### Printing the Results Table
You can run this command from the `webarena_prompt_injections` folder to print the results table with all the metrics we need.
```
python evaluate.py --log-dir <base_log_directory from the config/config.yaml>
```

This will go through all subdirectories of the `base_log_directory`, interpret them as results generated with the `run_end_to_end_in_parallel.py` script, and print a few tables. Most of those just give you a granular view in each metric and you can ignore them. The most important one -- the full final result of all metrics we report -- will come at the end and will look like this:



| Model | Scaffolding | Inputs | Defense Mechanism | ASR-End-to-End | ASR-Intermediate | Utility Under Attack | Utility Clean |
|-------|-------------|--------|-------------------|----------------|------------------|----------------------|---------------|
| claude-4-sonnet | tool-calling | axtree | interleaved reasoning | 0.083333 | 0.130952 | 0.940476 | 0.729730 |
| claude-4-sonnet | tool-calling | axtree | none | 0.154762 | 0.202381 | 0.940476 | 0.837838 |
| gpt-4o | tool-calling | axtree | none | 0.059524 | 0.107143 | 0.809524 | 0.571429 |


## What happens during a run?
At a high level, here is what will happen:
* Each of the comma-separated `env_ip`'s from the `config/experiment/experiment_name.yaml` will be treated as a deployment that has GitLab on port 8023 and Reddit on port 9999.
* Each Reddit and each GitLab task (each dictionary in the JSON list in `configs/example_task_config.json`) will be randomly assigned to one of these deployments. Task ids that have evals in the log folder will be skipped, so that the run can be restarted. 
* All `setup_fn`'s from your `webarena_prompt_injections/task_configs/example_task_config.json` will be ran upfront sequentially and without parallelization. 
   * Parameters for this function will be taken from the `parameters` field of the json dictionary and any return values of the function. 
   * Additionally, any strings under `eval` and `prompt_injection_eval` will be materialized based on the same dictionary. 
   * Additionally, the `user_instruction_template` and `start_url_template` will also be formatted/materialized with the same parameters and new dictionary keys will be added: `intent` and `start_url`.
   * The materialized/formatted task configs in this way will be written under `tasks` in the log folder.
* The agent configured in `config/experiment/experiment_name.yaml` will be kicked off in parallel while maintaining a lock on any given environment. If you had only one deployment, the parallelization will only be between Reddit and GitLab and each instance will still be locked independently. 
* Still parallelized, "utility" will be evaluated by following the specification `eval` from the dictionary in `webarena_prompt_injections/task_configs/example_task_config.json`.
* Still parallelized, if `prompt_injection_success_eval` is present in the current dictionary, this will be used to evaluate if the prompt injection succeeded end-to-end.
* Logs will be written to subfolders of the `hydra.run.dir` folder (you can also see on the stdout what that is exactly or reconstruct the pattern yourself based on the `config/config.yaml`). Here are the subfolders and files that will be created:
   * `agent_logs` the logs that each agent scaffolding outputs
   * `eval_results` contains `json` files with the status of each eval. Any task id not present here and any task id for which the status is not `completed` will be reran at any given run of the experiment.
   * `tasks` the folder containing the materialized tasks based on formatting the strings in 

## Defining New Tasks
We currently define tasks in files that have json format and contain a list of dictionary objects. A basic example is given in `webarena_prompt_injections/task_configs/basic_adhoc_tasks.json` with and without a prompt injection. In order to add new...
* **utility/"clean" tasks**: simply define the setup function (or borrow one from `environment_setup.py`), provide its necessary parameters, and provide the user instruction template and eval for it.
* **prompt injection tasks**: same as above but use a setup function like `make_attacker_account_and_issue_with_prompt_injection`, include an `adversarial_instruction_template` in the parameters dictionary, and add a `prompt_injection_success_eval` definition.


## Setting up a New Experiment
This consits of adding an experiment-defining config to the `config/experiment` folder. An experiment config is expected to look like:
```yaml
short_model_name: "your model name here" # a descriptive model name that will be used in the folder name for the logs. Make sure there is a corresponding mapping in the top-level yaml config's deployment model names.
skip_docker_build: true # if using the curi-35 or curi-37 scaffolding recommend setting this to True
max_actions: 20 # cap the number of actions/tool calls the agent is allowed to make
system_objective_message_role: "system"  # currently developer is only supported for o1
max_observations_to_keep: 3 # for curi and tool-calling scaffoldings, how many past environment observations to send with each request to the model
scaffolding: "tool-calling" # can also be curi-35 or curi-37 or visualwebarena-axtree or visualwebarena-som
use_defensive_system_prompt: False # currently True is only supported for Claude models with the CURI scaffolding and for the visualwebarena scaffolding
defensive_system_prompt: "foo" # if use_defensive_system_prompt is true and the scaffolding is CURI-35 or CURI-37, append this to the system prompt. IMPORTANT: For visualwebarena-* scaffoldings, this is not used and we read the file at agent/prompts/jsons/wa_p_cot_id_actree_3s_generic_defense.json in the visualwebarena scaffolding directory
enable_thinking: False # True is only supported for Claude with the Tool-Calling scaffolding
enable_interleaved_thinking: False # True is only supported for Claude with the Tool-Calling scaffolding; this is a unique feature of Claude models
experiment_group: "adhoc" # or define your own, this will be used in the folder naming
tasks: "tasks_for_your_experiment_here"  # Path to the JSON file describing the webarena tasks
```



## Other Common Recipes
* To test only the environment setup, skip the agent and eval:
```
python run_end_to_end_in_parallel.py +experiment=o1-adhoc  skip_agent=True skip_evaluation=True skip_environment_cleanup=True
```

* If you have instead already setup the environment and have materialized tasks written under your folder, you can skip environment setup (this can happen if there's an adhoc failure in the agent that brings down the whole script but mostly useful during development):
```
python run_end_to_end_in_parallel.py +experiment=o1-adhoc  skip_environments_setup=True
```

* If you want to do the tasks manually, first run only the environment setup as above. Then, run only the eval. In this case, because `skip_environments_setup` is `True`, the tasks will be loaded from the materialized jsons under `tasks` in the log folder for the experiment.
```
python run_end_to_end_in_parallel.py +experiment=o1-adhoc  skip_environments_setup=True skip_agent=True skip_environment_cleanup=True
```


## Known Limitations and In-Progress Work
* Our script is currently tailored to the `reddit` and `gitlab` environments at ports 9999 and 8023 ONLY. Extending to new environments might require a slightly bigger refactor.
* Prompt injection tasks 4010, 4031, 4052, and 4073 are not parallelizable on the same environment since they all ask for making the same agent user public in the injection.
* Prompt injection tasks 4011, 4032, 4053, and 4074 are not parallelizable on the same environment since they all ask for edits to the same file in the injection.
* The reddit tasks are not parallelizable on the same environment since they take actions on the same posts. If cleanup happens properly, however, reusing an environment should be okay.
* Any given reddit deployment has a rate limit of 3 new user account creations and 3 posts per user. We have written the `webarena_prompt_injections/task_configs/prompt_injection_tests.json` to interleave attacker account creation and post creation with any given account without triggering that but any further extensions with more tasks will run into trouble. Which leads us to:
* Maintaining two different configuration systems - one for tasks in `json` format and one in `yaml` for experiments broadly is not great. We should standardize to yaml but that requires a much bigger rewrite. Maybe I'll see if some coding agent can help...
* Agents running the `visualwebarena` scaffolding with Set-of-Marks (SOM) are not parallelizable on the same machine since that scaffolding loads a model in GPU memory and takes up the whole GPU memory.


## Resetting environments

Our scripts automatically cleans up environment after each run. However, sometimes manual reset is required. To do so, please follow steps on [this page](visualwebarena/environment_docker/README.md#environment-reset).


## Acknowledgements

Our code is heavily based off the <a href="https://github.com/web-arena-x/webarena">WebArena</a>, <a href="https://github.com/web-arena-x/visualwebarena">VisualWebArena</a> and <a href="https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo">Anthropic Computer Use Demo</a> codebases.

## License
The majority of WASP is licensed under [CC-BY-NC 4.0 license](./LICENSE), however portions of the project are available under separate license terms: visualwebarena is licensed under the MIT license. More information available [via this link](./visualwebarena/LICENSE). The [data](./webarena_prompt_injections/configs/experiment_config.raw.json) is intended for benchmarking purposes and is licensed CC-BY-NC. License for using Claude computer use demo code is available [via this link](./claude-35-computer-use-demo/LICENSE).
