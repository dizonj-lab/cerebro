"""Statistical keyphrase extraction.

Scores candidate phrases by how often they occur and how specific they are,
then returns the strongest. Every phrase returned is a sequence of words that
literally appears in the document — the method cannot produce a topic the
text does not contain, which is exactly the property wanted here.

It is frequency statistics, not understanding. A document can be about
something it never names, and this will miss it.

Two rules keep the output worth reading rather than merely plentiful:

* **Recurrence is the evidence.** A phrase the document uses once is a phrase
  the document happened to contain. Topics and tags both require repetition,
  so an incidental word cannot become a subject heading.
* **Proper nouns lead the tags.** A word the document capitalises
  mid-sentence is naming something — a company, a product, a place — which is
  what a tag is useful for. Frequency alone surfaces words like "driven" or
  "represents", which are true of the text and useless as tags.
"""
from __future__ import annotations

import re
from collections import Counter

_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]+|\d{4}")

# Function words and discourse filler carry no topical signal. Longer than a
# classic stoplist because the weak words that survive frequency scoring are
# exactly these: verbs of saying and doing, vague quantities, and connectives.
_STOPWORDS = frozenset("""
a about above after again against all also am an and any are aren as at be
because been before being below between both but by can cannot could did do
does doing don down during each few for from further had has have having he
her here hers herself him himself his how i if in into is it its itself just
me more most my myself no nor not of off on once only or other ought our ours
ourselves out over own same she should so some such than that the their theirs
them themselves then there these they this those through to too under until up
very was we were what when where which while who whom why will with would you
your yours yourself yourselves upon shall may might must whose via etc
use used using one two three new within whether however therefore thus
across among around back based become becomes becoming came come comes
driven drive drives due even ever every follow following gave give given
gives goes going gone got great held help high however included includes
including keep known large last later least less let like made make makes
making many much need needs next now often per place put rather represent
represents required requires said say says see seen several show shows since
still take taken takes tell than thing things though time times together
toward towards try trying turn under upon various want way well went whole
work works year years able almost along already although always another
anything because before began begin behind best better beyond both bring
brought call called case cases certain change changes clear common course
currently day days described different done early end enough especially
example far find found full general get good hand however
""".split())

_MAX_PHRASE_WORDS = 3
_MIN_WORD_LENGTH = 3
_MIN_OCCURRENCES = 2
_PROPER_NOUN_RATIO = 0.5
_MAX_SINGLE_WORD_TOPICS = 3


def _sentences(text: str) -> list[list[tuple[str, str]]]:
    """Sentences as lists of (lowercase, original) words.

    Sentence boundaries matter twice: a phrase may not span one, and a word
    capitalised only at the start of a sentence is not evidence of a proper
    noun.
    """
    out: list[list[tuple[str, str]]] = []
    for segment in re.split(r"[.!?;:\n\r\t()\[\]{}\"“”|]+", text):
        words = [(w.lower(), w) for w in _WORD.findall(segment)]
        if words:
            out.append(words)
    return out


def _forms(sentences: list[list[tuple[str, str]]]) -> dict[str, str]:
    """The spelling the document uses most often for each term.

    Needed because a name can be sentence-initial every time it appears —
    "Acme Corp met with…", "Acme Corp agreed…" — so its capital is never
    mid-sentence evidence, yet "Acme" is still how the document writes it.
    """
    forms: dict[str, Counter] = {}
    for words in sentences:
        for lower, original in words:
            forms.setdefault(lower, Counter())[original] += 1
    return {term: counter.most_common(1)[0][0] for term, counter in forms.items()}


def _proper_nouns(sentences: list[list[tuple[str, str]]], forms: dict[str, str]) -> set[str]:
    """Terms the document treats as names.

    A term qualifies when it is capitalised in most of its occurrences *and*
    its usual spelling is capitalised. Position is not used: a name can be
    sentence-initial every time it appears, as "Globex" was in testing, and
    requiring mid-sentence evidence missed exactly the words most worth
    tagging. An ordinary word that starts the odd sentence still fails the
    ratio, because its usual spelling is lowercase.
    """
    seen: Counter = Counter()
    capitalised: Counter = Counter()
    for words in sentences:
        for lower, original in words:
            seen[lower] += 1
            if original[:1].isupper():
                capitalised[lower] += 1

    return {
        term
        for term, capitals in capitalised.items()
        if capitals / seen[term] >= _PROPER_NOUN_RATIO
        and forms.get(term, "")[:1].isupper()
    }


def _candidates(sentences: list[list[tuple[str, str]]]) -> Counter:
    """Phrases of 1..3 content words, not crossing a break or a stopword."""
    counts: Counter = Counter()

    def flush(run: list[str]) -> None:
        for size in range(1, _MAX_PHRASE_WORDS + 1):
            for start in range(len(run) - size + 1):
                phrase = run[start : start + size]
                counts[" ".join(phrase)] += 1

    for words in sentences:
        run: list[str] = []
        for lower, _original in words:
            if lower in _STOPWORDS or len(lower) < _MIN_WORD_LENGTH:
                flush(run)
                run = []
                continue
            run.append(lower)
        flush(run)
    return counts


def _score(phrase: str, count: int) -> float:
    """Repetition first, specificity second.

    An earlier version weighted specificity heavily enough that
    single-occurrence trigrams outranked terms the document used repeatedly,
    which filled the topics with overlapping noise.
    """
    return count * (1.0 + 0.6 * (len(phrase.split()) - 1))


def extract(text: str, *, topics: int = 6, tags: int = 8) -> tuple[list[str], list[str]]:
    """Topics (phrases) and tags (single words), both drawn from the text.

    Returns two disjoint lists, either of which may be empty. A document with
    nothing recurring gets nothing: a list padded to look thorough is a list
    of claims the document does not support.
    """
    sentences = _sentences(text)
    total = sum(len(s) for s in sentences)
    if total < 5:
        # Too little text for frequency to mean anything.
        return [], []

    counts = _candidates(sentences)
    if not counts:
        return [], []
    forms = _forms(sentences)
    proper = _proper_nouns(sentences, forms)

    # Drop a phrase wholly contained in a longer one that occurs just as
    # often: the longer phrase says the same thing more precisely.
    redundant = {
        short
        for short in counts
        for long in counts
        if short != long
        and f" {short} " in f" {long} "
        and counts[long] >= counts[short]
    }

    recurring = sorted(
        (
            (p, _score(p, c))
            for p, c in counts.items()
            if c >= _MIN_OCCURRENCES and p not in redundant
        ),
        key=lambda pair: (-pair[1], pair[0]),
    )
    # Short documents where nothing repeats still deserve something, but
    # little of it, and only as topics — a once-only word is too weak to tag.
    once = sorted(
        (
            (p, _score(p, c))
            for p, c in counts.items()
            if c == 1 and p not in redundant and " " in p
        ),
        key=lambda pair: (-pair[1], pair[0]),
    )[:3]

    chosen: list[str] = []
    singles_used = 0
    for phrase, _ in recurring or once:
        words = set(phrase.split())
        # Never two topics naming the same thing.
        if any(words & set(other.lower().split()) for other in chosen):
            continue
        if " " not in phrase:
            # Single words are capped as topics so the tag list is not
            # starved: a tag is a single word by definition, and topics that
            # swallow every one of them leave nothing to tag with.
            if singles_used >= _MAX_SINGLE_WORD_TOPICS:
                continue
            singles_used += 1
        chosen.append(phrase)
        if len(chosen) == topics:
            break

    taken = {t.lower() for t in chosen}
    # Tags are single recurring words that are not already a topic. Proper
    # nouns first: they name things, which is what a tag is for.
    singles = [(w, score) for w, score in recurring if " " not in w and w not in taken]
    singles.sort(key=lambda pair: (pair[0] not in proper, -pair[1], pair[0]))
    # Rendered as the document writes them, which gives names their capitals
    # without having to decide what is a name a second time.
    chosen_tags = [forms.get(w, w) for w, _ in singles][:tags]

    return [_present(t, proper, forms) for t in chosen], chosen_tags


def _present(phrase: str, proper: set[str], forms: dict[str, str]) -> str:
    """Display form: the document's own casing for names, Title Case otherwise."""
    words = phrase.split()
    if any(w in proper for w in words):
        return " ".join(forms.get(w, w) for w in words)
    return phrase.title() if phrase.islower() else phrase
