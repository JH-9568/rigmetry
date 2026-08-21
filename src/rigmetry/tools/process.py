"""Terminal Tool과 Evaluator가 공유하는 제한된 Process 실행 경계."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

DEFAULT_OUTPUT_LIMIT = 64 * 1024


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def rendered_output(self) -> str:
        """stdout/stderr와 잘림 여부를 사람이 읽을 수 있게 합친다."""

        sections: list[str] = []
        if self.stdout:
            sections.append(self.stdout)
        if self.stderr:
            sections.append(f"[stderr]\n{self.stderr}")
        if self.stdout_truncated:
            sections.append("[stdout truncated]")
        if self.stderr_truncated:
            sections.append("[stderr truncated]")
        return "\n".join(sections)


def _parse_command(command: str) -> tuple[str, ...]:
    if "\x00" in command:
        raise ValueError("명령에 NUL 문자를 사용할 수 없습니다")
    try:
        argv = tuple(shlex.split(command))
    except ValueError as error:
        raise ValueError(f"명령을 해석할 수 없습니다: {error}") from error
    if not argv:
        raise ValueError("빈 명령은 실행할 수 없습니다")
    return argv


def _safe_environment(process_home: Path) -> dict[str, str]:
    """Credential과 전체 부모 환경을 전달하지 않는 최소 환경."""

    return {
        "HOME": str(process_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", os.defpath),
        "PYTHONIOENCODING": "utf-8",
        "TMPDIR": str(process_home),
    }


def _read_limited(file: object, limit: int) -> tuple[str, bool]:
    file.seek(0)  # type: ignore[attr-defined]
    content = file.read(limit + 1)  # type: ignore[attr-defined]
    truncated = len(content) > limit
    return content[:limit].decode("utf-8", errors="replace"), truncated


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:  # pragma: no cover - Windows CI가 추가되면 검증한다.
        process.kill()


def run_process(
    command: str,
    *,
    cwd: str | Path,
    timeout: float,
    output_limit: int = DEFAULT_OUTPUT_LIMIT,
) -> ProcessResult:
    """shell 없이 명령을 실행하고 시간·출력·환경 경계를 적용한다."""

    workspace = Path(cwd).resolve()
    if not workspace.is_dir():
        raise ValueError(f"작업 디렉터리가 없습니다: {workspace}")
    if timeout <= 0:
        raise ValueError("timeout은 0보다 커야 합니다")
    if output_limit <= 0:
        raise ValueError("output_limit은 0보다 커야 합니다")
    argv = _parse_command(command)
    started = perf_counter()
    timed_out = False
    exit_code: int | None = None

    with (
        tempfile.TemporaryDirectory(prefix="rigmetry-process-") as process_home,
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace,
                env=_safe_environment(Path(process_home)),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=os.name == "posix",
            )
        except OSError as error:
            raise ValueError(f"명령을 시작할 수 없습니다: {argv[0]}: {error}") from error
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process(process)
            process.wait()

        stdout, stdout_truncated = _read_limited(stdout_file, output_limit)
        stderr, stderr_truncated = _read_limited(stderr_file, output_limit)

    return ProcessResult(
        argv=argv,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        duration_ms=max(0, int((perf_counter() - started) * 1000)),
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )
