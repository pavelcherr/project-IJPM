"""Math feasibility: a missing number, or an operation that is undefined.

The story is not solved. A warehouse total that disagrees with itself stays
with the model. What is rejected is a problem with no number at all, and a
problem whose text already names an undefined operation: division or modulo by
zero, an even root of a negative, a logarithm of zero or a negative, a
factorial of a negative, or zero raised to a negative power or to itself.
"""

from __future__ import annotations

import re

from feasibility.types import math_boost

# Closed English numerals. "a" is not here: it is also an article.
_NUMBER_WORDS = {
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
    "thousand",
    "million",
    "billion",
    "trillion",
    "dozen",
    "half",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
}

_ZERO = r"(?:0+|zero)"
_NEGATIVE = r"(?:-\s*\d+|negative|minus)"


def can_answer(instruction: str) -> tuple[bool, str]:
    problem = _problem(instruction)
    if not _has_number(problem):
        return False, "в условии нет числа"

    violation = _undefined(problem)
    if violation:
        return False, violation
    # Rules missed a hole such as "an unrecorded number of boxes".
    guessed = math_boost.unsolvable(instruction)
    if guessed:
        return False, guessed
    return True, "числа есть, запретной операции нет, считает модель"


def _problem(instruction: str) -> str:
    # python3 and the sample "echo 42" are the tool hint, not the problem.
    text = re.sub(r"\bpython\d+\b", " ", instruction, flags=re.IGNORECASE)
    text = re.sub(r"\becho\s+\d+\b", " ", text, flags=re.IGNORECASE)
    return text


def _has_number(text: str) -> bool:
    if re.search(r"\d", text):
        return True
    return any(word.lower() in _NUMBER_WORDS for word in re.findall(r"[A-Za-z]+", text))


def _undefined(text: str) -> str | None:
    if re.search(
        rf"(?:divided|divide|dividing|division|modulo|mod|remainder)\s+by\s+{_ZERO}\b",
        text,
        re.IGNORECASE,
    ):
        return "деление или остаток от деления на 0"
    if re.search(rf"\b(?:among|into|per)\s+{_ZERO}\b", text, re.IGNORECASE):
        return "деление на 0"
    if re.search(rf"(?<![\w])(?:/{{1,2}}|÷|%)\s*{_ZERO}\b", text, re.IGNORECASE):
        return "деление на 0"

    if re.search(rf"\bsquare\s+root\s+of\s+{_NEGATIVE}\b", text, re.IGNORECASE):
        return "корень из отрицательного числа"
    if re.search(r"\bsqrt\s*\(\s*-", text, re.IGNORECASE):
        return "корень из отрицательного числа"

    if re.search(
        rf"\b(?:log|ln|logarithm)\s*(?:\(\s*(?:{_ZERO}|-)|of\s+(?:{_ZERO}|negative|minus)\b)",
        text,
        re.IGNORECASE,
    ):
        return "логарифм нуля или отрицательного числа"

    if re.search(rf"\bfactorial\s+of\s+{_NEGATIVE}\b", text, re.IGNORECASE):
        return "факториал отрицательного числа"
    if re.search(r"\(\s*-\s*\d+\s*\)\s*!", text):
        return "факториал отрицательного числа"

    if re.search(
        rf"\b(?:0+|zero)\s*(?:\*\*|\^)\s*(?:-\s*\d+|0+|zero)\b",
        text,
        re.IGNORECASE,
    ):
        return "ноль в недопустимой степени"
    if re.search(
        rf"\b(?:0+|zero)\s+to\s+the\s+power\s+of\s+(?:{_ZERO}|{_NEGATIVE})\b",
        text,
        re.IGNORECASE,
    ):
        return "ноль в недопустимой степени"
    return None
