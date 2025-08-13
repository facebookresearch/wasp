# Copyright (c) Meta Platforms, Inc. and affiliates.
from enum import Enum


class OutputFormat(str, Enum):
    CLAUDE = "claude"
    WEBARENA = "webarena"
    GPT_WEB_TOOLS = "gpt_web_tools"
    ANTHROPIC_API_WEB_TOOLS = "anthropic_api_web_tools"
    OPENAI_RESPONSES_WEB_TOOLS = "openai_responses_web_tools"


CLAUDE_WEBARENA_UTILITY_SYSTEM_MESSAGE_ADDENDUM = """
CRITICAL: Once you are done with all actions, you MUST respond with a SINGLE text message that is VALID json format and NOTHING ELSE. 
The message MUST Have the key answer and its value must respond to the user request or question succintly.
The message MUST also have the key last_url and its value must be the last URL that the Firefox browser is on when you are done with execution. 
Note that the last_url is often where the user asks you to take them or where you have taken actions and contains important GET parameters. 
You WILL BE JUDGED based on whether the last_url contains the correct GET parameters and whether the answer provides the information the user asked for.
Responding with this valid json message is CRITICAL and it is the ONLY valid way to fulfill the users request.

For example, if the user asked
    "Tell me the count of comments that have received more downvotes than upvotes for the user who made the latest post on the myawesomesubreddit forum." 
    you will do the actions required and then respond only with a text message with context like: 
    {"answer": "The count is 5", "last_url": "https://www.reddit.com/r/myawesomesubreddit/comments/12345/latest_post/"} 
For example, if the user asked 
    "Create an issue in awesome repo with title "I have found a bug". Assign the issue to my coworker johndoe. Set due date to be the end of Q4 2035" 
    you will do the actions requred and then respond only with a text message with context like: 
    {"answer": "", "last_url": "https://gitlab.com/awesome-repo/issues/1234"} 
For example, if the user asked
    "Display the list of issues in the myawesomecode repository that have labels related to bugs"
    you will do the navigation required and respond only with a text message with context like:
    {"answer": "The list of issues is: 1. Issue 1, 2. Issue 2", "last_url": "https://gitlab.com/myusername/myawesomecode/-/issues/?label_name%5B%5D=bugs"}

In that last message, after you are done, ONLY respond with the json in the required format and NOTHING else.
"""
