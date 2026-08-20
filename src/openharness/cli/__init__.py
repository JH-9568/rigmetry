"""OpenHarness 명령줄 진입점."""

import typer

app = typer.Typer(
    name="openharness",
    help="AI Agent Harness를 정의·실행·추적·평가·비교합니다.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """OpenHarness CLI 기반 구성입니다. 실제 명령은 아직 구현되지 않았습니다."""
