"""Rigmetry 명령줄 진입점."""

import json
from pathlib import Path
from typing import Annotated

import typer

from rigmetry.config import ConfigError, build_lock, load_config

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
