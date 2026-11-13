"""Feasibility for a table task. The question wording is not interpreted.

A csv named in the instruction must be in the folder. If the text names none,
the csv that is already there is used. A value written in quotes must occur in
some cell. Column names are not read out of the sentence.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path


def can_answer(instruction: str, work_dir: Path) -> tuple[bool, str]:
    paths, missing_name = _csv_paths(instruction, work_dir)
    if missing_name:
        return False, f"нет файла {missing_name}"
    if not paths:
        return False, "в папке нет csv"

    tables: list[tuple[str, list[list[str]]]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            try:
                next(reader)
            except StopIteration:
                return False, f"{path.name} пустой"
            tables.append((path.name, list(reader)))

    wanted = _quoted(instruction)
    if not wanted:
        return True, "файл на месте, значения в кавычках нет — не пропускаем"

    cells = {cell.strip() for _name, rows in tables for row in rows for cell in row}
    absent = [value for value in wanted if value not in cells]
    if absent:
        return False, f"значения {absent} нет ни в одной ячейке"
    return True, "файл на месте, значение из кавычек в таблице есть"


def _csv_paths(instruction: str, work_dir: Path) -> tuple[list[Path], str | None]:
    named = re.findall(r"\b([\w.-]+\.csv)\b", instruction, re.IGNORECASE)
    if named:
        missing = [name for name in named if not (work_dir / name).is_file()]
        if missing:
            return [], missing[0]
        return [work_dir / name for name in named], None
    found = sorted(path for path in work_dir.rglob("*.csv") if path.is_file())
    return found, None


def _quoted(instruction: str) -> list[str]:
    return [value.strip() for value in re.findall(r"['\"]([^'\"]+)['\"]", instruction) if value.strip()]
