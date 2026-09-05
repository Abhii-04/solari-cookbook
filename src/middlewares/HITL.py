from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def ask_question(question: str):
    """Ask the human one concise clarification question."""
    response = interrupt({"question": question})
    return {"user_response": response}
