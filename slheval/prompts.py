"""Prompt construction, option permutation and answer parsing."""
from __future__ import annotations

import hashlib
import random
import re

from .data import LETTERS

SYSTEM_PROMPT = (
    "You are answering a multiple-choice question about public health practice. "
    "Reply with the single letter of the best answer (A, B, C or D) and nothing else."
)


def permutation(item_id, rep, seed):
    """Deterministic shuffle of option positions. perm[i] is the original option index shown at position i."""
    digest = hashlib.sha256(f"{seed}|{item_id}|{rep}".encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    perm = [0, 1, 2, 3]
    rng.shuffle(perm)
    return perm


def build_prompt(question, options, perm):
    shown = [options[j] for j in perm]
    lines = [f"Question: {question}", ""]
    lines += [f"{letter}. {text}" for letter, text in zip(LETTERS, shown)]
    lines += ["", "Answer with the letter only."]
    return "\n".join(lines)


def correct_letter(answer, perm):
    return LETTERS[perm.index(answer)]


def content_index(letter, perm):
    """Map a displayed letter back to the original option index."""
    return perm[LETTERS.index(letter)]


# Strict parsing. A reply such as "A patient with fever ..." must not be read as the letter A.
_LETTER_ONLY = re.compile(r"^\s*\**\(?([A-D])\)?[.):]?\**\s*$")
_LETTER_THEN_TEXT = re.compile(r"^\s*\**\(?([A-D])[.):]\**\s+\S")
_ANSWER_PHRASE = re.compile(r"(?i:answer|option|choice)(?:\s+is)?\s*:?\s*\**\(?([A-D])\)?(?![A-Za-z])")


def parse_letter(text):
    """Return 'A'..'D' or None if the reply cannot be read unambiguously."""
    if not text:
        return None
    m = _LETTER_ONLY.match(text) or _LETTER_THEN_TEXT.match(text)
    if m:
        return m.group(1)
    found = _ANSWER_PHRASE.findall(text)
    if found:
        return found[-1]
    return None
