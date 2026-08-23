"""Rigmetry 명령줄 진입점."""

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from rigmetry.config import ConfigError, build_lock, load_config
from rigmetry.replay import ReplayError, replay_run
from rigmetry.storage import RunStore, StorageError
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
