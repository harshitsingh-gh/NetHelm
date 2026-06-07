"""Inspect AI scorer wrapping the netbrace grader. Requires inspect-ai (install with [eval])."""

from __future__ import annotations


def blast_radius_scorer():
    """Return an Inspect AI scorer that grades blast-radius predictions.

    Wraps the existing grade() function. The dataset target must be the
    task's oracle.blast_radius serialized as JSON text.
    """
    from inspect_ai.scorer import Score, mean, scorer, stderr

    from netbrace.core.schemas import BlastRadius
    from netbrace.evals.parser import parse_prediction
    from netbrace.graders.safety import grade

    @scorer(metrics=[mean(), stderr()])
    def _scorer():
        async def score(state, target):
            pred = parse_prediction(state.output.completion)
            truth = BlastRadius.model_validate_json(target.text)
            sr = grade(pred, truth, task_id=state.sample_id or "")
            return Score(
                value=sr.macro_f1,
                answer=state.output.completion,
                metadata=sr.model_dump(),
            )
        return score

    return _scorer()
