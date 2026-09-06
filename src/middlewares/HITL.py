from langchain_core.tools import tool
from langgraph.types import interrupt


#Use this HITL for clarification purpose only, keep the other one for security purpose
@tool
def ask_question(question:str):
    """Ask the human one concise clarification question."""
    response = interrupt({question:question})
    return{
        "user`s response":response
    }
