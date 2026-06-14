"""AI dependency classification for combinatorial arbitrage.

The research uses an LLM (DeepSeek-R1-Distill-Qwen-32B in the paper) to read
two market descriptions and emit the set of *feasible joint outcomes* — the
logical constraints that turn 2^n brute force into a small marginal polytope.

Here we implement two interchangeable classifiers behind one interface:

  * HeuristicClassifier -- rule-based implication detection (shared subject +
    margin/superset keywords). Runs fully offline, no credentials. Catches the
    canonical "Republicans win PA by 5+  ⇒  Trump wins PA" style dependency.

  * ClaudeClassifier   -- uses the Anthropic SDK (claude-opus-4-8) to classify
    arbitrary market pairs into feasible joint worlds, with a strict JSON
    schema. Enabled automatically when ANTHROPIC_API_KEY is set.

A feasible "world" is a 0/1 assignment over the two markets' YES outcomes.
We expand each world into a payoff vector over all four tradeable tokens
(A_YES, A_NO, B_YES, B_NO) so the LP in arbitrage.detect_combinatorial can
search for a guaranteed-profit portfolio that may hold YES *or* NO legs.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .arbitrage import detect_combinatorial
from .models import Market, Opportunity


@dataclass
class DependencyResult:
    relationship: str            # e.g. "B implies A", "mutually_exclusive"
    feasible_worlds: list[tuple[int, int]]  # allowed (A_yes, B_yes) assignments
    confidence: float


# All four joint assignments of two binary markets.
_ALL_WORLDS = [(1, 1), (1, 0), (0, 1), (0, 0)]


class HeuristicClassifier:
    """Rule-based: detect when one market is a strict sub-condition of another.

    If market B's question is a *stronger* version of A's (same subject, plus a
    margin/threshold qualifier), then B ⇒ A and the world (A=0, B=1) is
    infeasible. Everything else is treated as independent (no combinatorial
    edge beyond the single-market detectors).
    """

    _MARGIN_HINTS = re.compile(
        r"\b(by\s+\d+|\d+\+|\d+\s*or\s+more|landslide|by\s+a\s+margin|"
        r"5\+|10\+|sweep|supermajority)\b",
        re.IGNORECASE,
    )
    _STOPWORDS = {
        "will", "the", "a", "an", "win", "be", "in", "on", "of", "to", "by",
        "for", "at", "and", "or", "this", "that", "with", "?",
    }

    def _keywords(self, q: str) -> set[str]:
        words = re.findall(r"[a-z0-9]+", q.lower())
        return {w for w in words if w not in self._STOPWORDS and len(w) > 2}

    def classify(self, a: Market, b: Market) -> Optional[DependencyResult]:
        ka, kb = self._keywords(a.question), self._keywords(b.question)
        if not ka or not kb:
            return None
        overlap = ka & kb
        # Need meaningful shared subject.
        if len(overlap) < 2:
            return None

        a_margin = bool(self._MARGIN_HINTS.search(a.question))
        b_margin = bool(self._MARGIN_HINTS.search(b.question))
        if b_margin and not a_margin:
            # B is the stronger claim ⇒ B implies A. (A=0,B=1) impossible.
            worlds = [w for w in _ALL_WORLDS if w != (0, 1)]
            return DependencyResult("B implies A", worlds, 0.75)
        if a_margin and not b_margin:
            worlds = [w for w in _ALL_WORLDS if w != (1, 0)]
            return DependencyResult("A implies B", worlds, 0.75)
        return None


class ClaudeClassifier:
    """LLM-backed classifier using the Anthropic SDK (claude-opus-4-8)."""

    _SCHEMA = {
        "type": "object",
        "properties": {
            "relationship": {
                "type": "string",
                "description": "Short description of the logical relationship.",
            },
            "feasible_worlds": {
                "type": "array",
                "description": (
                    "Every logically possible joint outcome as [A_yes, B_yes], "
                    "where 1 means that market resolves YES and 0 means NO."
                ),
                "items": {
                    "type": "array",
                    "items": {"type": "integer", "enum": [0, 1]},
                },
            },
        },
        "required": ["relationship", "feasible_worlds"],
        "additionalProperties": False,
    }

    def __init__(self):
        self._client = None
        self._cache: dict[tuple[str, str], Optional[DependencyResult]] = {}

    def _anthropic(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def classify(self, a: Market, b: Market) -> Optional[DependencyResult]:
        key = (a.question, b.question)
        if key in self._cache:
            return self._cache[key]

        prompt = (
            "Two binary prediction markets:\n"
            f"  A: {a.question}\n"
            f"  B: {b.question}\n\n"
            "Determine the logical relationship between A and B. Return the set "
            "of feasible joint outcomes as [A_yes, B_yes] pairs. Exclude any "
            "joint outcome that is logically impossible (e.g. if B logically "
            "implies A, then [0,1] is impossible). If A and B are fully "
            "independent, return all four combinations."
        )
        try:
            resp = self._anthropic().messages.create(
                model="claude-opus-4-8",
                max_tokens=1024,
                thinking={"type": "adaptive"},
                output_config={"format": {"type": "json_schema", "schema": self._SCHEMA}},
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            text = next(blk.text for blk in resp.content if blk.type == "text")
            data = json.loads(text)
            worlds = [tuple(int(x) for x in w) for w in data["feasible_worlds"]
                      if len(w) == 2]
            worlds = [w for w in worlds if w in _ALL_WORLDS]
            if not worlds or len(worlds) == 4:
                result = None  # independent or unusable → no combinatorial edge
            else:
                result = DependencyResult(data.get("relationship", "dependent"),
                                          worlds, 0.81)
        except Exception as exc:  # network/credential/parse failure → skip
            print(f"[dependencies] Claude classify failed: {exc}")
            result = None

        self._cache[key] = result
        return result


def make_classifier():
    """Claude classifier when credentials exist, else the offline heuristic."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return ClaudeClassifier()
    return HeuristicClassifier()


def _token_columns(a: Market, b: Market):
    """Columns = [A_YES, A_NO, B_YES, B_NO] with (token_id, label)."""
    a_yes, a_no = a.outcomes[0], a.outcomes[1]
    b_yes, b_no = b.outcomes[0], b.outcomes[1]
    return [
        (a_yes.token_id, f"{a.question[:18]}:YES"),
        (a_no.token_id, f"{a.question[:18]}:NO"),
        (b_yes.token_id, f"{b.question[:18]}:YES"),
        (b_no.token_id, f"{b.question[:18]}:NO"),
    ]


def combinatorial_opportunity(
    a: Market, b: Market, result: DependencyResult
) -> Optional[Opportunity]:
    """Expand a dependency into a payoff matrix and run the LP detector."""
    if len(a.outcomes) != 2 or len(b.outcomes) != 2:
        return None
    labels = _token_columns(a, b)
    # Payoff of [A_YES, A_NO, B_YES, B_NO] in each feasible world (av, bv).
    rows = [[av, 1 - av, bv, 1 - bv] for (av, bv) in result.feasible_worlds]
    feasible = np.array(rows, dtype=float)
    opp = detect_combinatorial([a, b], feasible, labels)
    if opp:
        opp.confidence = min(opp.confidence, result.confidence)
        opp.description = f"{result.relationship}: {opp.description}"
    return opp


def scan_combinatorial(markets: list[Market], classifier, max_pairs: int = 60):
    """Classify binary-market pairs and detect cross-market arbitrage."""
    binaries = [m for m in markets
                if len(m.outcomes) == 2 and not m.mutually_exclusive]
    found: list[Opportunity] = []
    checked = 0
    for i in range(len(binaries)):
        for j in range(i + 1, len(binaries)):
            if checked >= max_pairs:
                return found
            checked += 1
            res = classifier.classify(binaries[i], binaries[j])
            if res is None:
                continue
            opp = combinatorial_opportunity(binaries[i], binaries[j], res)
            if opp:
                found.append(opp)
    return found
