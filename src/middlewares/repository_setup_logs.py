import json
from typing import Any

from langchain_core.messages import ToolMessage

from src.nodes.script import sandbox_output_text


def _message_payload(message: Any) -> Any:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    return content


def repo_setup_terminal_log(messages: list[Any]) -> str:
    """Return raw sandbox setup output from repo setup tool messages."""
    sections = []

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue

        if getattr(message, "name", "") != "create_sandbox_clone_repo_and_install":
            continue

        payload = _message_payload(message)
        if not isinstance(payload, dict):
            continue

        sandbox_install = payload.get("sandbox_install")
        if not isinstance(sandbox_install, dict):
            continue

        sandbox_text = sandbox_output_text(sandbox_install).strip()
        sandbox_error = sandbox_install.get("error")
        if not sandbox_text and not sandbox_error:
            continue

        section = ["\n=== Sandbox operations log ==="]
        if sandbox_text:
            section.append(sandbox_text)
        if sandbox_error:
            section.append(f"SANDBOX_ERROR {sandbox_error}")
        section.append("=== End sandbox operations log ===\n")
        sections.append("\n".join(section))

    return "\n".join(sections)
