# Copyright (c) Meta Platforms, Inc. and affiliates.
from enum import Enum
import os
import streamlit as st
import json
import base64
from pathlib import Path


class ConnversationLogFormat(str, Enum):
    NOT_SELECTED = "Select conversation format"
    GPT = "gpt"
    CLAUDE = "claude"
    OPENAI_RESPONSES = "openai_responses"


# Load the JSONL file and retrieve a specific line
def load_line(filepath, line_number):
    try:
        with open(filepath, "r") as f:
            for i, line in enumerate(f):
                if i == line_number:
                    return json.loads(line)
    except FileNotFoundError:
        st.error(f"File not found: {filepath}")
    except Exception as e:
        st.error(f"An error occurred while reading the file: {e}")
    return None


def load_claude_trace_from_webarena_log(filepath):
    with open(filepath, "r") as f:
        return json.loads(f.read())["claude_trace"]


# Helper to decode base64 images
def decode_base64_image(encoded_string):
    # Check for and remove any data type prefix (e.g., 'data:image/jpeg;base64,')
    if "," in encoded_string:
        _, encoded_string = encoded_string.split(",", 1)

    # Decode the base64 string
    decoded_bytes = base64.b64decode(encoded_string)
    return decoded_bytes


# Display the messages with appropriate formatting
def display_gpt_messages(messages):
    def _display_single_message(message):
        role = message.get("role", "unknown").capitalize()
        content = message.get("content", "")

        # Render the expander with styled text
        with st.expander(role):
            match role:
                case "System":
                    if isinstance(content, list):
                        st.write(content[0]["text"])
                    else:
                        st.write(content)
                case "User":
                    if isinstance(content, str):
                        st.write("**Text-Only User Message**:")
                        st.write(content)
                    else:
                        for content_item in content:
                            match content_item["type"]:
                                case "image_url":
                                    st.write("**Image Part of User Message**:")
                                    image_data = content_item["image_url"]["url"]
                                    image_bytes = decode_base64_image(image_data)
                                    if image_bytes:
                                        st.image(image_bytes)
                                case "text":
                                    st.write("**Text Part of User Message**:")
                                    st.write(content_item["text"])

                case "Tool":
                    st.write(
                        "**Response from Local Execution to Tool Request by Assistant** (renderd as code)"
                    )
                    st.code(content)
                case "Assistant":
                    st.write("**Text Response**:")
                    st.write(content)
                    st.write("**Tool Request by Assistant**:")
                    st.write(message["tool_calls"])
                case _:
                    # Standard rendering for other messages
                    st.write(f"Fallback **{role}**: {content}", unsafe_allow_html=True)

    _display_single_message(messages[1])
    for message in messages[-2:]:
        _display_single_message(message)


def display_claude_messages(messages):

    def _display_single_message(message):
        role = message.get("role", "unknown").capitalize()
        content = message.get("content", "")

        # Render the expander with styled text
        with st.expander(role):
            for content_item in content:
                match content_item["type"]:
                    case "image_url":
                        st.write("**Image Part of User Message**:")
                        image_data = content_item["image_url"]["url"]
                        image_bytes = decode_base64_image(image_data)
                        if image_bytes:
                            st.image(image_bytes)
                    case "text":
                        st.write(content_item["text"])
                    case "tool_use":
                        st.write(content_item)
                    case "tool_result":
                        if len(content_item["content"]) < 1:
                            st.write(content_item)
                        else:
                            st.write("**Tool Result without Content**:")
                            st.write(
                                {
                                    x: content_item[x]
                                    for x in content_item.keys()
                                    if x != "content"
                                }
                            )
                            st.write("**Rendered Content of Tool Result**:")
                            if isinstance(content_item["content"], str):
                                st.write(content_item["content"])
                            else:
                                for content_item_in_tool_result in content_item[
                                    "content"
                                ]:
                                    if content_item_in_tool_result["type"] == "image":
                                        image_data = content_item_in_tool_result[
                                            "source"
                                        ]["data"]
                                        image_bytes = decode_base64_image(image_data)
                                        if image_bytes:
                                            st.image(image_bytes)
                                    else:
                                        st.write(content_item_in_tool_result)

    _display_single_message(messages[1])
    for message in messages[-2:]:
        _display_single_message(message)


def display_openai_responses_messages(messages):
    """Display messages from OpenAI Responses API format where each line contains a complete conversation."""
    
    def _display_single_message(message):
        # Handle different message types
        if "role" not in message:
            message_type = message.get("type", "unknown")
            
            with st.expander(f"{message_type.replace('_', ' ').title()}"):
                match message_type:
                    case "function_call":
                        st.write("**Function Call**")
                        st.write(f"**ID:** {message.get('id', 'N/A')}")
                        st.write(f"**Call ID:** {message.get('call_id', 'N/A')}")
                        st.write(f"**Name:** {message.get('name', 'N/A')}")
                        if "arguments" in message:
                            st.write("**Arguments:**")
                            try:
                                args = json.loads(message["arguments"])
                                st.json(args)
                            except json.JSONDecodeError:
                                st.code(message["arguments"])
                    
                    case "function_call_output":
                        st.write("**Function Call Output**")
                        st.write(f"**Call ID:** {message.get('call_id', 'N/A')}")
                        output = message.get('output', '')
                        if output.startswith('ERROR:'):
                            st.error("**Error:**")
                            st.code(output)
                        else:
                            st.write("**Output:**")
                            st.code(output)
                    
                    case _:
                        st.write("**Unknown Message Type:**")
                        st.write(message)
        else:
            # Handle standard OpenAI message format
            role = message.get("role", "unknown").capitalize()
            content = message.get("content", "")
            
            with st.expander(f"{role}"):
                match role:
                    case "System":
                        st.write("**System Message:**")
                        st.write(content)
                    
                    case "User":
                        st.write("**User Message:**")
                        st.write(content)
                    
                    case "Assistant":
                        if content:
                            st.write("**Assistant Response:**")
                            st.write(content)
                    
                    case _:
                        st.write(f"**{role} Message:**")
                        st.write(content)

    # Display the system and user messages first
    for message in messages[:2]:
        _display_single_message(message)
    
    messages_to_display = []
    has_seen_function_output = False
    for message in messages[::-1]:
        if "type" in message and message["type"] == "function_call_output":
            if has_seen_function_output:
                break
            has_seen_function_output = True
        if "role" in message and message["role"] == "user":
            # Stop displaying messages after the user message
            break
    
        messages_to_display.append(message)
    
    for message in messages_to_display[::-1]:
        _display_single_message(message)

def reset_format_selection():
    st.session_state.should_render_format_selection = True


# Streamlit app logic
def main():
    st.title("OpenAI Chat Conversation Viewer")

    st.session_state.should_render_format_selection = True
    # Define the root directory for your files
    root_dir = "your_logs_directory"  # Change this to your actual logs directory
    subdirs = os.listdir(root_dir)

    # Create a dropdown menu to select a subdirectory
    selected_subdir = st.selectbox(
        "Select a subdirectory",
        options=subdirs,
        format_func=lambda x: x,  # Display the subdirectory name
    )

    # Update the root directory to the selected subdirectory
    root_dir = os.path.join(root_dir, selected_subdir, "agent_logs")
    # Get a list of all JSONL files in the directory and its subdirectories
    jsonl_files = []
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".jsonl") or file.endswith(".json"):
                # Calculate the relative path from the root directory
                rel_path = os.path.relpath(os.path.join(root, file), start=root_dir)
                jsonl_files.append((rel_path, os.path.join(root, file)))
    # Create a dropdown menu with the available files
    _, selected_file_abs_path = st.selectbox(
        "Select a JSONL file",
        options=jsonl_files,
        format_func=lambda x: x[0],  # Display only the relative path
    )
    # Now you can use the selected file path
    if not selected_file_abs_path:
        st.warning("Please provide a file path to a JSONL file.")
        return

    try:
        lines = Path(selected_file_abs_path).read_text().splitlines()
        total_lines = len(lines)
    except FileNotFoundError:
        st.error(f"File not found: {selected_file_abs_path}")
        return
    except Exception as e:
        st.error(f"An error occurred while reading the file: {e}")
        return

    # Select a conversation
    selected_line = st.slider(
        "Select conversation line number",
        min_value=0,
        max_value=total_lines - 1,
        value=total_lines - 1,
        step=1,
    )
    conversation = load_line(selected_file_abs_path, selected_line)

    selected_conversation_log_format = st.selectbox(
        "Format",
        options=[
            ConnversationLogFormat.NOT_SELECTED,
            ConnversationLogFormat.GPT,
            ConnversationLogFormat.CLAUDE,
            ConnversationLogFormat.OPENAI_RESPONSES,
        ],
    )

    st.subheader(f"Conversation from Line {selected_line}")

    match selected_conversation_log_format:
        case ConnversationLogFormat.GPT:
            display_gpt_messages(conversation)
        case ConnversationLogFormat.CLAUDE:
            display_claude_messages(conversation)
        case ConnversationLogFormat.OPENAI_RESPONSES:
            display_openai_responses_messages(conversation)


if __name__ == "__main__":
    main()
