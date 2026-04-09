from __future__ import annotations

import shutil
from pathlib import Path


class LibraryStorage:
    def __init__(self, programs_root: Path):
        self.programs_root = Path(programs_root)

    def ensure(self) -> None:
        self.programs_root.mkdir(parents=True, exist_ok=True)

    def program_dir(self, program_id: str) -> Path:
        return self.programs_root / program_id

    def manifest_path(self, program_id: str) -> Path:
        return self.program_dir(program_id) / "manifest.yaml"

    def list_program_ids(self) -> list[str]:
        self.ensure()
        ids: list[str] = []
        for entry in self.programs_root.iterdir():
            if entry.is_dir() and self.manifest_path(entry.name).exists():
                ids.append(entry.name)
        return sorted(ids)

    def copy_program_file(self, program_id: str, source_file: Path) -> Path:
        target_dir = self.program_dir(program_id)
        target_dir.mkdir(parents=True, exist_ok=False)
        target_file = target_dir / source_file.name
        shutil.copy2(source_file, target_file)
        return target_file

    def remove_program(self, program_id: str) -> None:
        shutil.rmtree(self.program_dir(program_id))
