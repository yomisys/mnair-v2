"""Tests for app.services.quiz_shuffle.

Root cause this exists to catch a regression of: curriculum content has
the correct answer disproportionately in option A (66% of all 875 quiz
questions across the platform, verified during investigation), so quiz
delivery has to randomize option order per question rather than trusting
content to already be randomized.
"""
import pytest

from app.services.quiz_shuffle import (
    generate_shuffle,
    get_or_create_shuffle,
    shuffled_options,
    unshuffle_answer,
)


def test_generate_shuffle_is_a_permutation():
    order = generate_shuffle(4)
    assert sorted(order) == [0, 1, 2, 3]


def test_shuffle_and_unshuffle_round_trip():
    """Whatever original index ends up at a given display position, looking
    that position back up must return the same original index."""
    options = ["A text", "B text", "C text", "D text"]
    order = [2, 0, 3, 1]

    displayed = shuffled_options(options, order)
    assert displayed == ["C text", "A text", "D text", "B text"]

    for display_position, original_index in enumerate(order):
        assert unshuffle_answer(display_position, order) == original_index


def test_correct_answer_is_not_always_in_display_position_zero():
    """The actual bug: across many quiz deliveries, option A must not
    always be where the correct answer lands. Without shuffling, this
    would fail 100% of the time — a question with correct=0 would always
    display it at position 0."""
    landed_positions = set()
    for _ in range(200):
        order = generate_shuffle(4)
        # correct answer is always original index 0 in this scenario
        # (matching the real curriculum's dominant pattern) — where does
        # it land after shuffling?
        display_position = order.index(0)
        landed_positions.add(display_position)

    # Over 200 trials, the correct answer must have landed somewhere
    # other than position 0 at least once. (Odds of failing this by
    # chance if shuffling actually works: (1/4)^200, indistinguishable
    # from zero.)
    assert landed_positions != {0}, (
        "correct answer landed at display position 0 every single time — "
        "shuffling isn't actually happening"
    )


def test_get_or_create_shuffle_creates_once_then_reuses():
    """A resend of the same question (invalid reply, CONTINUE after a
    timeout, etc.) must show the exact same order the learner already
    saw — the order can't be regenerated on every call."""
    context = {}
    order1, context = get_or_create_shuffle(context, question_num=0, num_options=4)
    order2, context = get_or_create_shuffle(context, question_num=0, num_options=4)
    assert order1 == order2
    assert context["quiz_shuffle"]["0"] == order1


def test_get_or_create_shuffle_is_independent_per_question():
    context = {}
    order_q0, context = get_or_create_shuffle(context, question_num=0, num_options=4)
    order_q1, context = get_or_create_shuffle(context, question_num=1, num_options=4)
    assert context["quiz_shuffle"]["0"] == order_q0
    assert context["quiz_shuffle"]["1"] == order_q1


def test_get_or_create_shuffle_does_not_mutate_input_context():
    """Callers (engine/USSD handlers) rely on identity comparison
    (`new_context is not conversation.context`) to decide whether a DB
    commit is needed — this only works if an unchanged context is
    returned as the *same* object, and a changed one is a *new* dict."""
    context = {"some_other_key": "value"}
    order, new_context = get_or_create_shuffle(context, question_num=0, num_options=4)
    assert new_context is not context
    assert context == {"some_other_key": "value"}  # original untouched

    same_order, same_context = get_or_create_shuffle(new_context, question_num=0, num_options=4)
    assert same_context is new_context  # no new shuffle needed -> same object
