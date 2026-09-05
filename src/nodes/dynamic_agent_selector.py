from langchain_core.messages import HumanMessage

from src.config.state import State

REPO_SETUP_TEXT = ["github.com/", "git@github.com:", "clone","repo","repository","install", "setup", "set up", "sandbox",]
ASSISTANT_TEXT = ["solari", "sandbox", "desktop", "browser", "code", "bash"]
SANDBOX_CONTEXT_MARKERS = ["solari_sandbox","sandbox_id","control_url","sandbox_code_execution","getsolari.com",]
SANDBOX_FOLLOW_UP_TEXT = ["cat","clone","content","file", "find", "grep","inspect","list", "ls", "open", "read", "readme", "repo","repository","run","show", "test",]
LOCAL_PROJECT_TEXT = ["local", "project","workspace", "this repo", "ultron","src/", "main.py","pyproject.toml",]


def _message_content(message) -> str:
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(getattr(message, "content", ""))


def _last_user_text(state: State) -> str:
    messages = state.get("messages", [])

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _message_content(message).lower()

        if getattr(message, "type", None) == "human":
            return _message_content(message).lower()

        if isinstance(message, dict) and message.get("role") in {"user", "human"}:
            return _message_content(message).lower()

    if messages:
        last = messages[-1]
        return _message_content(last).lower()

    return ""


def _has_sandbox_context(state: State) -> bool:
    for message in state.get("messages", [])[:-1]:
        name = str(getattr(message, "name", "")).lower()
        content = _message_content(message).lower()
        if any(marker in name or marker in content for marker in SANDBOX_CONTEXT_MARKERS):
            return True
    return False


def _is_sandbox_follow_up(user_text: str) -> bool:
    if any(word in user_text for word in LOCAL_PROJECT_TEXT):
        return False
    return any(word in user_text for word in SANDBOX_FOLLOW_UP_TEXT)


def dynamic_agent_router(state: State):
    """select agent based on task given by user."""
    user_text = _last_user_text(state)
    if (
        ("github.com/" in user_text or "git@github.com:" in user_text)
        and any(word in user_text for word in REPO_SETUP_TEXT)
    ):
        return {"next": "repo_setup"}
    if any(word in user_text for word in ASSISTANT_TEXT):
        return {"next": "assistant"}
    if _has_sandbox_context(state) and _is_sandbox_follow_up(user_text):
        return {"next": "assistant"}
    return {"next": "orchestrator"}


def dynamic_router(state: State):
    route = state.get("next")
    if route in {"orchestrator", "assistant", "repo_setup"}:
        return route
    return "orchestrator"
