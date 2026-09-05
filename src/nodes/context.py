import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from src.nodes.script import sandbox_output_text

COMPACT_TOOL_NAMES = {
    "read_skill",
    "ask_question",
    "install_missing_setup_tools",
    "create_sandbox_clone_repo_and_install",
}
SUMMARY_MESSAGE_ID = "repo-setup-context-summary"
MAX_SUMMARY_CHARS = 6000


def _json_payload(message: ToolMessage) -> Any:
    if not isinstance(message.content, str):
        return message.content
    try:
        return json.loads(message.content)
    except json.JSONDecodeError:
        return None


def _status_lines(text: str) -> list[str]:
    prefixes = (
        "REPO_",
        "SECURITY_SCAN_END",
        "MANIFESTS_FOUND_BEGIN",
        "MANIFESTS_FOUND_END",
        "INSTALL_BEGIN",
        "INSTALL_END",
        "MISSING_TOOL",
        "ENV_HINT",
        "NO_SMOKE_COMMAND_FOUND",
        "DOCS_READ",
        "RUN_CANDIDATE",
        "SMOKE_COMMAND_STATUS",
    )
    lines = [line for line in text.splitlines() if line.startswith(prefixes)]
    return lines[-80:]


def _setup_log_from_payload(payload: dict[str, Any]) -> str | None:
    sandbox_install = payload.get("sandbox_install")
    if not isinstance(sandbox_install, dict):
        return None

    sandbox_text = sandbox_output_text(sandbox_install).strip()
    sandbox_error = sandbox_install.get("error")
    if not sandbox_text and not sandbox_error:
        return None

    section = ["\n=== Sandbox operations log ==="]
    if sandbox_text:
        section.append(sandbox_text)
    if sandbox_error:
        section.append(f"SANDBOX_ERROR {sandbox_error}")
    section.append("=== End sandbox operations log ===\n")
    return "\n".join(section)


def _summarize_repo_profile(label: str, profile: dict[str, Any]) -> str:
    parts = [f"{label}_profile:"]
    manifests = profile.get("manifests")
    if manifests:
        parts.append(f"manifests={manifests}")

    files = profile.get("files")
    if isinstance(files, dict):
        shown = files.get("shown") if isinstance(files.get("shown"), list) else []
        parts.append(
            "files="
            f"total={files.get('total')} "
            f"sample={shown[:30]} "
            f"truncated={files.get('truncated')}"
        )

    docs = profile.get("docs")
    if isinstance(docs, list):
        doc_paths = [doc.get("path") for doc in docs if isinstance(doc, dict) and doc.get("path")]
        if doc_paths:
            parts.append(f"docs={doc_paths}")
        excerpts = []
        for doc in docs[:2]:
            if not isinstance(doc, dict) or not doc.get("content"):
                continue
            content = str(doc["content"]).strip().replace("\n", " ")
            excerpts.append(f"{doc.get('path')}: {content[:1000]}")
        if excerpts:
            parts.append("doc_excerpts=" + repr(excerpts))

    manifest_contents = profile.get("manifest_contents")
    if isinstance(manifest_contents, list):
        excerpts = []
        for manifest in manifest_contents[:4]:
            if not isinstance(manifest, dict) or not manifest.get("content"):
                continue
            content = str(manifest["content"]).strip().replace("\n", " ")
            excerpts.append(f"{manifest.get('path')}: {content[:700]}")
        if excerpts:
            parts.append("manifest_excerpts=" + repr(excerpts))

    candidates = profile.get("readme_smoke_candidates")
    if candidates:
        parts.append(f"readme_smoke_candidates={candidates}")

    entrypoints = profile.get("entrypoints")
    if isinstance(entrypoints, dict):
        parts.append(f"entrypoints={entrypoints}")

    return "\n".join(parts)


def _summarize_setup_payload(payload: dict[str, Any]) -> str:
    parts = [
        f"repo_url={payload.get('repo_url')}",
        f"repo_name={payload.get('repo_name')}",
        f"ok={payload.get('ok')}",
    ]

    sandbox = payload.get("sandbox")
    if isinstance(sandbox, dict):
        parts.append(f"sandbox_id={sandbox.get('sandbox_id')}")
        parts.append(f"control_url={sandbox.get('control_url')}")

    parts.append(f"sandbox_repo_path={payload.get('sandbox_repo_path')}")

    sandbox_profile = payload.get("sandbox_repo_profile")
    if isinstance(sandbox_profile, dict):
        parts.append(_summarize_repo_profile("sandbox", sandbox_profile))

    local_install = payload.get("local_install")
    if isinstance(local_install, dict):
        parts.append(f"local_ok={local_install.get('ok')}")
        parts.append(f"local_path={local_install.get('repo_path')}")
        missing_tools = local_install.get("missing_tools")
        if missing_tools:
            parts.append(f"local_missing_tools={missing_tools}")
        local_profile = local_install.get("repo_profile")
        if isinstance(local_profile, dict):
            parts.append(_summarize_repo_profile("local", local_profile))

    fallback_questions = payload.get("fallback_questions")
    if fallback_questions:
        parts.append(f"pending_fallback={fallback_questions[0]}")

    sandbox_install = payload.get("sandbox_install")
    if isinstance(sandbox_install, dict):
        sandbox_text = sandbox_output_text(sandbox_install)
        status_lines = _status_lines(sandbox_text)
        if status_lines:
            parts.append("sandbox_status:\n" + "\n".join(status_lines))
        if sandbox_install.get("error"):
            parts.append(f"sandbox_error={sandbox_install.get('error')}")

    return "\n".join(str(part) for part in parts if part is not None)


def _summarize_tool_message(message: ToolMessage) -> str | None:
    payload = _json_payload(message)

    if message.name == "create_sandbox_clone_repo_and_install" and isinstance(payload, dict):
        return _summarize_setup_payload(payload)

    if message.name == "read_skill":
        return "read_skill completed; repo startup discovery instructions were loaded."

    if message.name == "ask_question":
        return f"ask_question result={payload if payload is not None else message.content}"

    if message.name == "install_missing_setup_tools":
        return f"install_missing_setup_tools result={payload if payload is not None else message.content}"

    return None


def _tool_call_ids(message: AIMessage) -> set[str]:
    ids = set()
    for tool_call in getattr(message, "tool_calls", None) or []:
        if tool_call.get("name") in COMPACT_TOOL_NAMES and tool_call.get("id"):
            ids.add(tool_call["id"])
    return ids


def compact_repo_setup_context(state: dict[str, Any]) -> dict[str, Any]:
    """Replace bulky repo setup tool exchanges with one rolling summary."""
    messages = state.get("messages", [])
    summaries = []
    setup_logs = []
    compacted_tool_call_ids = set()
    removals = []

    for message in messages:
        if isinstance(message, HumanMessage) and message.id == SUMMARY_MESSAGE_ID:
            summaries.append(message.content)

    for message in messages:
        if not isinstance(message, ToolMessage) or message.name not in COMPACT_TOOL_NAMES:
            continue

        summary = _summarize_tool_message(message)
        if summary:
            summaries.append(f"- {message.name}:\n{summary}")

        payload = _json_payload(message)
        if message.name == "create_sandbox_clone_repo_and_install" and isinstance(payload, dict):
            setup_log = _setup_log_from_payload(payload)
            if setup_log:
                setup_logs.append(setup_log)

        if message.id:
            removals.append(RemoveMessage(id=message.id))
        if message.tool_call_id:
            compacted_tool_call_ids.add(message.tool_call_id)

    if not summaries:
        return {}

    for message in messages:
        if not isinstance(message, AIMessage) or not message.id:
            continue
        if _tool_call_ids(message) & compacted_tool_call_ids:
            removals.append(RemoveMessage(id=message.id))

    summary_text = "Repo setup context summary:\n" + "\n\n".join(summaries[-12:])
    if len(summary_text) > MAX_SUMMARY_CHARS:
        summary_text = summary_text[-MAX_SUMMARY_CHARS:]

    summary_message = HumanMessage(
        id=SUMMARY_MESSAGE_ID,
        content=summary_text,
    )

    result: dict[str, Any] = {"messages": removals + [summary_message]}
    if setup_logs:
        result["setup_logs"] = setup_logs[-3:]
    return result
