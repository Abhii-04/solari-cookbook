from pathlib import Path
from string import Template
from typing import Any

SANDBOX_SETUP_TEMPLATE = Path(__file__).with_name("setup_script.py.tmpl")


def sandbox_setup_script(
    repo_url: str,
    repo_name: str,
    env_overrides: dict[str, str] | None = None,
    startup_command: str | None = None,
) -> str:
    return Template(SANDBOX_SETUP_TEMPLATE.read_text()).substitute(
        repo_url_literal=repr(repo_url),
        repo_name_literal=repr(repo_name),
        env_overrides_literal=repr(env_overrides or {}),
        startup_command_literal=repr(startup_command),
    )


def sandbox_output_text(result: dict[str, Any]) -> str:
    text_parts = []
    for output in result.get("outputs", []):
        text = output.get("text")
        if text:
            text_parts.append(str(text))
    return "\n".join(text_parts)
