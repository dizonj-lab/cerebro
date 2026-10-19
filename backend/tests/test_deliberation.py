"""Keeping the model's deliberation off the screen.

Reasoning models were asked for `think: false`, which stops them emitting
<think> tags — and not, it turns out, from deliberating. qwen3 simply moved
its reasoning into plain prose, where nothing was looking for it, and it
reached Assisted Recollection as though it were the answer: the question
restated, the passages counted, and the rules it had been given listed back
to the user.

Two changes, tested here. The instructions moved into the system role, so
they are no longer material in the prompt for the model to summarise. And an
untagged-deliberation filter sits at the daemon boundary, both for a whole
response and chunk by chunk as it streams.

The filter is a heuristic, so the tests that matter most are the ones that
say what it must *not* remove.
"""
import pytest

from app.services import ollama
from app.services.ollama import _PreambleFilter, strip_deliberation

# Verbatim from the reported failure.
REPORTED = """We are given a question: "recommend knowledge if i want to learn a transformer"

We have 6 passages (labeled [1] to [6]) that the user has uploaded and approved.

We must answer as a colleague who has read the passages, in plain prose, in our own words.

Key rules:
- Start with the answer, no "Based on the passages" etc.
- Refer to documents by their name (e.g., "the retention policy says…")
- Put a citation [X] after a specific claim that a reader might want to check
- Continuous prose, only list if asked for

Your course notes cover transformers in the attention module [3], and the IRS
proposal sets out the architecture in its background section [2]."""

ANSWER = (
    "Your course notes cover transformers in the attention module [3], and the IRS\n"
    "proposal sets out the architecture in its background section [2]."
)


# --- whole responses --------------------------------------------------------

def test_the_reported_leak_is_removed_and_the_answer_survives():
    assert strip_deliberation(REPORTED) == ANSWER


@pytest.mark.parametrize(
    "preamble",
    [
        "We are given a question about embeddings.",
        "The user is asking about retention.",
        "Okay, so the question concerns provenance.",
        "Let me look at what the documents say.",
        "First, I need to find the relevant passage.",
        "I'll start by checking the proposal.",
        "The task is to answer from the passages only.",
        "Looking at the passages, there are four of them.",
        "Key rules:\n- Start with the answer\n- Cite claims\n- Use prose",
        "Instructions:\n- Answer directly\n- Do not invent\n- Cite sources",
    ],
)
def test_each_shape_of_deliberation_is_recognised(preamble):
    assert strip_deliberation(f"{preamble}\n\n{ANSWER}") == ANSWER


# --- what must survive ------------------------------------------------------

def test_a_plain_answer_is_untouched():
    assert strip_deliberation(ANSWER) == ANSWER


def test_deliberation_shaped_prose_inside_a_real_answer_survives():
    """"We have" is an ordinary way to begin a sentence mid-answer."""
    answer = (
        "The retention policy keeps records for seven years [1].\n\n"
        "We have two exceptions to that, both in the appendix [2]."
    )
    assert strip_deliberation(answer) == answer


def test_an_answer_that_opens_with_we_have_is_not_eaten():
    """A risk of the heuristic: the filter must not swallow the whole reply."""
    answer = "We have no document covering transformers, only the IRS proposal [1]."
    # Every paragraph reads as deliberation, so the original is returned
    # rather than nothing at all.
    assert strip_deliberation(answer) == answer


def test_an_empty_or_blank_response_is_returned_as_is():
    assert strip_deliberation("") == ""
    assert strip_deliberation("   \n  ") == "   \n  "


def test_a_json_reply_is_never_mistaken_for_deliberation():
    body = '{"title": "We have a plan", "topics": ["Let me think"]}'
    assert strip_deliberation(body) == body


# --- streaming --------------------------------------------------------------

def stream_through(text: str, size: int = 7) -> str:
    """Feed text through the filter in small chunks, as the daemon would."""
    filter_ = _PreambleFilter()
    out = [filter_.feed(text[i : i + size]) for i in range(0, len(text), size)]
    out.append(filter_.flush())
    return "".join(out)


def test_nothing_of_the_reported_leak_is_ever_streamed():
    streamed = stream_through(REPORTED)

    assert "Key rules" not in streamed
    assert "We are given" not in streamed
    assert "labeled [1] to [6]" not in streamed
    assert "attention module [3]" in streamed


def test_a_normal_answer_streams_without_being_held_back():
    """An answer that does not open with deliberation must not be delayed."""
    filter_ = _PreambleFilter()
    long_enough = ANSWER + " " * 100

    released = "".join(
        filter_.feed(long_enough[i : i + 7]) for i in range(0, len(long_enough), 7)
    )
    # Released during the stream, not only at flush.
    assert "attention module" in released
    assert filter_.flush() == ""


def test_a_short_answer_still_streams_word_by_word():
    """The filter must not turn a streamed reply into one that lands at once.

    Deciding from the first word is what makes this true: holding every
    response back until enough text arrived to run the full pattern would
    cost every answer its streaming.
    """
    filter_ = _PreambleFilter()
    released = [filter_.feed(piece) for piece in ("Seven", " years", " [1]", ".")]

    assert [r for r in released if r] == ["Seven", " years", " [1]", "."]
    assert filter_.flush() == ""


def test_an_answer_opening_with_a_common_word_is_barely_delayed():
    """"The" begins both "The user is asking…" and most ordinary answers.

    It cannot be released on sight, but it must be released as soon as the
    pattern is ruled out — not held for a whole paragraph, which is what an
    eighty-character window did.
    """
    filter_ = _PreambleFilter()
    words = "The retention schedule is seven years [1].".split()

    released = [filter_.feed(word + " ") for word in words]
    held = [i for i, r in enumerate(released) if not r]

    assert held == [0, 1, 2, 3], "released once the opener is ruled out"
    assert "The retention schedule" in "".join(released)
    assert filter_.flush().strip() in ("", "[1].")


def test_a_model_that_only_deliberates_still_yields_its_text():
    """Nothing is better than something only when something is wrong."""
    only_thinking = "We are given a question.\n\nWe must answer it."
    assert stream_through(only_thinking).strip() == only_thinking.strip()


def test_deliberation_past_the_cap_is_released_rather_than_lost():
    """A runaway preamble must not swallow the answer with it."""
    runaway = "We are given a question.\n\n" + ("We consider it. " * 400) + "\n\n" + ANSWER
    assert len(runaway) > ollama._PREAMBLE_CAP
    streamed = stream_through(runaway, size=200)
    assert "attention module [3]" in streamed


# --- the prompt itself ------------------------------------------------------

def test_the_rules_are_sent_as_system_not_as_prompt_material():
    """The cause, not the symptom: rules in the body get summarised back."""
    from app.services import recall

    body = recall._prompt("what is a transformer?", [], None)

    assert "Key rules" not in body
    assert "Start with the answer" not in body
    assert "what is a transformer?" in body
    # The rules still exist — just somewhere the model treats as instruction.
    assert "Start with the answer" in recall._SYSTEM
    assert "Do not narrate your reasoning" in recall._SYSTEM


def test_the_daemon_is_told_the_system_role():
    """A system prompt that never reaches the request body does nothing."""
    import inspect

    source = inspect.getsource(ollama.generate_stream)
    assert 'body["system"] = system' in source
