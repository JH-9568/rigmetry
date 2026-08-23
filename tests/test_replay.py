import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rigmetry.cli import app
from rigmetry.models import (
    EvaluatorResult,
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelResult,
    ProviderCapabilities,
    TokenTotalSource,
    TokenUsage,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from rigmetry.replay import ReplayError, replay_run
from rigmetry.runtime import AgentRuntime, RuntimeLimits, RuntimeRequest
from rigmetry.storage import RunStore, StorageError
from rigmetry.tracing import EventChainError

DIGEST = f"sha256:{'1' * 64}"


def _usage(input_tokens: int, output_tokens: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        total_tokens_source=TokenTotalSource.PROVIDER,
    )


def _request(*, run_id: str = "run-replay", tools: bool = True) -> RuntimeRequest:
    return RuntimeRequest(
        run_id=run_id,
        model="test-model",
        system_prompt="system",
        prompt="credential super-secret must be redacted",
        tools=(ToolDefinition(name="terminal"),) if tools else (),
        limits=RuntimeLimits(max_steps=3, timeout=1, max_total_tokens=100),
        harness_digest=DIGEST,
        task_digest=DIGEST,
        environment_digest=DIGEST,
    )


class FakeAdapter:
    name = "fake"
    version = "test"
    capabilities = ProviderCapabilities(tool_calling=True, token_usage=True)

    def __init__(self, *results: ModelResult) -> None:
        self.results = list(results)
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResult:
        self.calls += 1
        return self.results.pop(0)


async def _live_execution(request: RuntimeRequest):
    call = ToolCall(
        id="call-1",
        name="terminal",
        arguments={"command": "pytest", "token": "super-secret"},
    )
    adapter = FakeAdapter(
        ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT),
            tool_calls=(call,),
            usage=_usage(3, 2),
            response_model="resolved-model",
        ),
        ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT, content="완료"),
            usage=_usage(2, 1),
            response_model="resolved-model",
        ),
    )

    async def tool_handler(tool_call: ToolCall) -> ToolResult:
        return ToolResult(
            call_id=tool_call.id,
            output="Bearer " + "abcdefghijklmnop" + " and super-secret",
        )

    return await AgentRuntime(adapter, tool_handler).run(request)


def test_sqlite_store_redacts_credentials_and_replays_without_external_calls(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runs.sqlite3"
    request = _request()
    execution = asyncio.run(_live_execution(request))
    evaluator = EvaluatorResult(passed=True, exit_code=0, output="super-secret")
    store = RunStore(database)

    stored = store.save_execution(
        request,
        execution,
        evaluator=evaluator,
        secrets=("super-secret",),
    )
    report = asyncio.run(replay_run(store, request.run_id))

    assert stored.execution.boundaries[0].kind == "model"
    assert report.result.termination_reason == execution.result.termination_reason
    assert report.result.usage == execution.result.usage
    assert report.result.evaluator == EvaluatorResult(
        passed=True,
        exit_code=0,
        output="[REDACTED]",
    )
    assert report.external_calls.model == 0
    assert report.external_calls.tool == 0
    assert report.external_calls.evaluator == 0
    assert report.metrics_match
    database_bytes = database.read_bytes()
    assert b"super-secret" not in database_bytes
    assert b"abcdefghijklmnop" not in database_bytes


def test_store_detects_event_chain_and_transcript_digest_corruption(tmp_path: Path) -> None:
    database = tmp_path / "runs.sqlite3"
    request = _request(run_id="run-corrupt")
    store = RunStore(database)
    store.save_execution(request, asyncio.run(_live_execution(request)))

    with sqlite3.connect(database) as connection:
        raw = connection.execute(
            "SELECT event_json FROM events WHERE run_id = ? AND sequence = 0",
            (request.run_id,),
        ).fetchone()[0]
        event = json.loads(raw)
        event["payload"]["max_steps"] = 999
        connection.execute(
            "UPDATE events SET event_json = ? WHERE run_id = ? AND sequence = 0",
            (json.dumps(event), request.run_id),
        )

    with pytest.raises(EventChainError, match="Event hash"):
        store.load_run(request.run_id)

    second_database = tmp_path / "digest.sqlite3"
    second_store = RunStore(second_database)
    second_store.save_execution(request, asyncio.run(_live_execution(request)))
    with sqlite3.connect(second_database) as connection:
        result = json.loads(
            connection.execute(
                "SELECT result_json FROM runs WHERE run_id = ?", (request.run_id,)
            ).fetchone()[0]
        )
        result["steps"] = 99
        connection.execute(
            "UPDATE runs SET result_json = ? WHERE run_id = ?",
            (json.dumps(result), request.run_id),
        )

    with pytest.raises(StorageError, match="Transcript digest"):
        second_store.load_run(request.run_id)


def test_replay_rejects_runtime_version_mismatch(tmp_path: Path) -> None:
    request = _request(run_id="run-old-version")
    store = RunStore(tmp_path / "runs.sqlite3")
    store.save_execution(
        request,
        asyncio.run(_live_execution(request)),
        runtime_version="0",
    )

    with pytest.raises(ReplayError, match="Runtime version"):
        asyncio.run(replay_run(store, request.run_id))


def test_replay_preserves_tool_timeout_termination(tmp_path: Path) -> None:
    call = ToolCall(id="call-timeout", name="terminal")
    adapter = FakeAdapter(
        ModelResult(
            message=ModelMessage(role=MessageRole.ASSISTANT),
            tool_calls=(call,),
            usage=_usage(1, 1),
        )
    )
    request = _request(run_id="run-timeout").model_copy(
        update={"limits": RuntimeLimits(max_steps=1, timeout=0.001, max_total_tokens=100)}
    )

    async def slow_tool(tool_call: ToolCall) -> ToolResult:
        await asyncio.sleep(0.05)
        return ToolResult(call_id=tool_call.id, output="late")

    execution = asyncio.run(AgentRuntime(adapter, slow_tool).run(request))
    store = RunStore(tmp_path / "runs.sqlite3")
    store.save_execution(request, execution)
    report = asyncio.run(replay_run(store, request.run_id))

    assert report.result.termination_reason == "timeout_exceeded"
    assert report.result.tool_calls == 1


def test_replay_cli_requires_offline_and_prints_verified_report(tmp_path: Path) -> None:
    database = tmp_path / "runs.sqlite3"
    request = _request(run_id="run-cli")
    RunStore(database).save_execution(request, asyncio.run(_live_execution(request)))
    runner = CliRunner()

    online = runner.invoke(app, ["replay", request.run_id, "--database", str(database)])
    offline = runner.invoke(
        app,
        ["replay", request.run_id, "--offline", "--database", str(database)],
    )

    assert online.exit_code == 1
    assert "--offline" in online.output
    assert offline.exit_code == 0
    assert '"metrics_match": true' in offline.output
    assert '"model": 0' in offline.output
