from pathlib import Path
from string import Template
from typing import Any

SANDBOX_TESTS_DIR = Path(__file__).parents[1] / "sandbox_tests"

#If you want to add custom tests then just write them in sandbox_tests
#In the same format as other files and include them here
#But order matters cause they are combined to form a big single script so it should be in 
# a proper order else it might fail or produce an error
SANDBOX_TEST_FRAGMENTS = (
    "core.py.tmpl",
    "repository.py.tmpl",
    "security.py.tmpl",
    "discovery.py.tmpl",
    "smoke.py.tmpl",
    "test_checks.py.tmpl",
    "socket_mcp.py.tmpl",
    "main_flow.py.tmpl",
)


def _sandbox_setup_template_text() -> str:
    return "\n\n".join(
        (SANDBOX_TESTS_DIR / filename).read_text().rstrip()
        for filename in SANDBOX_TEST_FRAGMENTS
    ) + "\n"


def sandbox_setup_script(
    repo_url: str,
    repo_name: str,
    env_overrides: dict[str, str] | None = None,
    startup_command: str | None = None,
    socket_api_token: str | None = None,
) -> str:
    return Template(_sandbox_setup_template_text()).substitute(
        repo_url_literal=repr(repo_url),
        repo_name_literal=repr(repo_name),
        env_overrides_literal=repr(env_overrides or {}),
        startup_command_literal=repr(startup_command),
        socket_api_token_literal=repr(socket_api_token),
    )


def sandbox_output_text(result: dict[str, Any]) -> str:
    text_parts = []
    for output in result.get("outputs", []):
        text = output.get("text")
        if text:
            text_parts.append(str(text))
    return "\n".join(text_parts)
