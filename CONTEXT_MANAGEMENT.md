# Handling Overgrown Context

This repo handles overgrown conversation context mainly in the repository setup workflow. The setup flow can produce very large tool payloads: repository profiles, manifest excerpts, README excerpts, sandbox installation output, security scan output, smoke-run logs, and fallback questions.

Instead of keeping every bulky tool exchange in the model context forever, the graph replaces selected tool messages with one rolling summary and stores the raw sandbox logs separately for terminal output.

## Where It Lives

The main implementation is in:

- `src/middlewares/context.py`
- `src/subgraphs/repo_setup.py`
- `src/config/state.py`
- `src/agent.py`

## The Compaction Target

Only repo-setup tool messages that tend to grow large are compacted:

```python
COMPACT_TOOL_NAMES = {
    "read_skill",
    "ask_question",
    "install_missing_setup_tools",
    "create_sandbox_clone_repo_and_install",
}
SUMMARY_MESSAGE_ID = "repo-setup-context-summary"
MAX_SUMMARY_CHARS = 6000
```

This keeps normal conversation intact while targeting the expensive setup messages.

## Structured Summaries Instead Of Raw Payloads

The context middleware parses JSON tool payloads when possible:

```python
def _json_payload(message: ToolMessage) -> Any:
    if not isinstance(message.content, str):
        return message.content
    try:
        return json.loads(message.content)
    except json.JSONDecodeError:
        return None
```

For the setup tool, the repo profile is reduced to the parts the model needs for later reasoning: manifests, file samples, docs, manifest excerpts, README smoke candidates, and entrypoints.

```python
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

    return "\n".join(parts)
```

The full implementation adds docs, manifest excerpts, startup candidates, and entrypoints as well. The important pattern is that it keeps decision evidence, not the whole payload.

## Keeping Only Useful Log Lines

Sandbox setup output can be very noisy. The compactor keeps the last 80 status-style lines with known prefixes:

```python
def _status_lines(text: str) -> list[str]:
    prefixes = (
        "REPO_",
        "SECURITY_SCAN_END",
        "SOCKET_MCP_",
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
```

This lets the model remember what happened without carrying every install log line.

## Removing Bulky Messages

The core function walks the current graph state, summarizes selected tool messages, and schedules those original messages for removal:

```python
def compact_repo_setup_context(state: dict[str, Any]) -> dict[str, Any]:
    """Replace bulky repo setup tool exchanges with one rolling summary."""
    messages = state.get("messages", [])
    summaries = []
    setup_logs = []
    compacted_tool_call_ids = set()
    removals = []

    for message in messages:
        if not isinstance(message, ToolMessage) or message.name not in COMPACT_TOOL_NAMES:
            continue

        summary = _summarize_tool_message(message)
        if summary:
            summaries.append(f"- {message.name}:\n{summary}")

        if message.id:
            removals.append(RemoveMessage(id=message.id))
        if message.tool_call_id:
            compacted_tool_call_ids.add(message.tool_call_id)
```

It also removes the matching AI tool-call messages. That matters because LangGraph/OpenAI-style tool calls usually come as a pair: an assistant message asks for a tool, then a tool message returns the result. Removing only the tool response would leave dangling tool-call context.

```python
for message in messages:
    if not isinstance(message, AIMessage) or not message.id:
        continue
    if _tool_call_ids(message) & compacted_tool_call_ids:
        removals.append(RemoveMessage(id=message.id))
```

## Rolling Summary Message

The summaries are collapsed into a synthetic human message with a stable id:

```python
summary_text = "Repo setup context summary:\n" + "\n\n".join(summaries[-12:])
if len(summary_text) > MAX_SUMMARY_CHARS:
    summary_text = summary_text[-MAX_SUMMARY_CHARS:]

summary_message = HumanMessage(
    id=SUMMARY_MESSAGE_ID,
    content=summary_text,
)

result: dict[str, Any] = {"messages": removals + [summary_message]}
```

Two limits prevent summary growth:

- only the latest 12 compacted summaries are included
- the final text is capped at 6000 characters

Earlier summary messages with the same `SUMMARY_MESSAGE_ID` are read back in before the new summary is created, so the compactor can roll forward previous context without preserving all original messages.

## Separating Human-Visible Logs From Model Context

Raw sandbox logs are still useful to the user, but they do not need to stay in the model context. The compactor extracts up to the latest three setup logs into a separate state field:

```python
if setup_logs:
    result["setup_logs"] = setup_logs[-3:]
```

That state field is defined with an additive reducer:

```python
class State(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    next: Annotated[Any, latest_value]
    user_id: str
    task_instructions: str
    setup_logs: Annotated[list[str], add]
```

The top-level agent prints those logs separately:

```python
def _print_result(self, result: dict[str, Any], pending_question: str | None = None) -> None:
    setup_logs = result.get("setup_logs", []) or []
    for setup_log in setup_logs[self.printed_setup_log_count:]:
        print(setup_log)
    self.printed_setup_log_count = len(setup_logs)
```

This gives the user full operational visibility while keeping the model's future context smaller.

## Where The Graph Uses It

The repo setup graph registers the compactor as a node named `context_manager`:

```python
graph_builder.add_node("context_manager", compact_repo_setup_context)
```

After tools run, the graph routes through this node when it does not need to finalize or ask a fallback question:

```python
def route_after_tools(self, state: RepoSetupState):
    messages = state.get("messages", [])
    if fallback_question_from_messages(messages):
        return "fallback_gate"
    if latest_setup_payload(messages):
        return "finalize_setup"
    if latest_tool_name(messages) == "read_skill" and latest_repo_url(messages):
        return "start_setup"
    return "context_manager"
```

The graph then loops back to the setup agent with the compacted context:

```python
graph_builder.add_edge("context_manager", "repo_setup_agent")
```

## Net Effect

The repo handles overgrown context with four practical moves:

1. Summarize only the bulky setup tools.
2. Preserve decision evidence such as manifests, docs, entrypoints, command candidates, statuses, and fallback questions.
3. Remove the original bulky tool messages and matching AI tool-call messages.
4. Keep raw sandbox logs outside model context, in `setup_logs`, so they can still be printed for the user.

That gives the next model turn enough memory to reason correctly without dragging the entire setup transcript forward.
