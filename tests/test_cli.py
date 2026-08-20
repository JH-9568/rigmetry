from typer.testing import CliRunner

from rigmetry import __version__
from rigmetry.cli import app


def test_package_and_cli_entry_point() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert __version__ == "0.1.0"
    assert result.exit_code == 0
    assert "AI Agent Harness를 잠그고 실행·재생·비교합니다" in result.output
