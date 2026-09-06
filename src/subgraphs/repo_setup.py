import json
import os
from operator import add
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from typing_extensions import Annotated, TypedDict

from src.middlewares.HITL import ask_question
from src.middlewares.context import compact_repo_setup_context
from src.middlewares.repo_setup_progress import emit_setup_progress
from src.nodes.local import install_missing_setup_tools
from src.nodes.sandbox_repo_clone import create_sandbox_clone_repo_and_install
from src.subgraphs.repo_setup_messages import (
    SETUP_TOOL_NAME,
    fallback_question_from_messages,
    latest_repo_url,
    latest_setup_payload,
    latest_tool_name,
)
from src.subgraphs.repo_setup_prompt import repo_setup_system_message
from src.subgraphs.repo_setup_summary import setup_final_message
from src.tools.read_skill import read_skill

load_dotenv(override=True)


class RepoSetupState(TypedDict, total=False):
    messages: Annotated[list[Any], add_messages]
    setup_logs: Annotated[list[str], add]


def _llm():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required")
    return ChatOpenAI(
        api_key=api_key,
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )


class RepoSetupWorkflow:
    """Builds the repository setup graph."""

    def __init__(self):
        self.tools = [
            read_skill,
            ask_question,
            install_missing_setup_tools,
            create_sandbox_clone_repo_and_install,
        ]
        self.agent = _llm().bind_tools(self.tools)
        self.graph = None
        self.checkpointer = InMemorySaver()

    def setup_agent(self, state: RepoSetupState):
        emit_setup_progress("Planning repository setup")
        response = self.agent.invoke([repo_setup_system_message()] + state["messages"])
        return {"messages": [response]}

    def route_after_agent(self, state: RepoSetupState):
        if getattr(state["messages"][-1], "tool_calls", None):
            return "tools"
        return END

    def fallback_gate(self, state: RepoSetupState):
        question = fallback_question_from_messages(state.get("messages", []))
        if not question:
            return {}

        response = interrupt({"question": question})
        return {
            "messages": [
                HumanMessage(content=f"User response to setup fallback question: {response}")
            ]
        }

    def route_after_tools(self, state: RepoSetupState):
        messages = state.get("messages", [])
        if fallback_question_from_messages(messages):
            return "fallback_gate"
        if latest_setup_payload(messages):
            return "finalize_setup"
        if latest_tool_name(messages) == "read_skill" and latest_repo_url(messages):
            return "start_setup"
        return "context_manager"

    async def start_setup(self, state: RepoSetupState):
        repo_url = latest_repo_url(state.get("messages", []))
        if not repo_url:
            return {"messages": [AIMessage(content="I need a GitHub repository URL before I can set it up.")]}

        emit_setup_progress("Starting deterministic sandbox setup", repo_url=repo_url)
        result = await create_sandbox_clone_repo_and_install.ainvoke(
            {
                "repo_url": repo_url,
                "install_on_user_device": True,
            }
        )
        return {
            "messages": [
                ToolMessage(
                    name=SETUP_TOOL_NAME,
                    tool_call_id="deterministic-repo-setup",
                    content=json.dumps(result),
                )
            ]
        }

    def finalize_setup(self, state: RepoSetupState):
        emit_setup_progress("Preparing final setup summary")
        payload = latest_setup_payload(state.get("messages", []))
        if not payload:
            return {"messages": [AIMessage(content="Repository setup finished.")]}
        return {"messages": [AIMessage(content=setup_final_message(payload))]}

    async def build_graph(self):
        graph_builder = StateGraph(RepoSetupState)
        graph_builder.add_node("repo_setup_agent", self.setup_agent)
        graph_builder.add_node("tools", ToolNode(self.tools))
        graph_builder.add_node("start_setup", self.start_setup)
        graph_builder.add_node("fallback_gate", self.fallback_gate)
        graph_builder.add_node("context_manager", compact_repo_setup_context)
        graph_builder.add_node("finalize_setup", self.finalize_setup)

        graph_builder.add_edge(START, "repo_setup_agent")
        graph_builder.add_conditional_edges(
            "repo_setup_agent",
            self.route_after_agent,
            {"tools": "tools", END: END},
        )
        graph_builder.add_conditional_edges(
            "tools",
            self.route_after_tools,
            self._post_tool_routes(),
        )
        graph_builder.add_conditional_edges(
            "start_setup",
            self.route_after_tools,
            self._post_tool_routes(),
        )
        graph_builder.add_edge("fallback_gate", "context_manager")
        graph_builder.add_edge("context_manager", "repo_setup_agent")
        graph_builder.add_edge("finalize_setup", END)
        self.graph = graph_builder.compile(checkpointer=self.checkpointer)

    def _post_tool_routes(self):
        return {
            "finalize_setup": "finalize_setup",
            "fallback_gate": "fallback_gate",
            "start_setup": "start_setup",
            "context_manager": "context_manager",
        }

    async def run(self, message: str, thread_id: str = "repo-setup"):
        if self.graph is None:
            await self.build_graph()
        return await self.graph.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config={"configurable": {"thread_id": thread_id}},
        )
