"""
Turns the LLM's per-requirement assessments into a score.

The LLM only judges each requirement and quotes evidence. The score itself
is computed here with fixed, documented weights, so it is reproducible and
explainable. Evidence that cannot be found in the CV is not trusted.
"""
import re
from difflib import SequenceMatcher

from app.models import (
    LLMRequirementAssessment,
    MatchLevel,
    MatchStatus,
    Priority,
    Requirement,
    RequirementAssessment,
)


MUST_HAVE_WEIGHT = 0.7
NICE_TO_HAVE_WEIGHT = 0.3
STATUS_VALUE = {MatchStatus.MET: 1.0, MatchStatus.PARTIAL: 0.5, MatchStatus.NOT_MET: 0.0}
STRONG_MATCH_SCORE = 75
PARTIAL_MATCH_SCORE = 50
MIN_EVIDENCE_CHARS = 3
FUZZY_MATCH_RATIO = 0.85

# Flags that mean a person has to look at the CV before any ranking is trusted
MANUAL_REVIEW_FLAGS = {
    "unreadable_file",
    "no_extractable_text",
    "possible_prompt_injection",
    "screening_failed",
}


def _normalize(text: str) -> str:
    text = text.lower().replace("…", " ").replace("...", " ")
    text = re.sub(r"[\"'`“”‘’]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def evidence_in_cv(evidence: str, cv_text: str) -> bool:
    """
    True if the quoted evidence appears in the CV, allowing for small
    differences in whitespace, quotes and punctuation.
    """
    quote = _normalize(evidence)
    if len(quote) < MIN_EVIDENCE_CHARS:
        return False
    source = _normalize(cv_text)
    if quote in source:
        return True
    match = SequenceMatcher(None, source, quote, autojunk=False).find_longest_match(
        0, len(source), 0, len(quote)
    )
    return match.size / len(quote) >= FUZZY_MATCH_RATIO


def _downgrade(status: MatchStatus) -> MatchStatus:
    return MatchStatus.PARTIAL if status == MatchStatus.MET else MatchStatus.NOT_MET


def build_assessments(
    requirements: list[Requirement],
    llm_assessments: list[LLMRequirementAssessment],
    cv_text: str,
) -> tuple[list[RequirementAssessment], bool]:
    """
    Matches the LLM's answers to the requirements and checks the evidence.
    A met/partial claim without verifiable evidence is downgraded one level.
    Returns the assessments and whether any claim had to be downgraded.
    """
    by_name = {_normalize(a.requirement): a for a in llm_assessments}
    downgraded = False
    results = []

    for i, requirement in enumerate(requirements):
        answer = by_name.get(_normalize(requirement.name))
        if answer is None and i < len(llm_assessments) and len(llm_assessments) == len(requirements):
            answer = llm_assessments[i]

        if answer is None:
            results.append(RequirementAssessment(
                requirement=requirement.name, priority=requirement.priority, status=MatchStatus.NOT_MET,
            ))
            continue

        status = answer.status
        verified = status != MatchStatus.NOT_MET and evidence_in_cv(answer.evidence, cv_text)
        if status != MatchStatus.NOT_MET and not verified:
            status = _downgrade(status)
            downgraded = True

        results.append(RequirementAssessment(
            requirement=requirement.name,
            priority=requirement.priority,
            status=status,
            evidence=answer.evidence if answer.status != MatchStatus.NOT_MET else "",
            evidence_verified=verified,
        ))

    return results, downgraded


def compute_score(assessments: list[RequirementAssessment]) -> int:
    """
    Weighted score from 0 to 100: must-haves count 70%, nice-to-haves 30%.
    If one group is empty, the other counts 100%.
    """
    groups = {
        Priority.MUST_HAVE: [a for a in assessments if a.priority == Priority.MUST_HAVE],
        Priority.NICE_TO_HAVE: [a for a in assessments if a.priority == Priority.NICE_TO_HAVE],
    }
    weights = {Priority.MUST_HAVE: MUST_HAVE_WEIGHT, Priority.NICE_TO_HAVE: NICE_TO_HAVE_WEIGHT}
    active = {p: weights[p] for p, items in groups.items() if items}
    if not active:
        return 0

    total_weight = sum(active.values())
    score = sum(
        (weight / total_weight) * sum(STATUS_VALUE[a.status] for a in groups[p]) / len(groups[p])
        for p, weight in active.items()
    )
    return round(score * 100)


def match_level(score: int, assessments: list[RequirementAssessment], flags: list[str]) -> MatchLevel:
    if MANUAL_REVIEW_FLAGS & set(flags):
        return MatchLevel.MANUAL_REVIEW
    must_haves = [a for a in assessments if a.priority == Priority.MUST_HAVE]
    all_must_haves_met = all(a.status == MatchStatus.MET for a in must_haves)
    if score >= STRONG_MATCH_SCORE and all_must_haves_met:
        return MatchLevel.STRONG
    if score >= PARTIAL_MATCH_SCORE:
        return MatchLevel.PARTIAL
    return MatchLevel.WEAK
