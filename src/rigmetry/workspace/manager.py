"""Task별 임시 작업 사본의 생성과 정리."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(ValueError):
    """Workspace 경계 또는 준비 과정에서 발견한 사용자 입력 오류."""


@dataclass(frozen=True)
class DisposableWorkspace:
    """한 Task 실행 동안만 존재하는 원본 Workspace 사본."""

    original: Path
    path: Path


def _contained_path(path: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise WorkspaceError(f"허용 root 밖의 Workspace입니다: {path}") from error
    return resolved_path


def _reject_reference_symlinks(path: Path, root: Path) -> None:
    """참조 경로 자체 또는 중간 디렉터리의 symlink를 거부한다."""

    try:
        relative = path.absolute().relative_to(root.resolve())
    except ValueError:
        return  # root 밖 경로는 _contained_path가 설명 가능한 오류로 처리한다.
    candidate = root.resolve()
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise WorkspaceError(f"Workspace symlink는 지원하지 않습니다: {relative}")


def _validate_source(source: Path) -> None:
    if not source.is_dir():
        raise WorkspaceError(f"Workspace 디렉터리가 없습니다: {source}")
    if source.is_symlink():
        raise WorkspaceError(f"Workspace symlink는 지원하지 않습니다: {source}")
    for candidate in source.rglob("*"):
        if candidate.is_symlink():
            relative = candidate.relative_to(source)
            raise WorkspaceError(
                f"Workspace symlink는 지원하지 않습니다: {relative.as_posix()}"
            )


class WorkspaceManager:
    """검증된 원본을 임시 디렉터리로 복사하고 확실히 정리한다.

    이 사본은 원본 보호 수단이며 Process의 시스템 접근을 제한하는 보안
    Sandbox가 아니다.
    """

    def __init__(self, root: str | Path, *, temporary_root: str | Path | None = None) -> None:
        self.root = Path(root).resolve()
        self.temporary_root = (
            Path(temporary_root).resolve() if temporary_root is not None else None
        )
        if not self.root.is_dir():
            raise WorkspaceError(f"허용 root 디렉터리가 없습니다: {self.root}")
        if self.temporary_root is not None and not self.temporary_root.is_dir():
            raise WorkspaceError(
                f"임시 Workspace root 디렉터리가 없습니다: {self.temporary_root}"
            )

    @contextmanager
    def create(self, source: str | Path) -> Iterator[DisposableWorkspace]:
        """원본의 disposable 사본을 만들고 context 종료 시 삭제한다."""

        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = self.root / source_path
        _reject_reference_symlinks(source_path, self.root)
        resolved_source = _contained_path(source_path, self.root)
        _validate_source(resolved_source)

        with tempfile.TemporaryDirectory(
            prefix="rigmetry-workspace-",
            dir=self.temporary_root,
        ) as temporary_directory:
            destination = Path(temporary_directory) / "workspace"
            try:
                shutil.copytree(
                    resolved_source,
                    destination,
                    symlinks=False,
                    ignore=shutil.ignore_patterns(".git"),
                )
            except OSError as error:
                raise WorkspaceError(f"Workspace 사본을 만들 수 없습니다: {error}") from error
            yield DisposableWorkspace(original=resolved_source, path=destination)
