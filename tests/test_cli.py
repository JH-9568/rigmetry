from typer.testing import CliRunner

from openharness import __version__
from openharness.cli import app


def test_package_and_cli_entry_point() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert __version__ == "0.1.0"
    assert result.exit_code == 0
    assert "AI Agent Harness를 정의·실행·추적·평가·비교합니다" in result.output
