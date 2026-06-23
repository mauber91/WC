from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace(",", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def name_tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in normalize_name(value).split() if token)


def names_match(left: str, right: str, *, threshold: float = 0.88) -> bool:
    a = normalize_name(left)
    b = normalize_name(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    left_tokens = name_tokens(left)
    right_tokens = name_tokens(right)
    if left_tokens and right_tokens and sorted(left_tokens) == sorted(right_tokens):
        return True
    if left_tokens and right_tokens and left_tokens[-1] == right_tokens[-1]:
        if left_tokens[0][:1] == right_tokens[0][:1]:
            return True
    return SequenceMatcher(None, a, b).ratio() >= threshold


def best_name_match(needle: str, choices: dict[str, str]) -> str | None:
    for key, label in choices.items():
        if names_match(needle, label):
            return key
    return None
