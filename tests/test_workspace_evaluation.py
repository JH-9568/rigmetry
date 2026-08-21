import asyncio
import os
import sys
from pathlib import Path

import pytest

from rigmetry.evaluation import CommandEvaluator
from rigmetry.models import ToolCall
from rigmetry.tools import TerminalTool
from rigmetry.workspace import WorkspaceError, WorkspaceManager


def _python(code: str) -> str:
    escaped = code.replace("\\", "\\\\").replace('"', '\\"')
    return f'{sys.executable} -c "{escaped}"'


def test_workspace_copy_protects_original_and_is_cleaned_up(tmp_path: Path) -> None:
    source = tmp_path / "fixture"
    source.mkdir()
    (source / "value.txt").write_text("original", encoding="utf-8")
    manager = WorkspaceManager(tmp_path)

    with manager.create("fixture") as workspace:
        disposable_path = workspace.path
        (workspace.path / "value.txt").write_text("changed", encoding="utf-8")
        (workspace.path / "new.txt").write_text("new", encoding="utf-8")
        assert workspace.original == source.resolve()
        assert disposable_path.is_dir()

    assert (source / "value.txt").read_text(encoding="utf-8") == "original"
    assert not (source / "new.txt").exists()
    assert not disposable_path.exists()


def test_workspace_rejects_escape_and_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    manager = WorkspaceManager(root)
    with pytest.raises(WorkspaceError, match="허용 root 밖"):
        with manager.create("../outside"):
            pass

    fixture = root / "fixture"
    fixture.mkdir()
    try:
        (fixture / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("이 환경은 symlink 생성을 지원하지 않습니다")
    with pytest.raises(WorkspaceError, match="symlink"):
        with manager.create(fixture):
            pass

    clean_fixture = root / "clean-fixture"
    clean_fixture.mkdir()
    alias = root / "fixture-alias"
    alias.symlink_to(clean_fixture, target_is_directory=True)
    with pytest.raises(WorkspaceError, match="symlink"):
        with manager.create(alias):
            pass


def test_terminal_uses_workspace_minimal_environment_timeout_and_output_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RIGMETRY_TEST_SECRET", "must-not-leak")
    terminal = TerminalTool(tmp_path, timeout=2)
    limited_terminal = TerminalTool(tmp_path, timeout=2, output_limit=16)

    pwd_result = asyncio.run(
        terminal(
            ToolCall(
                id="pwd",
                name="terminal",
                arguments={"command": _python("import os;print(os.getcwd())")},
            )
        )
    )
    env_result = asyncio.run(
        terminal(
            ToolCall(
                id="env",
                name="terminal",
                arguments={
                    "command": _python(
                        "import os;print(os.environ.get('RIGMETRY_TEST_SECRET','missing'))"
                    )
                },
            )
        )
    )
    timeout_result = asyncio.run(
        terminal(
            ToolCall(
                id="timeout",
                name="terminal",
                arguments={
                    "command": _python("import time;time.sleep(2)"),
                    "timeout": 0.1,
                },
            )
        )
    )
    limited_result = asyncio.run(
        limited_terminal(
            ToolCall(
                id="limit",
                name="terminal",
                arguments={"command": _python("print('x'*100)")},
            )
        )
    )

    assert str(tmp_path.resolve()) in pwd_result.output
    assert "missing" in env_result.output
    assert "must-not-leak" not in env_result.output
    assert timeout_result.is_error
    assert "terminal timeout" in timeout_result.output
    assert limited_result.is_error is False
    assert "stdout truncated" in limited_result.output
    assert "x" * 17 not in limited_result.output


def test_terminal_does_not_interpret_shell_operators(tmp_path: Path) -> None:
    terminal = TerminalTool(tmp_path)
    marker = tmp_path / "created"
    result = asyncio.run(
        terminal(
            ToolCall(
                id="shell",
                name="terminal",
                arguments={"command": f"{sys.executable} -c pass && touch {marker}"},
            )
        )
    )

    assert result.call_id == "shell"
    assert not marker.exists()


def test_command_evaluator_distinguishes_pass_failure_timeout_and_truncation(
    tmp_path: Path,
) -> None:
    passed = asyncio.run(
        CommandEvaluator(_python("print('ok')"), timeout=1).evaluate(tmp_path)
    )
    failed = asyncio.run(
        CommandEvaluator(_python("raise SystemExit(3)"), timeout=1).evaluate(tmp_path)
    )
    timed_out = asyncio.run(
        CommandEvaluator(_python("import time;time.sleep(2)"), timeout=0.1).evaluate(tmp_path)
    )
    truncated = asyncio.run(
        CommandEvaluator(_python("print('y'*100)"), timeout=1, output_limit=8).evaluate(
            tmp_path
        )
    )

    assert passed.passed and passed.exit_code == 0 and passed.timed_out is False
    assert failed.passed is False and failed.exit_code == 3 and failed.timed_out is False
    assert timed_out.passed is False and timed_out.exit_code is None and timed_out.timed_out
    assert truncated.passed and "stdout truncated" in (truncated.output or "")


def test_process_environment_does_not_copy_parent_environment(tmp_path: Path) -> None:
    secret_name = "RIGMETRY_PARENT_ONLY_SECRET"
    os.environ[secret_name] = "credential-value"
    try:
        result = asyncio.run(
            CommandEvaluator(
                _python(f"import os;print('{secret_name}' in os.environ)"), timeout=1
            ).evaluate(tmp_path)
        )
    finally:
        os.environ.pop(secret_name, None)

    assert result.passed
    assert result.output is not None and "False" in result.output
    assert "credential-value" not in result.output


def test_terminal_change_is_evaluated_in_copy_without_touching_original(
    tmp_path: Path,
) -> None:
    source = tmp_path / "fixture"
    source.mkdir()
    (source / "value.txt").write_text("before", encoding="utf-8")

    with WorkspaceManager(tmp_path).create(source) as workspace:
        terminal = TerminalTool(workspace.path)
        tool_result = asyncio.run(
            terminal(
                ToolCall(
                    id="edit",
                    name="terminal",
                    arguments={
                        "command": _python(
                            "from pathlib import Path;Path('value.txt').write_text('after')"
                        )
                    },
                )
            )
        )
        evaluation = asyncio.run(
            CommandEvaluator(
                _python(
                    "from pathlib import Path;raise SystemExit("
                    "Path('value.txt').read_text()!='after')"
                ),
                timeout=1,
            ).evaluate(workspace.path)
        )

    assert tool_result.is_error is False
    assert evaluation.passed
    assert (source / "value.txt").read_text(encoding="utf-8") == "before"
