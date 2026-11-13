"""Search feasibility: two file checks, nothing else.

1. The looked-up person or thing is the file name, a heading (`# Sergei Garcia`
   or a similar marker), or a plain line inside the file. If no file carries
   that name, the task is unsolvable.
2. Keys are the words before the colon (`Born`, `Employer`, `Mentor`). If none
   of them, even as the same root (`birth`/`born`, `names`/`name`), appears in
   the instruction, the task is unsolvable.
"""

from __future__ import annotations

import re
from pathlib import Path

# Filename tokens that are not the person or the thing.
_GENERIC = {
    "card",
    "cards",
    "company",
    "data",
    "doc",
    "docs",
    "file",
    "files",
    "info",
    "note",
    "notes",
    "people",
    "person",
}


def can_answer(instruction: str, work_dir: Path) -> tuple[bool, str]:
    folder_name = _directory_name(instruction)
    if folder_name is None:
        return True, "папка в тексте не названа, не пропускаем"

    folder = work_dir / folder_name
    paths = _files(folder)
    if not paths:
        return False, f"нет файлов в {folder_name}/"

    instruction_stems = _stems(instruction)
    if not any(_subject_in(path, instruction_stems) for path in paths):
        return False, "ни в имени файла, ни в тексте нет искомого имени или предмета"

    if not any(_key_in(path, instruction_stems) for path in paths):
        return False, "ни один ключ из файлов не встречается в условии"

    return True, "имя и ключ нашлись в файлах"


def _directory_name(instruction: str) -> str | None:
    path = re.search(r"([A-Za-z0-9_-]+)/", instruction)
    if path:
        return path.group(1)
    named = re.search(r"\bdirectory\s+([A-Za-z0-9_-]+)", instruction, re.IGNORECASE)
    if named and named.group(1).lower() not in {"current", "this", "working"}:
        return named.group(1)
    return None


def _files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.md")) + sorted(folder.glob("*.txt"))


def _subject_in(path: Path, instruction_stems: set[str]) -> bool:
    text = path.read_text(encoding="utf-8")
    phrases = [_filename_phrase(path), *_body_phrases(text)]
    return any(_phrase_in(phrase, instruction_stems) for phrase in phrases)


def _filename_phrase(path: Path) -> str:
    return " ".join(part for part in re.split(r"[_\-\s]+", path.stem) if not part.isdigit())


def _body_phrases(text: str) -> list[str]:
    phrases: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            phrases.append(line.lstrip("#").strip())
            continue
        marked = re.fullmatch(r"[*_]+(.+?)[*_]+", line)
        if marked:
            phrases.append(marked.group(1).strip())
            continue
        if ":" in line:
            value = line.split(":", 1)[1].strip()
            if re.search(r"[A-Za-z]", value):
                phrases.append(value)
            continue
        phrases.append(line)
    return phrases


def _phrase_in(phrase: str, instruction_stems: set[str]) -> bool:
    words = [
        _stem(word)
        for word in re.findall(r"[A-Za-z]+", phrase)
        if len(_stem(word)) >= 3 and _stem(word) not in _GENERIC
    ]
    if not words:
        return False
    return all(any(_parts_match(word, other) for other in instruction_stems) for word in words)


def _key_in(path: Path, instruction_stems: set[str]) -> bool:
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key = line.split(":", 1)[0]
        for word in re.findall(r"[A-Za-z]+", key):
            stem = _stem(word)
            if len(stem) < 3:
                continue
            if any(_parts_match(stem, other) for other in instruction_stems):
                return True
    return False


def _stems(instruction: str) -> set[str]:
    return {
        _stem(word)
        for word in re.findall(r"[A-Za-z]+", instruction)
        if len(_stem(word)) >= 3
    }


def _parts_match(left: str, right: str) -> bool:
    if left == right:
        return True
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    return len(short) >= 3 and long.startswith(short) and len(long) - len(short) <= 2


def _stem(word: str) -> str:
    text = word.lower()
    # birth/born do not share an ending, so a suffix rule cannot see them.
    if text in {"birth", "born", "borne"}:
        return "born"
    if len(text) > 6 and text.endswith("ment"):
        text = text[:-4]
    if len(text) > 5 and text.endswith("ing"):
        text = text[:-3]
    if len(text) > 4 and text.endswith("ed"):
        text = text[:-2]
    if len(text) > 5 and text.endswith("er"):
        text = text[:-2]
    if len(text) > 5 and text.endswith("ies"):
        return text[:-3] + "y"
    if len(text) > 4 and text.endswith("s") and not text.endswith("ss"):
        return text[:-1]
    return text
