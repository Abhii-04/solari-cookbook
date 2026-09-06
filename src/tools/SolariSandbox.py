import os
from typing import Any, Literal

from dotenv import load_dotenv
from langchain_core.tools import tool
from solari_sandbox import SandboxClient

load_dotenv(override=True)


DEFAULT_CALL_TIMEOUT_MS = 5 * 60 * 1000


class SolariSandbox:
    def __init__(self):
        self.api_key = self._solari_api()
        self.base_url = "https://api.getsolari.com"
        self.call_timeout_ms = DEFAULT_CALL_TIMEOUT_MS

    def _solari_api(self):
        solari_api = os.getenv("SOLARI_API_KEY")
        if not solari_api:
            raise RuntimeError("SOLARI_API_KEY is required to create a Solari sandbox")
        return solari_api

    def client(self):
        return SandboxClient(
            api_key=self.api_key,
            base_url=self.base_url,
            call_timeout_ms=self.call_timeout_ms,
        )

    def _sandbox_result(self, sandbox, note: str, reused_existing: bool = False):
        return {
            "type": "sandbox",
            "sandbox_id": sandbox.sandboxId,
            "control_url": getattr(sandbox, "controlUrl", None),
            "expires_at": getattr(sandbox, "expiresAt", None),
            "connected": bool(getattr(sandbox, "connected", False)),
            "reused_existing": reused_existing,
            "note": note,
        }

    async def connect_existing(self, connect: bool = False, states: tuple[str, ...] = ("running", "paused")):
        client = self.client()
        try:
            for state in states:
                page = await client.list(state=state, kind="sandbox", limit=10)
                for sandbox_view in page.get("sandboxes", []):
                    sandbox = await client.connect(sandbox_view.sandboxId)
                    if connect:
                        await sandbox.connect()

                    return self._sandbox_result(
                        sandbox,
                        f"Create failed, so connected to existing {state} sandbox.",
                        reused_existing=True,
                    )

            return None
        finally:
            await client.aclose()

    async def create(
        self,
        template: str | None = None,
        cpu: int = 2,
        mem_mb: int = 2048,
        disk_gb: int | None = None,
        envs: dict[str, str] | None = None,
        metadata: dict[str, str] | None = None,
        timeout_ms: int = 3600000,
        from_snapshot: str | None = None,
        lifecycle: dict[str, Any] | None = None,
        volumes: list[dict[str, str]] | None = None,
        connect: bool = False,
    ):
        client = self.client()
        lifecycle = lifecycle or {"onTimeout": "pause", "autoResume": True}

        try:
            try:
                sandbox = await client.create(
                    template=template,
                    cpu=cpu,
                    mem_mb=mem_mb,
                    disk_gb=disk_gb,
                    envs=envs,
                    metadata=metadata,
                    timeout_ms=timeout_ms,
                    from_snapshot=from_snapshot,
                    lifecycle=lifecycle,
                    volumes=volumes,
                )
            except Exception as create_error:
                existing = await self.connect_existing(connect=connect)
                if existing is not None:
                    existing["create_error"] = f"{type(create_error).__name__}: {create_error}"
                    return existing
                raise

            if connect:
                await sandbox.connect()

            return self._sandbox_result(
                sandbox,
                "Create was completed successfully.",
            )
        finally:
            await client.aclose()

    async def run_code(
        self,
        sandbox_id: str,
        code: str,
        language: Literal["python", "javascript", "typescript", "bash", "r"] = "bash",
    ):
        client = self.client()
        try:
            sandbox = await client.connect(sandbox_id)
            await sandbox.connect()
            result = await sandbox.run_code(
                code=code,
                language=language,
            )

            outputs = []
            for item in result.results:
                outputs.append(
                    {
                        "type": item.type,
                        "text": item.text,
                        "json": item.json,
                        "markdown": item.markdown,
                    }
                )

            return {
                "type": "sandbox_code_execution",
                "sandbox_id": sandbox_id,
                "language": language,
                "outputs": outputs,
                "error": result.error,
            }
        finally:
            await client.aclose()


_solari_sandbox = None

#main class instance
def SolariSandboxClient():
    global _solari_sandbox
    if _solari_sandbox is None:
        _solari_sandbox = SolariSandbox()
    return _solari_sandbox


@tool
async def solari_sandbox_create(
    template: str | None = None,
    cpu: int = 2,
    mem_mb: int = 2048,
    disk_gb: int | None = None,
    envs: dict[str, str] | None = None,
    metadata: dict[str, str] | None = None,
    timeout_ms: int = 3600000,
    from_snapshot: str | None = None,
    lifecycle: dict[str, Any] | None = None,
    volumes: list[dict[str, str]] | None = None,
    connect: bool = False,
) -> dict[str, Any]:
    """Create a Solari sandbox session and return its connection metadata."""
    return await SolariSandboxClient().create(
        template=template,
        cpu=cpu,
        mem_mb=mem_mb,
        disk_gb=disk_gb,
        envs=envs,
        metadata=metadata,
        timeout_ms=timeout_ms,
        from_snapshot=from_snapshot,
        lifecycle=lifecycle,
        volumes=volumes,
        connect=connect,
    )


@tool
async def solari_sandbox_run_code(
    sandbox_id: str,
    code: str,
    language: Literal["python", "javascript", "typescript", "bash", "r"] = "bash",
) -> dict[str, Any]:
    """Run code or shell commands inside an existing Solari sandbox."""
    return await SolariSandboxClient().run_code(
        sandbox_id=sandbox_id,
        code=code,
        language=language,
    )
