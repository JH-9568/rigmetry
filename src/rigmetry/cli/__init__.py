"""Rigmetry 명령줄 진입점."""

import asyncio
import json
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from rigmetry.config import ConfigError, build_lock, load_config
from rigmetry.experiment import (
    EvidenceError,
    ExperimentError,
    export_evidence,
    run_experiment,
    verify_evidence_sync,
)
from rigmetry.metrics import ReportError, render_markdown
from rigmetry.replay import ReplayError, replay_run
from rigmetry.storage import RunStore, StorageError
from rigmetry.tasks import TaskRunnerError, run_task
from rigmetry.tracing import EventChainError

app = typer.Typer(
    name="rigmetry",
    help="AI Agent Harness를 잠그고 실행·재생·비교합니다.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Rigmetry CLI."""


def _fail(error: ConfigError) -> None:
    typer.echo(f"오류: {error}", err=True)
    raise typer.Exit(code=1)


@app.command()
def validate(config: Path) -> None:
    """Config와 참조 Artifact를 검증합니다."""

    try:
        parsed = load_config(config)
        lock = build_lock(config)
    except ConfigError as error:
        _fail(error)
    kind = lock["kind"]
    digest = lock[f"{kind}_digest"]
    typer.echo(f"유효한 {type(parsed).__name__}입니다: {digest}")


@app.command(name="lock")
def lock_command(
    config: Path,
    output: Annotated[Path | None, typer.Option(help="Lock JSON 출력 파일")] = None,
) -> None:
    """Config와 참조 Artifact의 canonical Lock을 생성합니다."""

    try:
        lock = build_lock(config)
    except ConfigError as error:
        _fail(error)
    rendered = json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is None:
        typer.echo(rendered, nl=False)
        return
    output.write_text(rendered, encoding="utf-8")
    typer.echo(f"Lock을 생성했습니다: {output}")


@app.command()
def replay(
    run_id: str,
    offline: Annotated[bool, typer.Option("--offline", help="외부 호출 없는 Replay")] = False,
    database: Annotated[Path, typer.Option("--database", "-d", help="Run SQLite 파일")] = Path(
        "rigmetry.sqlite3"
    ),
) -> None:
    """저장된 Boundary Transcript로 Runtime을 재생합니다."""

    if not offline:
        typer.echo("오류: 현재 replay는 --offline 모드만 지원합니다", err=True)
        raise typer.Exit(code=1)
    try:
        report = asyncio.run(replay_run(RunStore(database), run_id))
    except (EventChainError, StorageError, ReplayError) as error:
        typer.echo(f"오류: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command()
def run(
    harness: Annotated[Path, typer.Option("--harness", help="Harness YAML")],
    task: Annotated[Path, typer.Option("--task", help="Task YAML")],
    database: Annotated[Path, typer.Option("--database", "-d", help="Run SQLite 파일")] = Path(
        "rigmetry.sqlite3"
    ),
    run_id: Annotated[str | None, typer.Option("--run-id", help="개별 Run 식별자")] = None,
) -> None:
    """단일 Task를 disposable Workspace에서 실행하고 평가합니다."""

    try:
        stored = asyncio.run(
            run_task(
                harness_path=harness,
                task_path=task,
                store=RunStore(database),
                run_id=run_id or f"run-{uuid4().hex}",
            )
        )
    except (ConfigError, TaskRunnerError, StorageError, ValueError) as error:
        typer.echo(f"오류: {error}", err=True)
        raise typer.Exit(code=1) from error
    result = stored.execution.result.model_dump(mode="json")
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def compare(
    experiment: Path,
    database: Annotated[Path, typer.Option("--database", "-d", help="Run SQLite 파일")] = Path(
        "rigmetry.sqlite3"
    ),
    json_output: Annotated[bool, typer.Option("--json", help="JSON Report 출력")] = False,
) -> None:
    """통제된 Variant 순서를 반복 실행하고 Metric을 비교합니다."""

    try:
        report = asyncio.run(run_experiment(experiment, RunStore(database)))
    except (
        ConfigError,
        ExperimentError,
        ReportError,
        StorageError,
        TaskRunnerError,
        ValueError,
    ) as error:
        typer.echo(f"오류: {error}", err=True)
        raise typer.Exit(code=1) from error
    if json_output:
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        typer.echo(render_markdown(report))


@app.command(name="export")
def export_command(
    experiment_id: str,
    output: Annotated[Path, typer.Option("--output", "-o", help="Evidence 출력 디렉터리")],
    database: Annotated[Path, typer.Option("--database", "-d", help="Run SQLite 파일")] = Path(
        "rigmetry.sqlite3"
    ),
) -> None:
    """저장된 Experiment를 이식 가능한 Evidence Bundle로 내보냅니다."""

    try:
        manifest = export_evidence(RunStore(database), experiment_id, output)
    except (EvidenceError, ReportError, StorageError, OSError, ValueError) as error:
        typer.echo(f"오류: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(manifest, ensure_ascii=False, indent=2))


@app.command()
def verify(evidence: Path) -> None:
    """Evidence의 Lock, Run, Replay와 Report 내부 일관성을 검증합니다."""

    try:
        result = verify_evidence_sync(evidence)
    except (EvidenceError, ReportError, ReplayError, StorageError, OSError, ValueError) as error:
        typer.echo(f"오류: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
