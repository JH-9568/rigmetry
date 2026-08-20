"""Rigmetry 명령줄 진입점."""

import typer

app = typer.Typer(
    name="rigmetry",
    help="AI Agent Harness를 잠그고 실행·재생·비교합니다.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Rigmetry CLI 기반 구성입니다. 실제 명령은 아직 구현되지 않았습니다."""
