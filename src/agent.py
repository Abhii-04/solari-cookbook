import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from src.config.state import State
from src.middlewares.repository_setup_logs import repo_setup_terminal_log
from src.middlewares.dynamic_agent_selector import dynamic_agent_router, dynamic_router
from src.middlewares.handle_tool_error import handle_tool_error
from src.middlewares.handoff import create_task_instructions_handoff_tool
from src.subgraphs.assistant import Assistant
from src.subgraphs.repo_setup import RepoSetupWorkflow

load_dotenv(override=True)

llm = ChatOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    model="deepseek-v4-flash",
    base_url="https://api.deepseek.com",
)


class Agent:
    def __init__(self):
        self.assistant_graph = None
        self.graph = None
        self.agent_id = None
        self.checkpointer = None
        self.store = None
        self.repo_setup_graph = None
        self.orchestrator_agent = None
        self.handoff_tools = []
        self.orchestrator_tools = []
        self.pending_interrupt = False
        self.printed_setup_log_count = 0

    async def setup(self):
        self.handoff_tools = [
            create_task_instructions_handoff_tool(
                agent_name="assistant",
                description=(
                    "Transfer work to the assistant with clear "
                    "task instructions and any relevant context."
                ),
            )
        ]
        self.orchestrator_tools = self.handoff_tools
        self.orchestrator_agent = llm.bind_tools(self.orchestrator_tools)

        assistant = Assistant()
        assistant.setup()
        await assistant.build_graph()
        self.assistant_graph = assistant.graph

        repo_setup = RepoSetupWorkflow()
        await repo_setup.build_graph()
        self.repo_setup_graph = repo_setup.graph

        self.checkpointer = InMemorySaver()
        self.store = InMemoryStore()
        await self.build_graph()

    def orchestrator(self, state: State, store: BaseStore) -> dict[str, Any]:
        _ = store
        system_message = SystemMessage(
            content="""
            You are the orchestrator. Call transfer_to_assistant with concise task instructions and any relevant context from the conversation.
            The Gmail, LinkedIn, and internet agents are not available in this repo.
            Transfer Solari sandbox, sandbox creation/session/environment/runtime, isolated code execution, dev container, ephemeral compute, or sandbox setup tasks to assistant.
            Transfer general reasoning, writing, editing, planning, summaries, and context-only help to assistant.
            When unsure, transfer to assistant.
            """
        )

        response = self.orchestrator_agent.invoke([system_message] + state["messages"])

        if getattr(response, "tool_calls", None):
            return {"messages": [response], "next": "orchestrator_tools"}

        if isinstance(state["messages"][-1], ToolMessage):
            return {"messages": [response], "next": END}

        route = response.content.strip().lower()

        if route not in ("assistant",):
            route = "assistant"

        return {"next": route}

    def orchestrator_router(self, state: State):
        route = state.get("next")
        if route == "orchestrator_tools":
            return route
        if route in {"assistant", "repo_setup"}:
            return route
        return END

    async def build_graph(self):
        graph_builder = StateGraph(State)
        graph_builder.add_node("orchestrator", self.orchestrator)
        graph_builder.add_node(
            "orchestrator_tools",
            ToolNode(self.orchestrator_tools, handle_tool_errors=handle_tool_error),
        )
        graph_builder.add_node("assistant", self.assistant_graph)
        graph_builder.add_node("repo_setup", self.repo_setup_graph)
        graph_builder.add_node("router", dynamic_agent_router)

        graph_builder.add_edge(START, "router")
        graph_builder.add_conditional_edges(
            "router",
            dynamic_router,
            {
                "orchestrator": "orchestrator",
                "assistant": "assistant",
                "repo_setup": "repo_setup",
                END: END,
            }
        )
        graph_builder.add_conditional_edges(
            "orchestrator",
            self.orchestrator_router,
            {
                "assistant": "assistant",
                "repo_setup": "repo_setup",
                "orchestrator_tools": "orchestrator_tools",
                END: END,
            },
        )
        graph_builder.add_edge("orchestrator_tools", "orchestrator")
        graph_builder.add_edge("assistant", END)
        graph_builder.add_edge("repo_setup", END)

        self.graph = graph_builder.compile(
            checkpointer=self.checkpointer,
            store=self.store,
        )

    async def close(self):
        pass

    def _thread_config(self) -> dict[str, Any]:
        return {"configurable": {"thread_id": self.agent_id or "default"}}

    def _resume_value(self, message: str) -> dict[str, Any] | str:
        normalized = message.strip().lower()
        if normalized in {"approve", "approved", "yes", "y", "allow", "ok", "okay"}:
            return {"approved": True, "response": message}
        if normalized in {"reject", "rejected", "no", "n", "deny", "cancel"}:
            return {"approved": False, "response": message}
        return message

    def _interrupt_question(self, result: dict[str, Any]) -> str | None:
        interrupts = result.get("__interrupt__") or []
        if not interrupts:
            return None

        return self._question_from_interrupt(interrupts[0])

    def _question_from_interrupt(self, interrupt: Any) -> str:
        value = getattr(interrupt, "value", interrupt)
        if isinstance(value, dict):
            if "question" in value:
                return str(value["question"])
            if len(value) == 1:
                return str(next(iter(value.values())))
            return str(value)
        return str(value)

    def _snapshot_interrupts(self, snapshot: Any) -> list[Any]:
        interrupts = list(getattr(snapshot, "interrupts", ()) or ())
        for task in getattr(snapshot, "tasks", ()) or ():
            interrupts.extend(getattr(task, "interrupts", ()) or ())
            task_state = getattr(task, "state", None)
            if task_state is not None:
                interrupts.extend(self._snapshot_interrupts(task_state))
        return interrupts

    async def _pending_interrupt_question(self, config: dict[str, Any]) -> str | None:
        if self.graph is None:
            return None

        try:
            snapshot = await self.graph.aget_state(config, subgraphs=True)
        except Exception:
            return None

        interrupts = self._snapshot_interrupts(snapshot)
        if not interrupts:
            return None
        return self._question_from_interrupt(interrupts[0])

    def _print_result(self, result: dict[str, Any], pending_question: str | None = None) -> None:
        setup_logs = result.get("setup_logs", []) or []
        for setup_log in setup_logs[self.printed_setup_log_count:]:
            print(setup_log)
        self.printed_setup_log_count = len(setup_logs)

        sandbox_log = repo_setup_terminal_log(result.get("messages", []))
        if sandbox_log:
            print(sandbox_log)

        question = self._interrupt_question(result) or pending_question
        if question:
            self.pending_interrupt = True
            print(f"Agent needs input: {question}")
            return

        self.pending_interrupt = False
        messages = result.get("messages", [])
        if messages:
            print(messages[-1].content)

    def _print_progress(self, event: Any) -> None:
        if not isinstance(event, dict):
            return
        if event.get("type") != "repo_setup_progress":
            return

        message = event.get("message")
        if not message:
            return

        details = []
        if event.get("elapsed_seconds") is not None:
            details.append(f"{event['elapsed_seconds']}s")
        if event.get("dependency_count") is not None:
            details.append(f"{event['dependency_count']} deps")
        if event.get("status") is not None:
            details.append(f"status={event['status']}")
        if event.get("local_path"):
            details.append(str(event["local_path"]))

        suffix = f" ({', '.join(details)})" if details else ""
        print(f"[repo-setup] {message}{suffix}")

    async def _run_graph(self, graph_input: Any, config: dict[str, Any]) -> dict[str, Any]:
        if not hasattr(self.graph, "astream"):
            return await self.graph.ainvoke(graph_input, config=config)

        latest_result: dict[str, Any] = {}
        async for item in self.graph.astream(
            graph_input,
            config=config,
            stream_mode=["custom", "values"],
            subgraphs=True,
        ):
            namespace = ()
            if isinstance(item, tuple) and len(item) == 3:
                namespace, mode, payload = item
            else:
                mode, payload = None, item

            if mode == "custom":
                self._print_progress(payload)
            elif mode == "values" and namespace == () and isinstance(payload, dict):
                latest_result = payload

        if latest_result:
            return latest_result

        snapshot = await self.graph.aget_state(config, subgraphs=False)
        values = getattr(snapshot, "values", None)
        return values if isinstance(values, dict) else {}

    async def run_superstep(self, message, history, user_id: str = "default"):
        _ = history
        config = self._thread_config()
        pending_question = await self._pending_interrupt_question(config)

        if self.pending_interrupt or pending_question:
            print("[agent] Resuming paused workflow")
            result = await self._run_graph(
                Command(resume=self._resume_value(message)),
                config=config,
            )
        else:
            print("[agent] Starting request")
            state = {
                "messages": [HumanMessage(content=message)],
                "user_id": user_id,
            }
            result = await self._run_graph(state, config=config)

        pending_question = await self._pending_interrupt_question(config)
        self._print_result(result, pending_question=pending_question)
        return result
