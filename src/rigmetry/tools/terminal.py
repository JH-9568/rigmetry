"""Disposable Workspace 안에서만 동작하는 Terminal Tool."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rigmetry.models import ToolCall, ToolDefinition, ToolResult
from rigmetry.tools.process import DEFAULT_OUTPUT_LIMIT, run_process

TERMINAL_DEFINITION = ToolDefinition(
    name="terminal",
    description="현재 disposable Workspace에서 한 개의 명령을 실행합니다.",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "minLength": 1},
            "timeout": {"type": "number", "exclusiveMinimum": 0},
        },
        "required": ["command"],
        "additionalProperties": False,
    },
)


class TerminalTool:
    """고정된 작업 디렉터리와 상한 안에서 Terminal 호출을 실행한다."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        timeout: float = 30,
        output_limit: int = DEFAULT_OUTPUT_LIMIT,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.timeout = timeout
        self.output_limit = output_limit
        if not self.workspace.is_dir():
            raise ValueError(f"작업 디렉터리가 없습니다: {self.workspace}")
        if timeout <= 0:
            raise ValueError("timeout은 0보다 커야 합니다")
        if output_limit <= 0:
            raise ValueError("output_limit은 0보다 커야 합니다")

    async def __call__(self, call: ToolCall) -> ToolResult:
        if call.name != TERMINAL_DEFINITION.name:
            return ToolResult(
                call_id=call.id,
                output=f"지원하지 않는 Tool입니다: {call.name}",
                is_error=True,
            )
        unexpected = sorted(set(call.arguments) - {"command", "timeout"})
        if unexpected:
            return ToolResult(
                call_id=call.id,
                output="지원하지 않는 terminal argument입니다: " + ", ".join(unexpected),
                is_error=True,
            )
        command = call.arguments.get("command")
        requested_timeout = call.arguments.get("timeout", self.timeout)
        if not isinstance(command, str):
            return ToolResult(
                call_id=call.id,
                output="terminal.command는 문자열이어야 합니다",
                is_error=True,
            )
        if not isinstance(requested_timeout, int | float) or isinstance(
            requested_timeout, bool
        ):
            return ToolResult(
                call_id=call.id,
                output="terminal.timeout은 숫자여야 합니다",
                is_error=True,
            )
        if requested_timeout <= 0 or requested_timeout > self.timeout:
            return ToolResult(
                call_id=call.id,
                output=f"terminal.timeout은 0보다 크고 {self.timeout} 이하여야 합니다",
                is_error=True,
            )
        try:
            result = await asyncio.to_thread(
                run_process,
                command,
                cwd=self.workspace,
                timeout=float(requested_timeout),
                output_limit=self.output_limit,
            )
        except ValueError as error:
            return ToolResult(call_id=call.id, output=str(error), is_error=True)

        output = result.rendered_output()
        if result.timed_out:
            output = f"{output}\n[terminal timeout]".lstrip()
        if not output:
            output = f"[exit_code={result.exit_code}]"
        return ToolResult(
            call_id=call.id,
            output=output,
            is_error=result.timed_out or result.exit_code != 0,
        )
