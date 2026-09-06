import json
from typing import Any


def status_word(status: str | None) -> str:
    return "passed" if status == "0" else "failed"


def sandbox_repo_profile(sandbox_output: str) -> dict[str, Any] | None:
    profiles = []
    in_profile = False
    payload_lines = []
    for line in sandbox_output.splitlines():
        if line == "REPO_PROFILE_JSON_BEGIN":
            in_profile = True
            payload_lines = []
            continue
        if line == "REPO_PROFILE_JSON_END" and in_profile:
            in_profile = False
            try:
                profile = json.loads("\n".join(payload_lines))
            except json.JSONDecodeError:
                continue
            if isinstance(profile, dict):
                profiles.append(profile)
            continue
        if in_profile:
            payload_lines.append(line)

    return profiles[-1] if profiles else None


def sandbox_progress_events(sandbox_output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    socket_package_count: str | None = None
    manifests: list[str] = []
    in_manifests = False

    for line in sandbox_output.splitlines():
        if line == "MANIFESTS_FOUND_BEGIN":
            in_manifests = True
            manifests = []
            continue
        if line == "MANIFESTS_FOUND_END":
            in_manifests = False
            events.append(
                {
                    "message": (
                        "Repository manifests discovered: "
                        f"{', '.join(manifests) if manifests else 'none'}"
                    ),
                    "manifests": manifests,
                }
            )
            continue
        if in_manifests:
            manifests.append(line)
            continue

        if line.startswith("REPO_SECURITY_STATUS "):
            status = line.rsplit(" ", 1)[-1]
            events.append({"message": f"Static security scan {status_word(status)}", "status": int(status)})
        elif line.startswith("SOCKET_MCP_PACKAGE_COUNT "):
            socket_package_count = line.rsplit(" ", 1)[-1]
            events.append(
                {
                    "message": f"Socket MCP is checking {socket_package_count} dependencies",
                    "dependency_count": int(socket_package_count),
                }
            )
        elif line.startswith("SOCKET_MCP_NODE_MAJOR "):
            node_major = line.rsplit(" ", 1)[-1]
            events.append(
                {
                    "message": f"Socket MCP runtime is using Node {node_major}",
                    "node_major": None if node_major == "None" else int(node_major),
                }
            )
        elif line.startswith("REPO_SOCKET_MCP_STATUS "):
            status = line.rsplit(" ", 1)[-1]
            package_note = (
                f" for {socket_package_count} dependencies"
                if socket_package_count is not None
                else ""
            )
            events.append(
                {
                    "message": f"Socket MCP dependency scan {status_word(status)}{package_note}",
                    "status": int(status),
                }
            )
        elif line.startswith("INSTALL_BEGIN "):
            events.append({"message": "Installing repository dependencies", "path": line.split(" ", 1)[1]})
        elif line.startswith("INSTALL_END "):
            path, status = line.removeprefix("INSTALL_END ").rsplit(" ", 1)
            events.append({"message": f"Dependency install {status_word(status)}", "path": path, "status": int(status)})
        elif line.startswith("SMOKE_BEGIN "):
            events.append({"message": "Running sandbox smoke check", "path": line.split(" ", 1)[1]})
        elif line.startswith("REPO_SMOKE_STATUS "):
            status = line.rsplit(" ", 1)[-1]
            events.append({"message": f"Sandbox smoke check {status_word(status)}", "status": int(status)})
        elif line.startswith("NO_TEST_DIRECTORY "):
            events.append({"message": "No tests directory found in sandbox", "path": line.split(" ", 1)[1]})
        elif line.startswith("TEST_CHECK_BEGIN "):
            events.append({"message": "Checking files in tests directory", "path": line.split(" ", 1)[1]})
        elif line.startswith("REPO_TEST_STATUS "):
            status = line.rsplit(" ", 1)[-1]
            events.append({"message": f"Sandbox test-file checks {status_word(status)}", "status": int(status)})
        elif line.startswith("REPO_SETUP_STATUS "):
            status = line.rsplit(" ", 1)[-1]
            events.append({"message": f"Sandbox setup gate {status_word(status)}", "status": int(status)})

    return events


def sandbox_install_failure_summary(sandbox_output: str) -> str | None:
    lines = sandbox_output.splitlines()
    if not any(line.startswith("INSTALL_END ") and not line.endswith(" 0") for line in lines):
        return None

    interesting_prefixes = (
        "$ ",
        "EXIT ",
        "INSTALL_END ",
        "INSTALL_RETRY ",
        "MISSING_TOOL ",
        "SKIP ",
        "ERROR:",
        "error:",
        "ModuleNotFoundError",
        "Traceback",
    )
    interesting = [line.strip() for line in lines if line.startswith(interesting_prefixes)]
    return " | ".join(interesting[-12:]) if interesting else "INSTALL_END reported a non-zero status."


def sandbox_socket_mcp_failure_summary(sandbox_output: str) -> str | None:
    lines = sandbox_output.splitlines()
    if not any(line.startswith("REPO_SOCKET_MCP_STATUS ") and not line.endswith(" 0") for line in lines):
        return None

    interesting_prefixes = (
        "$ ",
        "EXIT ",
        "MISSING_TOOL ",
        "ENV_HINT ",
        "SOCKET_MCP_",
        "Traceback",
        "ModuleNotFoundError",
        "ImportError",
        "RuntimeError",
        "Exception",
    )
    interesting = [
        line.strip()
        for line in lines
        if line.startswith(interesting_prefixes)
        or "Socket authentication failed" in line
        or "Unauthorized" in line
    ]
    return " | ".join(interesting[-12:]) if interesting else "REPO_SOCKET_MCP_STATUS reported a non-zero status."


def sandbox_test_failure_summary(sandbox_output: str) -> str | None:
    lines = sandbox_output.splitlines()
    if not any(line.startswith("REPO_TEST_STATUS ") and not line.endswith(" 0") for line in lines):
        return None

    interesting_prefixes = (
        "$ ",
        "EXIT ",
        "TEST_CHECK_BEGIN ",
        "TEST_CHECK_STATUS ",
        "TEST_CHECK_END ",
        "NO_TEST_FILES_FOUND",
        "FAILED",
        "ERROR",
        "Error:",
        "AssertionError",
        "Traceback",
    )
    interesting = [
        line.strip()
        for line in lines
        if line.startswith(interesting_prefixes) or " failed" in line.lower()
    ]
    return " | ".join(interesting[-12:]) if interesting else "REPO_TEST_STATUS reported a non-zero status."


def fallback_questions(sandbox_output: str, local_install: dict[str, Any]) -> list[str]:
    questions = []
    missing_tools = sorted(
        {
            line.split(" ", 1)[1].strip()
            for line in sandbox_output.splitlines()
            if line.startswith("MISSING_TOOL ") and line.split(" ", 1)[1].strip()
        }
    )
    if missing_tools:
        questions.append(
            "The setup needs these tools but could not find or bootstrap them: "
            f"{', '.join(missing_tools)}. May I install the missing tools on your local machine, "
            "or would you rather provide a different install/start command?"
        )

    local_missing = local_install.get("missing_tools") if isinstance(local_install, dict) else None
    if local_missing:
        questions.append(
            "The sandbox checks passed, but your local machine is missing these setup tools: "
            f"{', '.join(sorted(local_missing))}. May I install them locally so setup can finish?"
        )

    if "ENV_HINT " in sandbox_output or "API_KEY" in sandbox_output or "PASSWORD" in sandbox_output:
        questions.append(
            "The repo appears to need credentials or environment variables. Please provide the needed values, "
            "or tell me to skip credential-dependent startup steps."
        )

    socket_failure = sandbox_socket_mcp_failure_summary(sandbox_output)
    if socket_failure:
        questions.append(
            "The Socket MCP dependency scan failed inside the secure sandbox. "
            f"Last Socket details: {socket_failure}"
        )

    install_failure = sandbox_install_failure_summary(sandbox_output)
    if install_failure:
        questions.append(
            "The dependency install inside the secure sandbox failed after automatic retries. "
            f"Last install details: {install_failure}"
        )

    test_failure = sandbox_test_failure_summary(sandbox_output)
    if test_failure:
        questions.append(
            "The repository tests failed inside the secure sandbox. "
            f"Last test details: {test_failure}"
        )

    if "NO_SMOKE_COMMAND_FOUND" in sandbox_output:
        questions.append(
            "I could not confirm a runnable startup command from the discovered files. What command should I use to start or smoke-run this repo?"
        )

    if "NO_TEST_FILES_FOUND" in sandbox_output:
        questions.append(
            "The repo has a tests folder, but I could not find any recognizable test files inside it. Please confirm whether the tests folder is correct."
        )

    return questions
