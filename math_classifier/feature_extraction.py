"""Hole detectors for math word problems.

Each feature is a family of phrasings, not one generator sentence.
A repaired phrase ("a handful, exactly 9") stays at zero.
CatBoost only sees these numbers. It does not read the raw sentence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# After a cue, a digit this close means the amount was actually given.
_REPAIR = 24

_CUES = [
    re.compile(r"\bunrecorded\b"),
    re.compile(r"\bnot recorded\b"),
    re.compile(r"\bnot logged\b"),
    re.compile(r"\bnever logged\b"),
    re.compile(r"\bnot written(?:\s+down)?\b"),
    re.compile(r"\bleft blank\b"),
    re.compile(r"\bnot stated\b"),
    re.compile(r"\bnot given\b"),
    re.compile(r"\bnot provided\b"),
    re.compile(r"\bunspecified\b"),
    re.compile(r"\billegible\b"),
    re.compile(r"\bredacted\b"),
    re.compile(r"\bfactor that is not\b"),
    re.compile(r"\bnowhere in the\b"),
    re.compile(r"\bnot in the ledger\b"),
    re.compile(r"\bnot on the (?:sheet|form|ledger|page|slip)\b"),
    re.compile(r"\bnobody (?:wrote|counted)\b"),
    re.compile(r"\bno one (?:wrote|counted)\b"),
    re.compile(r"\b(?:was|were) omitted\b"),
    re.compile(r"\bwithout a (?:number|figure|count)\b"),
    re.compile(r"\bwho knows how many\b"),
    re.compile(r"\bgoodness knows how many\b"),
    re.compile(r"\bundisclosed\b"),
    re.compile(r"\bmystery number\b"),
    re.compile(r"\bunknown (?:number|amount|quantity)\b"),
    re.compile(r"\bmissing (?:number|amount|figure|quantity)\b"),
    re.compile(r"\bcount was skipped\b"),
    re.compile(r"\bbefore (?:anyone|anybody) counts\b"),
    re.compile(r"\bnot counted\b"),
    re.compile(r"\bwithout counting\b"),
    re.compile(r"\bhowever many\b"),
    re.compile(r"\bthe usual (?:number|amount|count)\b"),
    re.compile(r"\bas (?:many|much)(?:\s+\w+){0,3}\s+as\b"),
    re.compile(r"\bas it did\b"),
    re.compile(r"\ba handful\b"),
    re.compile(r"\bhandful of\b"),
    re.compile(r"\ba smattering\b"),
    re.compile(r"\ban untold\b"),
    re.compile(r"\ba bunch of them\b"),
    re.compile(r"\bplenty of them\b"),
    re.compile(r"\ban uncounted\b"),
    re.compile(r"\ba pile of them\b"),
    re.compile(r"\bno count was\b"),
    re.compile(r"\bthe figure is\b"),
    re.compile(r"\bamount (?:is|was) (?:unknown|missing|blank)\b"),
    re.compile(r"\bsame (?:number|count|amount) as (?:yesterday|before|last)\b"),
    re.compile(r"\b(?:yesterday|the day before|last week|last time|last month)(?:'s)? (?:count|total|number|amount)\b"),
]

_ZERO = r"(?:0+|zero)"
_DIVZERO = re.compile(
    rf"(?:divided|divide|dividing|division|modulo|mod|remainder)\s+by\s+{_ZERO}\b"
    rf"|\b(?:among|into|per)\s+{_ZERO}\b"
    rf"|(?<![\w])(?:/{{1,2}}|÷|%)\s*{_ZERO}\b"
    rf"|\b(?:among|across|into|between)\s+(?:no|none|nobody|nothing)\b"
    rf"|\b(?:no|zero)\s+(?:groups|people|zones|warehouses|bins|containers|teams|rows)\b",
    re.IGNORECASE,
)

_MADE = re.compile(
    r"\b(?:makes|make|made|produces|produce|produced|bakes|bake|baked|"
    r"prints|print|printed|sews|sew|sewed|bottles|bottle|bottled)\s+(\d+)\b",
    re.IGNORECASE,
)
_OUT = re.compile(
    r"\b(?:gives out|give out|gave out|gives away|give away|gave away|"
    r"sells|sell|sold|hands out|handed out|donates|donate|donated)\s+(\d+)\b",
    re.IGNORECASE,
)
_START = re.compile(
    r"\b(?:has|holds|owns|keeps|starts(?:\s+\w+){0,3}\s+with|opens with)\s+(\d+)\b",
    re.IGNORECASE,
)
_AWAY = re.compile(
    r"\b(?:gives away|give away|gave away|donates|donate|donated|hands away)\s+(\d+)\b",
    re.IGNORECASE,
)
_CLAIM = re.compile(
    r"\b(?:says|claims|records|shows|lists|reads|insists|maintains|writes|wrote)\s+"
    r"(\d+)\s+(?:\w+\s+){0,4}(?:remain|remaining|left|still)\b",
    re.IGNORECASE,
)
_BETWEEN = re.compile(r"\bbetween\s+(\d+)\s+and\s+(\d+)\b", re.IGNORECASE)
_FROM_TO = re.compile(r"\bfrom\s+(\d+)\s+to\s+(\d+)\b", re.IGNORECASE)
_AVERAGE = re.compile(
    r"\b(?:average|mean)\b(?:\s+\w+){0,3}\s+(?:is|equals|was|were|to)\s+(\d+)\b",
    re.IGNORECASE,
)
_ROOT = re.compile(r"\b(?:square\s+root|sqrt)\s+of\s+(?:that|this|the|its)\b", re.IGNORECASE)
_NEGATIVE = re.compile(r"-\s*\d+")
_LOG = re.compile(r"\b(?:logarithm|log|ln)\s+of\s+(?:that|this|the|its)\b", re.IGNORECASE)
_NONPOSITIVE = re.compile(
    r"-\s*\d+|\b(?:is|equals|was|reads)\s+(?:0|zero)\b|\b(?:value|reading|change|result)\s+is\s+(?:0|zero)\b",
    re.IGNORECASE,
)
_FACTORIAL = re.compile(r"\bfactorial\s+of\s+(?:that|this|the|its)\b", re.IGNORECASE)
_ZERO_POWER = re.compile(
    r"\b(?:0+|zero)\b(?:\s+\w+){0,4}\s+(?:to\s+the\s+power|raised\s+to)\s+(?:that|this|the|its)\b",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"(\d+)\s*(?:percent|per\s+cent|%)", re.IGNORECASE)
_MONEY_ASK = re.compile(
    r"\b(?:save|saved|saving|currency|dollar|dollars|euro|euros|pound|pounds|price|cost|pay)\b",
    re.IGNORECASE,
)
_PRICE = re.compile(
    r"\b(?:price|priced|costs|cost|worth|tagged)\b(?:\s+\w+){0,3}\s+\d+"
    r"|\b\d+\s*(?:dollars|euros|pounds|cents)\b",
    re.IGNORECASE,
)
_REMAINDER_ASK = re.compile(
    r"\b(?:remain|remaining|left|still|afterwards|at the end)\b",
    re.IGNORECASE,
)

FEATURE_NAMES = [
    "missing_quantity",
    "divides_by_zero",
    "conflicting_claim",
    "removal_exceeds_stock",
    "average_outside",
    "root_of_named_negative",
    "log_of_named_nonpositive",
    "factorial_of_named_negative",
    "zero_to_named_power",
    "percent_without_base",
    "two_remain_claims",
]


def extract_math_features(instruction: str) -> dict:
    text = _problem(instruction)
    claims = [int(n) for n in _CLAIM.findall(text)]
    features = {
        "missing_quantity": _missing_quantity(text),
        "divides_by_zero": int(bool(_DIVZERO.search(text))),
        "conflicting_claim": _conflicting_claim(text, claims),
        "removal_exceeds_stock": _removal_exceeds(text),
        "average_outside": _average_outside(text),
        "root_of_named_negative": int(bool(_ROOT.search(text) and _NEGATIVE.search(text))),
        "log_of_named_nonpositive": int(bool(_LOG.search(text) and _NONPOSITIVE.search(text))),
        "factorial_of_named_negative": int(bool(_FACTORIAL.search(text) and _NEGATIVE.search(text))),
        "zero_to_named_power": _zero_power(text),
        "percent_without_base": _percent_without_base(text),
        "two_remain_claims": int(len(claims) >= 2 and len(set(claims)) > 1),
    }
    return features


def hole_score(instruction: str) -> int:
    features = extract_math_features(instruction)
    return sum(int(features[name]) for name in FEATURE_NAMES)


def _problem(instruction: str) -> str:
    text = re.sub(r"\bpython\d+\b", " ", instruction, flags=re.IGNORECASE)
    text = re.sub(r"\becho\s+\d+\b", " ", text, flags=re.IGNORECASE)
    return text


def _missing_quantity(text: str) -> int:
    hits = 0
    for sentence in re.split(r"[.!?]+", text):
        for cue in _CUES:
            match = cue.search(sentence)
            if not match:
                continue
            after = sentence[match.end(): match.end() + _REPAIR]
            if not re.search(r"\d", after):
                hits += 1
    return hits


def _conflicting_claim(text: str, claims: list[int]) -> int:
    if not claims:
        return 0
    claimed = claims[0]
    made = _MADE.search(text)
    outgoing = _OUT.search(text)
    if made and outgoing and claimed != int(made.group(1)) - int(outgoing.group(1)):
        return 1
    start = _START.search(text)
    away = _AWAY.search(text)
    if start and away and claimed != int(start.group(1)) - int(away.group(1)):
        return 1
    return 0


def _removal_exceeds(text: str) -> int:
    if not _REMAINDER_ASK.search(text):
        return 0
    for away in _AWAY.finditer(text):
        previous = [m for m in _START.finditer(text) if m.start() < away.start()]
        if not previous:
            continue
        if int(away.group(1)) > int(previous[-1].group(1)):
            return 1
    return 0


def _average_outside(text: str) -> int:
    bounds = _BETWEEN.search(text) or _FROM_TO.search(text)
    average = _AVERAGE.search(text)
    if not bounds or not average:
        return 0
    low, high = sorted((int(bounds.group(1)), int(bounds.group(2))))
    value = int(average.group(1))
    if value < low or value > high:
        return 1
    return 0


def _zero_power(text: str) -> int:
    if not _ZERO_POWER.search(text):
        return 0
    if _NEGATIVE.search(text) or re.search(r"\b(?:power|exponent)\b(?:\s+\w+){0,3}\s+(?:is|equals|was)\s+(?:0|zero)\b", text, re.IGNORECASE):
        return 1
    return 0


def _percent_without_base(text: str) -> int:
    percents = _PERCENT.findall(text)
    if not percents or not _MONEY_ASK.search(text) or _PRICE.search(text):
        return 0
    numbers = re.findall(r"\b\d+\b", text)
    extras = len(numbers) - len(percents)
    return int(extras == 0)


def build_dataset(tasks_dir: str, unsolvable_file: str):
    unsolvable = set(Path(unsolvable_file).read_text().split())
    rows, labels, task_ids = [], [], []
    for folder in sorted(Path(tasks_dir).iterdir()):
        meta_path = folder / "task.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("task_type") != "math":
            continue
        rows.append(extract_math_features(meta["instruction"]))
        labels.append(int(meta["task_id"] in unsolvable))
        task_ids.append(meta["task_id"])
    return rows, labels, task_ids
