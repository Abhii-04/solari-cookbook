import asyncio
import faulthandler
import select
import sys

from src.agent import Agent

faulthandler.enable(all_threads=True)


def needs_continuation(text: str) -> bool:
    return text.rstrip().lower().endswith(
        (
            " and",
            " or",
            " then",
            " then also",
            " with",
            " from",
            " to",
            ",",
            "\\",
        )
    )


def read_user_input() -> str:
    try:
        lines = [input("You: ")]
    except EOFError:
        return "exit"

    while select.select([sys.stdin], [], [], 0.05)[0]:
        next_line = sys.stdin.readline()
        if not next_line:
            break
        lines.append(next_line.rstrip("\n"))

    while needs_continuation(" ".join(line.strip() for line in lines if line.strip())):
        try:
            lines.append(input("... "))
        except EOFError:
            break

    return " ".join(line.strip() for line in lines if line.strip())


async def main():
    agent = Agent()
    await agent.setup()

    try:
        while True:
            user_input = read_user_input()

            if user_input.lower() in {"exit", "quit"}:
                break
            if not user_input.strip():
                continue

            await agent.run_superstep(user_input, [])

    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
