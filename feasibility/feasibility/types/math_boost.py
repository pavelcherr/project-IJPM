"""CatBoost second pass for math tasks the rules leave through.

The rules catch a missing digit and an undefined operation written next to
the operator. This model catches the same holes in other words: a quantity
that is named and never given, two remainders that disagree, a percent with
no price, an average outside its own range, a root or log of a value the
text already called negative. It never overrides a rule: the caller asks it
only after the rules say the task is feasible.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3] / "math_classifier"
_MODEL = _ROOT / "model.cbm"
_NAMES = _ROOT / "feature_names.pkl"

_ready = False
_model = None
_feature_names: list[str] = []


def unsolvable(instruction: str) -> str | None:
    if not _load():
        return None
    from feature_extraction import extract_math_features

    features = extract_math_features(instruction)
    vector = [features.get(name, 0) for name in _feature_names]
    proba = _model.predict_proba([vector])[0]
    classes = [int(item) for item in _model.classes_]
    probability = float(proba[classes.index(1)])
    if probability >= 0.5:
        return f"модель: условие не задаёт один ответ ({probability:.2f})"
    return None


def _load() -> bool:
    global _ready, _model, _feature_names
    if _ready:
        return _model is not None
    _ready = True
    if not _MODEL.is_file() or not _NAMES.is_file():
        return False
    try:
        from catboost import CatBoostClassifier
    except ImportError:
        return False
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    model = CatBoostClassifier()
    model.load_model(str(_MODEL))
    with _NAMES.open("rb") as handle:
        names = pickle.load(handle)
    _model = model
    _feature_names = list(names)
    return True
