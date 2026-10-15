"""Statistical keyphrase extraction.

Scores candidate phrases by how often they occur and how specific they are,
then returns the strongest. Every phrase returned is a sequence of words that
literally appears in the document — the method cannot produce a topic the
text does not contain, which is exactly the property wanted here.

It is frequency statistics, not understanding. A document can be about
something it never names, and this will miss it.
"""
from __future__ import annotations

import re
from collections import Counter

_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]+|\d{4}")

# Function words carry no topical signal. Kept deliberately short: an
# aggressive list starts removing real subject terms.
_STOPWORDS = frozenset("""
a about above after again against all also am an and any are aren as at be
because been before being below between both but by can cannot could did do
does doing don down during each few for from further had has have having he
her here hers herself him himself his how i if in into is it its itself just
me more most my myself no nor not of off on once only or other ought our ours
ourselves out over own same she should so some such than that the their theirs
them themselves then there these they this those through to too under until up
very was we were what when where which while who whom why will with would you
your yours yourself yourselves been upon shall may might must whose via etc
use used using one two three new within whether however therefore thus
""".split())

_MAX_PHRASE_WORDS = 3
_MIN_WORD_LENGTH = 3


def _tokens(text: str) -> list[str | None]:
    """Words in order, with None marking a break a phrase may not cross."""
    out: list[str | None] = []
    for segment in re.split(r"[.!?;:\n\r\t()\[\]{}\"“”|]+", text):
        words = [w.lower() for w in _WORD.findall(segment)]
        out.extend(words)
        out.append(None)
    return out


def _candidates(tokens: list[str | None]) -> Counter:
    """Phrases of 1..3 content words, not crossing a break or a stopword."""
    counts: Counter = Counter()
    run: list[str] = []

    def flush(run: list[str]) -> None:
        for size in range(1, _MAX_PHRASE_WORDS + 1):
            for start in range(len(run) - size + 1):
                phrase = run[start : start + size]
                if any(len(w) < _MIN_WORD_LENGTH for w in phrase):
                    continue
                counts[" ".join(phrase)] += 1

    for token in tokens:
        if token is None or token in _STOPWORDS:
            flush(run)
            run = []
            continue
        run.append(token)
    flush(run)
    return counts


def _score(phrase: str, count: int) -> float:
    """Repetition first, specificity second.

    An earlier version weighted specificity heavily enough that
    single-occurrence trigrams outranked terms the document used repeatedly,
    which filled the topics with overlapping noise. Frequency now leads and
    length only breaks ties among phrases of similar frequency.
    """
    specificity = 1.0 + 0.6 * (len(phrase.split()) - 1)
    return count * specificity


def extract(text: str, *, topics: int = 6, tags: int = 8) -> tuple[list[str], list[str]]:
    """Topics (phrases) and tags (single words), both drawn from the text.

    Returns two disjoint lists. Topics prefer multi-word phrases because they
    name a subject more precisely; tags are single salient words, which is
    what a tag is useful as.
    """
    tokens = _tokens(text)
    total = sum(1 for t in tokens if t is not None)
    if total < 5:
        # Too little text for frequency to mean anything. Say nothing.
        return [], []

    counts = _candidates(tokens)
    if not counts:
        return [], []

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

    # Recurrence is the evidence that something is a subject of the document.
    # A phrase occurring once is a phrase the document happened to contain,
    # which is why "churn fell across" outranked "revenue" before this split:
    # once-only candidates are considered only when nothing recurs at all.
    recurring = sorted(
        ((p, _score(p, c)) for p, c in counts.items() if c > 1 and p not in redundant),
        key=lambda pair: (-pair[1], pair[0]),
    )
    once = sorted(
        ((p, _score(p, c)) for p, c in counts.items() if c == 1 and p not in redundant),
        key=lambda pair: (-pair[1], pair[0]),
    )
    # Short documents where nothing repeats still deserve something, but
    # little of it: three guesses, not a padded list of six.
    scored = recurring if recurring else once[:3]

    chosen_topics: list[str] = []
    for phrase, _ in scored:
        words = set(phrase.split())
        # Never two topics naming the same thing. Scored order is followed
        # exactly: an earlier version walked every multi-word phrase before
        # any single word, so incidental trigrams outranked the terms the
        # document actually repeats.
        if any(words & set(other.lower().split()) for other in chosen_topics):
            continue
        chosen_topics.append(phrase)
        if len(chosen_topics) == topics:
            break

    # Tags exclude a word that is already a topic in its own right, but not a
    # word that merely appears inside a longer topic — otherwise a document
    # whose topics are all single words would have no tags left.
    taken = {t.lower() for t in chosen_topics}
    # A tag is a weaker claim than a topic, so a word the document uses once
    # can still be a reasonable tag. Recurring words come first, and
    # once-only words top the list up only when the recurring ones run out.
    def singles(pool):
        return [w for w, _ in pool if " " not in w and w not in taken]

    chosen_tags = singles(recurring)
    if len(chosen_tags) < 3:
        for word in singles(once):
            if word in chosen_tags:
                continue
            chosen_tags.append(word)
            if len(chosen_tags) >= 5:
                break
    chosen_tags = chosen_tags[:tags]

    return [_present(t) for t in chosen_topics], chosen_tags


def _present(phrase: str) -> str:
    """Title Case for display, leaving anything already cased alone."""
    return phrase.title() if phrase.islower() else phrase
