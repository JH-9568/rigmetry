"""Command exit code로 Task 성공을 판정하는 Evaluator."""

from __future__ import annotations

import asyncio
from pathlib import Path

from rigmetry.models import EvaluatorResult
from rigmetry.tools.process import DEFAULT_OUTPUT_LIMIT, run_process


class CommandEvaluator:
    """Agent Runtime과 별도 timeout으로 disposable Workspace를 평가한다."""

    def __init__(
        self,
        command: str,
        *,
        timeout: float,
        output_limit: int = DEFAULT_OUTPUT_LIMIT,
    ) -> None:
        self.command = command
        self.timeout = timeout
        self.output_limit = output_limit
        if not command.strip():
            raise ValueError("Evaluator 명령은 비어 있을 수 없습니다")
        if timeout <= 0:
            raise ValueError("Evaluator timeout은 0보다 커야 합니다")
        if output_limit <= 0:
            raise ValueError("Evaluator output_limit은 0보다 커야 합니다")

    async def evaluate(self, workspace: str | Path) -> EvaluatorResult:
        try:
            process = await asyncio.to_thread(
                run_process,
                self.command,
                cwd=workspace,
                timeout=self.timeout,
                output_limit=self.output_limit,
            )
        except ValueError as error:
            return EvaluatorResult(passed=False, output=str(error))

        return EvaluatorResult(
            passed=not process.timed_out and process.exit_code == 0,
            exit_code=process.exit_code,
            output=process.rendered_output() or None,
            timed_out=process.timed_out,
        )
