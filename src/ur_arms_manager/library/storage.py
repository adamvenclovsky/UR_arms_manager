from __future__ import annotations

import shutil
from pathlib import Path


class MissingPayloadError(Exception):
    pass


class LibraryStorage:
    def __init__(self, programs_root: Path):
        self.programs_root = Path(programs_root)

    def ensure(self) -> None:
        self.programs_root.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, relative_path: str | Path = "") -> Path:
        self.ensure()
        candidate = self.programs_root / Path(relative_path)
        resolved = candidate.resolve()
        root_resolved = self.programs_root.resolve()
        if resolved != root_resolved and root_resolved not in resolved.parents:
            raise ValueError(f"Library path escapes root: {relative_path}")
        return resolved

    def relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.programs_root.resolve()).as_posix()

    def list_program_ids(self) -> list[str]:
        self.ensure()
        refs: list[str] = []
        for path in self.programs_root.rglob("*"):
            if not path.is_file():
                continue
            refs.append(self.relative_path(path))
        return sorted(refs)

    def list_entries(self, relative_dir: str = "") -> list[Path]:
        directory = self.resolve_path(relative_dir)
        if not directory.exists() or not directory.is_dir():
            raise FileNotFoundError(f"Library directory not found: {directory}")
        return sorted(directory.iterdir(), key=lambda entry: (entry.is_file(), entry.name.lower()))

    def copy_program_file(
        self,
        source_file: Path,
        target_dir: str = "uploaded",
        preferred_name: str | None = None,
    ) -> Path:
        source = Path(source_file)
        destination_dir = self.resolve_path(target_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        target_name = preferred_name or source.name
        destination = self._unique_path(destination_dir, target_name)
        shutil.copy2(source, destination)
        return destination

    def create_folder(self, relative_dir: str) -> Path:
        directory = self.resolve_path(relative_dir)
        directory.mkdir(parents=True, exist_ok=False)
        return directory

    def remove_path(self, relative_path: str) -> Path:
        path = self.resolve_path(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"Library path not found: {path}")
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return path

    def move_path(self, source_rel: str, destination_rel: str) -> Path:
        source = self.resolve_path(source_rel)
        destination = self.resolve_path(destination_rel)
        if not source.exists():
            raise FileNotFoundError(f"Library path not found: {source}")
        if destination.exists():
            raise FileExistsError(f"Library destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return destination

    def copy_path(self, source_rel: str, destination_rel: str) -> Path:
        source = self.resolve_path(source_rel)
        destination = self.resolve_path(destination_rel)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)
        return destination

    def resolve_payload_file(self, reference: str) -> Path:
        path = self.resolve_path(reference)
        if path.exists() and path.is_file():
            return path
        if path.exists() and path.is_dir():
            raise MissingPayloadError(f"Library path is a directory, not a file: {path}")

        raise MissingPayloadError(f"Library path not found: {path}")

    def _unique_path(self, directory: Path, name: str) -> Path:
        candidate = directory / name
        if not candidate.exists():
            return candidate

        stem = Path(name).stem
        suffix = Path(name).suffix
        index = 1
        while True:
            candidate = directory / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1
