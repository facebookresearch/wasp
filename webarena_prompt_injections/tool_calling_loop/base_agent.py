import json
import sys
from constants import Provider
from envs import ScriptBrowserEnv
from constants import ACCOUNTS
from actions import TOOL_NAME_TO_CREATE_ACTION_FUNCTION


class BaseToolCallingAgent:
    def __init__(
        self,
        model: str,
        system_prompt: str,
        filepath_to_trace_log: str,
        provider: Provider,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.filepath_to_trace_log = filepath_to_trace_log
        self.provider = provider

    def __enter__(self):
        self.trace_log_file = open(self.filepath_to_trace_log, "a")
        # call this so that the mixins can also set up their environment
        return super().__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        self.trace_log_file.close()
        # call this so that the mixins can also clean up their environment
        super().__exit__(exc_type, exc_value, traceback)

    def _call_model(self, messages: list[dict]):
        raise NotImplementedError(
            "This method should be implemented in a subclass that filters tool call results."
        )

    def _create_user_message(self, content):
        raise NotImplementedError(
            "This method should be implemented in a subclass that filters tool call results."
        )

    def _create_tool_message(self, tool_call_id, content):
        raise NotImplementedError(
            "This method should be implemented in a subclass that filters tool call results."
        )

    def _create_stop_message(self, answer):
        raise NotImplementedError(
            "This method should be implemented in a subclass that filters tool call results."
        )

    def _parse_model_response(self, response_message):
        raise NotImplementedError(
            "This method should be implemented in a subclass that filters tool call results."
        )

    def _maybe_filter_tool_call_results(
        self, messages: list[dict], max_observations_to_keep: int
    ):
        raise NotImplementedError(
            "This method should be implemented in a subclass that filters tool call results."
        )

    def _format_tool_response_message(
        self, tool_call_results: list[dict]
    ) -> list[dict]:
        raise NotImplementedError(
            "This method should be implemented in a subclass that formats tool response messages."
        )

    def _get_tool_name(self, tool_use_message: dict) -> list[str]:
        raise NotImplementedError(
            "This method should be implemented in a subclass that retrieves tool names from tool use messages."
        )

    def _get_tool_arguments(self, tool_use_message: dict) -> dict:
        raise NotImplementedError(
            "This method should be implemented in a subclass that retrieves tool arguments from tool use messages."
        )

    def _extract_tool_calls(self, response_message: dict) -> list[dict]:
        """
        Extract tool calls from the model response message.
        This method should be implemented in a subclass that handles specific model responses.
        """
        raise NotImplementedError(
            "This method should be implemented in a subclass that extracts tool calls from the model response."
        )

    def _check_for_stop_action_in_result_of_execution(
        self, result_of_execution: list[dict]
    ) -> bool:
        raise NotImplementedError(
            "This method should be implemented in a subclass that checks for stop actions in the result of execution."
        )

    def _log_messages(self, messages):
        self.trace_log_file.write(json.dumps(messages) + "\n")

    def loop(
        self,
        user_objective: str,
        max_actions: int,
        max_observations_to_keep: int,
    ):
        messages = []

        user_intent_message = self._create_user_message(user_objective)
        messages.append(user_intent_message)

        for action_number in range(max_actions):
            print(
                f"[{action_number} of max {max_actions}] Calling model {self.model}",
                file=sys.stderr,
            )
            model_response_message = self._call_model(messages)

            # print(
            #     f"Model [{self.model}] response {action_number} {model_response_message['content']}",
            #     file=sys.stderr,
            # )

            result_of_execution = self._execute_requested_tool_calls(
                self._extract_tool_calls(model_response_message)
            )

            if isinstance(model_response_message, list):
                messages.extend(model_response_message)
            else:
                messages.append(model_response_message)

            if len(result_of_execution) < 1:
                print("Agent did not call any tools; exiting.", file=sys.stderr)
                break

            # In the case of the OpenAI API, we append a new message for each tool result.
            # However, for Anthropic, everything goes in a single "User" message, so we let the child classes handle that accordingly.
            tool_response_message = self._format_tool_response_message(
                result_of_execution
            )

            messages.extend(tool_response_message)

            self._log_messages(messages)

            answer_if_stop_action = self._check_for_stop_action_in_result_of_execution(
                result_of_execution
            )

            if answer_if_stop_action:

                print(
                    f"Agent finished with stop action and answer {answer_if_stop_action}",
                    file=sys.stderr,
                )
                return answer_if_stop_action

            self._maybe_filter_tool_call_results(messages, max_observations_to_keep)
            print("+" * 80 + "\n", file=sys.stderr)


class WebAgentMixin:
    def __enter__(
        self,
    ):
        self.browser_env = ScriptBrowserEnv(
            headless=True,
            slow_mo=0,
            observation_type="accessibility_tree",
            current_viewport_only=False,
            viewport_size={
                "width": 1280,
                "height": 2048,
            },
            save_trace_enabled=False,
            sleep_after_execution=0.0,
            captioning_fn=None,
        )
        self.browser_env.reset()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.browser_env.close()

    def _login_to_gitlab(self, env_ip: str):
        page = self.browser_env.page
        username = ACCOUNTS["gitlab"]["username"]
        password = ACCOUNTS["gitlab"]["password"]
        page.goto(f"{env_ip}/users/sign_in")
        page.get_by_test_id("username-field").click()
        page.get_by_test_id("username-field").fill(username)
        page.get_by_test_id("username-field").press("Tab")
        page.get_by_test_id("password-field").fill(password)
        page.get_by_test_id("sign-in-button").click()

    def _login_to_reddit(self, env_ip: str):
        page = self.browser_env.page
        username = ACCOUNTS["reddit"]["username"]
        password = ACCOUNTS["reddit"]["password"]
        page.goto(f"{env_ip}/login")
        page.get_by_label("Username").fill(username)
        page.get_by_label("Password").fill(password)
        page.get_by_role("button", name="Log in").click()

    def login(self, sites: list[str], env_ip: str):
        if "gitlab" in sites:
            self._login_to_gitlab(env_ip)

        if "reddit" in sites:
            self._login_to_reddit(env_ip)

    def _execute_requested_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        # we will consistently return a list of dicitonaries in the message format
        # even though in non-error cases that list will be of length 1
        if len(tool_calls) > 1:
            return [
                self._create_tool_message(
                    tool_call,
                    "ERROR: Multiple tool calls provided. You MUST respond with ONLY one tool call!",
                )
                for tool_call in tool_calls
            ]

        if len(tool_calls) < 1:
            return []

        tool_call = tool_calls[0]

        tool_name = self._get_tool_name(tool_call)
        if tool_name not in TOOL_NAME_TO_CREATE_ACTION_FUNCTION:
            return [
                self._create_tool_message(
                    tool_call,
                    f"ERROR: {tool_name} is not a valid function! You must pick one of {','.join(TOOL_NAME_TO_CREATE_ACTION_FUNCTION.keys())}",
                )
            ]

        args = self._get_tool_arguments(tool_call)

        if tool_name == "stop":
            return [self._create_stop_message(args["answer"])]

        create_action_function = TOOL_NAME_TO_CREATE_ACTION_FUNCTION[tool_name]
        try:
            action = create_action_function(**args)
        except TypeError as e:
            return [self._create_tool_message(tool_call, f"ERROR: {e}")]

        browser_execution_result = self.browser_env.step(action)
        # the step function returns a tuple but we are only interested in the observation, which is in the first position
        # the Observation object is then keyed by modality, which is always text
        observation_text = browser_execution_result[0]["text"]

        formatted_tool_call_result = f"""OBSERVATION:
{observation_text}
URL: {self.browser_env.page.url}
"""

        return [self._create_tool_message(tool_call, formatted_tool_call_result)]


class EmailMixin:

    def __enter__(self):
        # Dummy enter method to prevent errors when called by BaseToolCallingAgent
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Dummy exit method to prevent errors when called by BaseToolCallingAgent
        pass

    def _execute_requested_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        # we will consistently return a list of dicitonaries in the message format
        # even though in non-error cases that list will be of length 1
        if len(tool_calls) > 1:
            return [
                self._create_tool_message(
                    tool_call,
                    "ERROR: Multiple tool calls provided. You MUST respond with ONLY one tool call!",
                )
                for tool_call in tool_calls
            ]

        if len(tool_calls) < 1:
            return []

        tool_call = tool_calls[0]

        tool_name = self._get_tool_name(tool_call)
        valid_tools = ["send_email", "read_email"]
        if tool_name not in valid_tools:
            return [
                self._create_tool_message(
                    tool_call,
                    f"ERROR: {tool_name} is not a valid function! You must pick one of {', '.join(valid_tools)}",
                )
            ]

        args = self._get_tool_arguments(tool_call)

        if tool_name == "send_email":
            # Here you would implement the logic to send an email using the provided arguments.
            # For now, we will just simulate sending an email and return a success message.
            formatted_tool_call_result = f"Email sent to {args['to']} with subject '{args['subject']}' and body '{args['body']}'"
        elif tool_name == "read_email":
            # Simulate reading emails - in a real implementation, you would fetch actual emails
            # Args could include filters like 'from', 'subject', 'unread_only', etc.
            emails = [
                {
                    "from": "user@example.com",
                    "subject": "Meeting reminder",
                    "body": "Don't forget our meeting tomorrow at 2pm.",
                    "date": "2023-11-30 09:15",
                },
                {
                    "from": "support@service.com",
                    "subject": "Your ticket #12345",
                    "body": "Your support request has been processed.",
                    "date": "2023-11-29 16:45",
                },
            ]

            # Apply any filters from the args
            if "from" in args and args["from"]:
                emails = [
                    e for e in emails if args["from"].lower() in e["from"].lower()
                ]
            if "subject" in args and args["subject"]:
                emails = [
                    e for e in emails if args["subject"].lower() in e["subject"].lower()
                ]

            formatted_tool_call_result = f"Found {len(emails)} emails:\n\n" + "\n\n".join(
                f"From: {email['from']}\nSubject: {email['subject']}\nDate: {email['date']}\n{email['body']}"
                for email in emails
            )

        return [self._create_tool_message(tool_call, formatted_tool_call_result)]
