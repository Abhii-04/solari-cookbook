import shlex
from typing import Any

from src.nodes.repo_setup_output import (
    sandbox_install_failure_summary,
    sandbox_socket_mcp_failure_summary,
    sandbox_test_failure_summary,
)
from src.nodes.script import sandbox_output_text


def preferred_node_start_command(entrypoints: dict[str, Any], manifests: list[Any]) -> str | None:
    scripts = entrypoints.get("node_scripts")
    if not isinstance(scripts, dict):
        return None

    script_name = next((name for name in ["start", "dev", "serve", "preview"] if name in scripts), None)
    if not script_name:
        return None

    manifest_names = {str(manifest).rsplit("/", 1)[-1] for manifest in manifests}
    if "pnpm-lock.yaml" in manifest_names:
        manager = "pnpm"
    elif "yarn.lock" in manifest_names:
        manager = "yarn"
    elif "bun.lock" in manifest_names or "bun.lockb" in manifest_names:
        manager = "bun"
    else:
        manager = "npm"

    if manager == "yarn":
        return f"yarn {script_name}"
    if manager == "npm" and script_name == "start":
        return "npm start"
    return f"{manager} run {script_name}"


def preferred_python_start_command(entrypoints: dict[str, Any], manifests: list[Any]) -> str | None:
    python_entrypoints = entrypoints.get("python")
    if not python_entrypoints:
        return None

    first_entrypoint = str(python_entrypoints[0])
    manifest_names = {str(manifest).rsplit("/", 1)[-1] for manifest in manifests}
    if "uv.lock" in manifest_names or "pyproject.toml" in manifest_names:
        return f"uv run python {shlex.quote(first_entrypoint)}"
    if any(name.startswith(("requirement", "requirements")) for name in manifest_names):
        return f".venv/bin/python {shlex.quote(first_entrypoint)}"
    return f"python3 {shlex.quote(first_entrypoint)}"


def detected_start_command(
    candidates: list[Any],
    entrypoints: dict[str, Any],
    manifests: list[Any],
) -> str | None:
    if candidates:
        return str(candidates[0])
    if not isinstance(entrypoints, dict):
        return None

    node_command = preferred_node_start_command(entrypoints, manifests)
    if node_command:
        return node_command

    python_command = preferred_python_start_command(entrypoints, manifests)
    if python_command:
        return python_command

    if entrypoints.get("go"):
        return "go run ."
    if entrypoints.get("rust"):
        return "cargo run"
    if entrypoints.get("make"):
        return "make run"

    return None


def next_steps_message(
    local_path: str | None,
    start_command: str | None,
    control_url: str | None = None,
) -> str:
    parts = ["**Next Steps**"]
    if local_path:
        quoted_path = shlex.quote(local_path)
        parts.extend([f"- Open the project: `cd {quoted_path}`", f"- Open it in VS Code: `code {quoted_path}`"])
    if start_command:
        parts.append(f"- Start command: `{start_command}`")
        parts.append("- Open the local URL printed by the command in your browser.")
    else:
        parts.append(
            "- Start command: not detected automatically. "
            "Check the README or manifest scripts in the local project folder."
        )
    if control_url:
        parts.append(f"- Sandbox console: {control_url}")
    return "\n".join(parts)


def setup_final_message(payload: dict[str, Any]) -> str:
    repo_name = payload.get("repo_name") or "repository"
    local_install = payload.get("local_install") if isinstance(payload.get("local_install"), dict) else {}
    sandbox = payload.get("sandbox") if isinstance(payload.get("sandbox"), dict) else {}
    sandbox_install = payload.get("sandbox_install") if isinstance(payload.get("sandbox_install"), dict) else {}
    sandbox_profile = payload.get("sandbox_repo_profile")
    local_profile = local_install.get("repo_profile") if isinstance(local_install, dict) else None

    manifests = []
    entrypoints = {}
    candidates = []
    if isinstance(local_profile, dict):
        manifests = local_profile.get("manifests") or []
        entrypoints = local_profile.get("entrypoints") or {}
    if isinstance(sandbox_profile, dict):
        candidates = sandbox_profile.get("readme_smoke_candidates") or []
        if not manifests:
            manifests = sandbox_profile.get("manifests") or []
        if not entrypoints:
            entrypoints = sandbox_profile.get("entrypoints") or {}

    local_path = local_install.get("repo_path") if isinstance(local_install, dict) else None
    start_command = detected_start_command(candidates, entrypoints, manifests)
    next_steps = next_steps_message(
        str(local_path) if local_path else None,
        start_command,
        sandbox.get("control_url"),
    )

    if not payload.get("ok"):
        return _failed_setup_message(
            payload,
            repo_name,
            sandbox,
            sandbox_install,
            local_install,
            manifests,
            candidates,
            next_steps,
        )

    return _successful_setup_message(
        payload,
        repo_name,
        sandbox,
        sandbox_install,
        local_install,
        manifests,
        candidates,
        entrypoints,
        next_steps,
    )


def _failed_setup_message(
    payload: dict[str, Any],
    repo_name: str,
    sandbox: dict[str, Any],
    sandbox_install: dict[str, Any],
    local_install: dict[str, Any],
    manifests: list[Any],
    candidates: list[Any],
    next_steps: str,
) -> str:
    sandbox_output = sandbox_output_text(sandbox_install)
    socket_failure = sandbox_socket_mcp_failure_summary(sandbox_output)
    install_failure = sandbox_install_failure_summary(sandbox_output)
    test_failure = sandbox_test_failure_summary(sandbox_output)
    error = payload.get("error") or local_install.get("error") or sandbox_install.get("error")
    parts = [
        f"**{repo_name} Setup Report**",
        "",
        "**Result**",
        "- Status: `[BLOCKED] Sandbox gate did not pass`",
        "- Local install: `skipped`",
        "",
        "**Sandbox**",
        f"- Sandbox ID: `{sandbox.get('sandbox_id')}`",
        f"- Sandbox path: `{payload.get('sandbox_repo_path')}`",
    ]
    if socket_failure:
        parts.extend(["", "**Blocking Failure**", f"- Socket MCP scan: {socket_failure}."])
    elif install_failure:
        parts.extend(["", "**Blocking Failure**", f"- Dependency install: {install_failure}."])
    elif test_failure:
        parts.extend(["", "**Blocking Failure**", f"- Test-file checks: {test_failure}."])
    elif error:
        parts.extend(["", "**Blocking Failure**", f"- Error: {error}."])
    else:
        parts.extend(
            [
                "",
                "**Blocking Failure**",
                "- The setup tool returned a failed result without a recovery question.",
            ]
        )

    parts.extend(["", "**Gate Evidence**", *_sandbox_gate_lines(sandbox_output)])
    if manifests:
        parts.append(f"- Manifests: {_inline_list(manifests)}")
    if candidates:
        parts.append(f"- Startup command from docs: `{candidates[0]}`")
    parts.extend(
        [
            "",
            "**Local Setup**",
            f"- Local path: `{local_install.get('repo_path')}`",
            "- Action taken: stopped instead of retrying the same setup step again.",
            "",
            next_steps,
        ]
    )
    return _render_parts(parts)


def _successful_setup_message(
    payload: dict[str, Any],
    repo_name: str,
    sandbox: dict[str, Any],
    sandbox_install: dict[str, Any],
    local_install: dict[str, Any],
    manifests: list[Any],
    candidates: list[Any],
    entrypoints: dict[str, Any],
    next_steps: str,
) -> str:
    sandbox_output = sandbox_output_text(sandbox_install)
    parts = [
        f"**{repo_name} Setup Report**",
        "",
        "**Result**",
        "- Status: `[PASS] Sandbox verified and local setup completed`",
        "- Safety model: unknown repo was checked in Solari before touching the local machine.",
        "",
        "**Sandbox Gate**",
        *_sandbox_gate_lines(sandbox_output),
        "",
        "**Sandbox**",
        f"- Sandbox ID: `{sandbox.get('sandbox_id')}`",
        f"- Sandbox path: `{payload.get('sandbox_repo_path')}`",
    ]
    if manifests:
        parts.append(f"- Manifests: {_inline_list(manifests)}")
    if candidates:
        parts.append(f"- Startup command from docs: `{candidates[0]}`")
    python_entrypoints = entrypoints.get("python") if isinstance(entrypoints, dict) else None
    if python_entrypoints:
        parts.append(f"- Python entrypoints: {_inline_list(python_entrypoints[:3])}")
    parts.extend(
        [
            "",
            "**Local Setup**",
            f"- Local path: `{local_install.get('repo_path')}`",
            "- Dependencies: installed after sandbox approval.",
            "",
            next_steps,
        ]
    )
    return _render_parts(parts)


def _sandbox_gate_lines(sandbox_output: str) -> list[str]:
    test_line = (
        "- Test-file checks: `[SKIPPED] no tests directory found`"
        if "NO_TEST_DIRECTORY " in sandbox_output
        else f"- Test-file checks: `{_gate_label(sandbox_output, 'REPO_TEST_STATUS')}`"
    )
    return [
        f"- Static security scan: `{_gate_label(sandbox_output, 'REPO_SECURITY_STATUS')}`",
        f"- Socket MCP dependency scan: `{_gate_label(sandbox_output, 'REPO_SOCKET_MCP_STATUS')}`",
        f"- Smoke run: `{_gate_label(sandbox_output, 'REPO_SMOKE_STATUS')}`",
        test_line,
        f"- Overall setup gate: `{_gate_label(sandbox_output, 'REPO_SETUP_STATUS')}`",
    ]


def _gate_label(sandbox_output: str, status_name: str) -> str:
    prefix = f"{status_name} "
    for line in reversed(sandbox_output.splitlines()):
        if not line.startswith(prefix):
            continue
        status = line.removeprefix(prefix).strip()
        if status == "0":
            return "PASS"
        return f"FAIL ({status})"
    return "UNKNOWN"


def _inline_list(values: list[Any], limit: int = 8) -> str:
    items = [f"`{value}`" for value in values[:limit]]
    if len(values) > limit:
        items.append(f"...and {len(values) - limit} more")
    return ", ".join(items)


def _render_parts(parts: list[str]) -> str:
    visible_parts = []
    previous_blank = False
    for part in parts:
        if _is_empty_optional_line(part):
            continue
        is_blank = part == ""
        if is_blank and previous_blank:
            continue
        visible_parts.append(part)
        previous_blank = is_blank
    return "\n".join(visible_parts).strip()


def _is_empty_optional_line(part: str) -> bool:
    return (
        part.endswith("None")
        or part.endswith("`None`")
        or part.endswith(": None")
        or part.endswith(": `None`")
    )
