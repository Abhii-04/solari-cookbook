import os
from typing import Any

from langchain_core.tools import tool

from src.nodes.local import (
    clone_repo_and_install_dependencies,
    is_supported_git_url,
    repo_name_from_url,
)
from src.middlewares.repo_setup_progress import await_with_progress, emit_setup_progress
from src.nodes.repo_setup_output import (
    fallback_questions,
    sandbox_progress_events,
    sandbox_repo_profile,
)
from src.nodes.script import sandbox_output_text, sandbox_setup_script
from src.tools.SolariSandbox import SolariSandboxClient

SOCKET_TOKEN_ENV_KEYS = (
    "SOCKET_API_TOKEN",
    "SOCKET_API_KEY",
    "SOCKET_CLI_API_TOKEN",
    "SOCKET_CLI_API_KEY",
    "SOCKET_SECURITY_API_TOKEN",
    "SOCKET_SECURITY_API_KEY",
)

@tool
async def create_sandbox_clone_repo_and_install(
    repo_url: str,
    env_overrides: dict[str, str] | None = None,
    startup_command: str | None = None,
    install_on_user_device: bool = True,
) -> dict[str, Any]:
    """Create a Solari sandbox, install and run a repo there, then install locally."""
    install_on_user_device = True
    if not is_supported_git_url(repo_url):
        return {
            "ok": False,
            "repo_url": repo_url,
            "error": "Only GitHub repository URLs are supported, for example https://github.com/owner/repo.",
        }

    repo_name = repo_name_from_url(repo_url)
    emit_setup_progress(
        "Creating secure Solari sandbox",
        repo_url=repo_url,
        repo_name=repo_name,
    )
    try:
        sandbox_result = await SolariSandboxClient().create(connect=True)
    except Exception as exc:
        emit_setup_progress(
            "Could not create Solari sandbox",
            repo_url=repo_url,
            repo_name=repo_name,
            error=f"{type(exc).__name__}: {exc}",
        )
        return {
            "ok": False,
            "repo_url": repo_url,
            "repo_name": repo_name,
            "error": f"Could not create Solari sandbox: {type(exc).__name__}: {exc}",
        }

    sandbox_id = sandbox_result["sandbox_id"]
    emit_setup_progress(
        "Sandbox ready; cloning repo and starting sandbox checks",
        repo_url=repo_url,
        repo_name=repo_name,
        sandbox_id=sandbox_id,
        control_url=sandbox_result.get("control_url"),
    )
    socket_api_token = None
    if env_overrides and any(env_overrides.get(key) for key in SOCKET_TOKEN_ENV_KEYS):
        socket_api_token = next(
            env_overrides[key]
            for key in SOCKET_TOKEN_ENV_KEYS
            if env_overrides.get(key)
        )
    else:
        for key in SOCKET_TOKEN_ENV_KEYS:
            token = os.getenv(key)
            if token:
                socket_api_token = token
                break
    repo_env_overrides = {
        key: value
        for key, value in (env_overrides or {}).items()
        if key not in SOCKET_TOKEN_ENV_KEYS
    }
    try:
        sandbox_install = await await_with_progress(
            SolariSandboxClient().run_code(
                sandbox_id=sandbox_id,
                code=sandbox_setup_script(
                    repo_url,
                    repo_name,
                    env_overrides=repo_env_overrides,
                    startup_command=startup_command,
                    socket_api_token=socket_api_token,
                ),
                language="python",
            ),
            "Sandbox checks are still running",
            repo_url=repo_url,
            repo_name=repo_name,
            sandbox_id=sandbox_id,
        )
    except Exception as exc:
        emit_setup_progress(
            "Sandbox setup script failed to execute",
            repo_url=repo_url,
            repo_name=repo_name,
            sandbox_id=sandbox_id,
            error=f"{type(exc).__name__}: {exc}",
        )
        sandbox_install = {
            "type": "sandbox_code_execution",
            "sandbox_id": sandbox_id,
            "language": "python",
            "outputs": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    sandbox_error = sandbox_install.get("error")
    sandbox_output = sandbox_output_text(sandbox_install)
    sandbox_profile = sandbox_repo_profile(sandbox_output)
    for event in sandbox_progress_events(sandbox_output):
        emit_setup_progress(
            event["message"],
            repo_url=repo_url,
            repo_name=repo_name,
            sandbox_id=sandbox_id,
            **{key: value for key, value in event.items() if key != "message"},
        )
    sandbox_ok = (
        sandbox_error in (None, "")
        and "REPO_SECURITY_STATUS 0" in sandbox_output
        and "REPO_SOCKET_MCP_STATUS 0" in sandbox_output
        and "REPO_SMOKE_STATUS 0" in sandbox_output
        and "REPO_TEST_STATUS 0" in sandbox_output
        and "REPO_SETUP_STATUS 0" in sandbox_output
    )

    if sandbox_ok:
        emit_setup_progress(
            "Sandbox checks passed; cloning and installing locally",
            repo_url=repo_url,
            repo_name=repo_name,
            sandbox_id=sandbox_id,
        )
        local_install = clone_repo_and_install_dependencies.invoke(
            {"repo_url": repo_url, "sandbox_checks_passed": True}
        )
    else:
        emit_setup_progress(
            "Sandbox checks failed; local clone/install skipped",
            repo_url=repo_url,
            repo_name=repo_name,
            sandbox_id=sandbox_id,
        )
        local_install = {
            "ok": False,
            "repo_url": repo_url,
            "local_install_skipped": True,
            "error": (
                "Skipped local clone/install because the sandbox security scan, "
                "Socket MCP dependency scan, install, smoke run, or test run did not complete successfully."
            ),
        }

    local_ok = bool(local_install.get("ok"))
    emit_setup_progress(
        "Repository setup finished" if sandbox_ok and local_ok else "Repository setup stopped",
        repo_url=repo_url,
        repo_name=repo_name,
        sandbox_id=sandbox_id,
        ok=sandbox_ok and local_ok,
        local_path=local_install.get("repo_path") if isinstance(local_install, dict) else None,
    )
    return {
        "ok": sandbox_ok and local_ok,
        "repo_url": repo_url,
        "repo_name": repo_name,
        "sandbox": sandbox_result,
        "sandbox_repo_path": (
            sandbox_profile.get("repo_path")
            if isinstance(sandbox_profile, dict) and sandbox_profile.get("repo_path")
            else f"/workspace/{repo_name}"
        ),
        "sandbox_repo_profile": sandbox_profile,
        "sandbox_install": sandbox_install,
        "local_install": local_install,
        "install_on_user_device": install_on_user_device,
        "fallback_questions": fallback_questions(sandbox_output, local_install),
    }
