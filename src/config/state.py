from operator import add
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


def latest_value(_left: Any, right: Any) -> Any:
    return right


class State(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    next: Annotated[Any, latest_value]
    user_id: str
    task_instructions: str
    setup_logs: Annotated[list[str], add]
