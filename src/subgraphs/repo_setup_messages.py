import json
import re
from typing import Any

from langchain_core.messages import ToolMessage


SETUP_TOOL_NAME = "create_sandbox_clone_repo_and_install"


def fallback_question_from_messages(messages: list[Any]) -> str | None:
    if not messages or not isinstance(messages[-1], ToolMessage):
        return None

    latest = messages[-1]
    if latest.name != SETUP_TOOL_NAME:
        return None

    try:
        payload = json.loads(str(latest.content))
    except json.JSONDecodeError:
        return None

    if payload.get("ok"):
        return None

    fallback_questions = payload.get("fallback_questions")
    if not fallback_questions:
        return None

    return str(fallback_questions[0])


def latest_setup_payload(messages: list[Any]) -> dict[str, Any] | None:
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue
        if message.name != SETUP_TOOL_NAME:
            continue
        try:
            payload = json.loads(str(message.content))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
    return None


def latest_tool_name(messages: list[Any]) -> str | None:
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            return message.name
    return None


def latest_repo_url(messages: list[Any]) -> str | None:
    pattern = re.compile(r"(?:https://github\.com/[^\s`'\"<>]+|git@github\.com:[^\s`'\"<>]+)")
    for message in reversed(messages):
        content = str(getattr(message, "content", ""))
        match = pattern.search(content)
        if match:
            return match.group(0).rstrip(".,)")
    return None
