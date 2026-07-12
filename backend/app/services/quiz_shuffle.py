"""Per-question answer-order shuffling for quiz delivery.

Root cause this exists to fix: curriculum content across the platform has
the correct answer disproportionately in option A (verified: 66% of all
875 quiz questions have correct=0, and correct=3 never appears at all).
The content itself isn't mislabeled -- option A genuinely is the right
answer where it's marked -- but with no randomization at delivery time, a
learner can pass every quiz by always picking the first option.

Rather than hand-editing 175 curriculum files (which also wouldn't stop
the same defect recurring in future content), delivery is shuffled per
question instead. The correct answer's *index* in the database never
changes -- only the *order* options are displayed in, per question, per
attempt. Grading still compares against the original stored index, so
nothing downstream (lesson_state.py, quiz_attempt.py, lesson.py) needed
to change.

The shuffle must be stored (not regenerated) once a question has been
shown, so that a resend -- CONTINUE after a timeout, an invalid reply,
re-fetching the same question -- shows the exact same order the learner
already saw, and their answer is interpreted against that same order.
"""
from __future__ import annotations

import random


def generate_shuffle(num_options: int) -> list[int]:
    """A random permutation of option indices. order[display_position] =
    original_index -- i.e. this says what original option to show at each
    displayed position."""
    order = list(range(num_options))
    random.shuffle(order)
    return order


def shuffled_options(options: list[str], order: list[int]) -> list[str]:
    """Reorder option text for display according to `order`."""
    return [options[i] for i in order]


def unshuffle_answer(display_position: int, order: list[int]) -> int:
    """Convert the position a learner picked (in the order they were shown)
    back to that option's original index in the stored quiz data."""
    return order[display_position]


def get_or_create_shuffle(context: dict, question_num: int, num_options: int) -> tuple[list[int], dict]:
    """Look up the stored shuffle order for a question, or create one.

    Pure function -- returns (order, updated_context). Callers own
    persisting updated_context (it's unchanged, same object, if a shuffle
    already existed -- only a fresh dict when a new one was created).
    """
    shuffles = dict(context.get("quiz_shuffle", {}))
    key = str(question_num)
    if key in shuffles:
        return shuffles[key], context

    order = generate_shuffle(num_options)
    shuffles[key] = order
    updated_context = {**context, "quiz_shuffle": shuffles}
    return order, updated_context
