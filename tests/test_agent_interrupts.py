import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langgraph.types import Command, Interrupt

from src.agent import Agent


class FakeInterruptGraph:
    def __init__(self):
        self.calls = []
        self.pending_interrupt = None

    async def ainvoke(self, state, config=None):
        self.calls.append((state, config))
        if isinstance(state, Command):
            self.pending_interrupt = None
            return {"messages": [AIMessage(content="resumed")]}
        self.pending_interrupt = Interrupt(value={"question": "Approve?"}, id="interrupt-1")
        return {"__interrupt__": [self.pending_interrupt]}

    async def aget_state(self, config, subgraphs=False):
        _ = config, subgraphs

        class Snapshot:
            def __init__(self, interrupt):
                self.interrupts = [interrupt] if interrupt else []
                self.tasks = []

        return Snapshot(self.pending_interrupt)


class AgentInterruptTests(unittest.TestCase):
    def test_resume_value_treats_approved_as_approval_payload(self):
        agent = Agent()

        self.assertEqual(
            agent._resume_value("approved"),
            {"approved": True, "response": "approved"},
        )
        self.assertEqual(
            agent._resume_value("no"),
            {"approved": False, "response": "no"},
        )
        self.assertEqual(agent._resume_value("MY_API_KEY=abc"), "MY_API_KEY=abc")

    def test_interrupt_question_extracts_question_payload(self):
        agent = Agent()
        result = {
            "__interrupt__": [
                Interrupt(value={"question": "May I install pnpm?"}, id="interrupt-1")
            ]
        }

        self.assertEqual(agent._interrupt_question(result), "May I install pnpm?")

    def test_print_result_marks_pending_interrupt_and_prints_question(self):
        agent = Agent()
        result = {
            "__interrupt__": [
                Interrupt(value={"question": "May I install pnpm?"}, id="interrupt-1")
            ]
        }

        with patch("builtins.print") as mocked_print:
            agent._print_result(result)

        self.assertTrue(agent.pending_interrupt)
        mocked_print.assert_called_with("Agent needs input: May I install pnpm?")

    def test_print_result_prints_new_setup_logs_once(self):
        agent = Agent()

        with patch("builtins.print") as mocked_print:
            agent._print_result({"setup_logs": ["log one"], "messages": []})
            agent._print_result({"setup_logs": ["log one", "log two"], "messages": []})

        mocked_print.assert_any_call("log one")
        mocked_print.assert_any_call("log two")
        self.assertEqual(mocked_print.call_count, 2)


class AgentRunSuperstepInterruptTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_superstep_resumes_pending_interrupt(self):
        agent = Agent()
        agent.graph = FakeInterruptGraph()

        with patch("builtins.print"):
            await agent.run_superstep("start", [])
            await agent.run_superstep("approved", [])

        resume_call = agent.graph.calls[1][0]
        self.assertIsInstance(resume_call, Command)
        self.assertEqual(resume_call.resume, {"approved": True, "response": "approved"})
        self.assertFalse(agent.pending_interrupt)

    async def test_run_superstep_uses_checkpoint_interrupt_when_local_flag_is_false(self):
        agent = Agent()
        agent.graph = FakeInterruptGraph()

        with patch("builtins.print"):
            await agent.run_superstep("start", [])

        agent.pending_interrupt = False

        with patch("builtins.print"):
            await agent.run_superstep("approved", [])

        resume_call = agent.graph.calls[1][0]
        self.assertIsInstance(resume_call, Command)
        self.assertEqual(resume_call.resume, {"approved": True, "response": "approved"})


if __name__ == "__main__":
    unittest.main()
