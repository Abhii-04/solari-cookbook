from operator import add

from typing_extensions import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


def latest_value(_left: Any, right: Any) -> Any:
    return right


class State(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    next: Annotated[Any, latest_value]
    user_id: str
    task_instructions: str
    feedback_on_work: str
    internet_skill: str
    linkedin_skill: str
    setup_logs: Annotated[list[str], add]
