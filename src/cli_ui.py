from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Sequence

from rich.align import Align
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


class GitReadyUI:
    """Polished terminal rendering for the GitReady CLI."""

    def __init__(self) -> None:
        self.console = Console(highlight=False)

    def banner(self) -> None:
        title = Text("GitReady", style="bold bright_cyan")
        title.append(" // repo launch console", style="bright_magenta")
        subtitle = Text(
            "Paste a repo link, ask for setup help, or run local agent tasks.",
            style="bright_black",
        )
        body = Text()
        body.append_text(title)
        body.append("\n")
        body.append_text(subtitle)
        self.console.print()
        self.console.print(
            Panel(
                Align.center(body),
                border_style="bright_cyan",
                padding=(1, 2),
                title="[bright_black]online[/]",
                title_align="right",
            )
        )

    def prompt(self, continuation: bool = False) -> str:
        label = "continue" if continuation else "gitready"
        prompt = Text()
        prompt.append(label, style="bold bright_cyan")
        prompt.append(" / ", style="bright_black")
        prompt.append(">> ", style="bold bright_magenta")
        return self.console.input(prompt)

    def lifecycle(self, message: str) -> None:
        self.console.print(self._prefix("core", "bright_magenta", message))

    def progress(self, message: str, details: Sequence[str] = ()) -> None:
        text = self._prefix("setup", "bright_cyan", message)
        if details:
            text.append("  ")
            text.append(" | ".join(details), style="bright_black")
        self.console.print(text)

    def log(self, content: str) -> None:
        if not content:
            return
        self.console.print(
            Panel(
                content,
                border_style="bright_black",
                title="[bright_black]system stream[/]",
                title_align="left",
            )
        )

    def response(self, content: str) -> None:
        if not content:
            return
        self.console.print(
            Panel(
                Markdown(content),
                border_style="bright_cyan",
                title="[bold bright_cyan]assistant[/]",
                title_align="left",
                padding=(1, 2),
            )
        )

    def interrupt(self, question: str) -> None:
        self.console.print(
            Panel(
                question,
                border_style="bright_yellow",
                title="[bold bright_yellow]approval needed[/]",
                title_align="left",
                padding=(1, 2),
            )
        )

    def farewell(self) -> None:
        self.console.print(self._prefix("offline", "bright_black", "session closed"))

    @contextmanager
    def status(self, message: str) -> Iterator[None]:
        with self.console.status(
            f"[bright_cyan]{message}[/]",
            spinner="dots12",
            spinner_style="bright_magenta",
        ):
            yield

    def _prefix(self, label: str, style: str, message: str) -> Text:
        text = Text()
        text.append("[", style="bright_black")
        text.append(label, style=f"bold {style}")
        text.append("] ", style="bright_black")
        text.append(message, style="white")
        return text
