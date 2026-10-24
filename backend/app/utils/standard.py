"""Normalise a girl's class ("6 वी", "6वा", "९वी", "आठवी", "9.0") to just the number."""
import re

WORDS = {"पहिली": 1, "दुसरी": 2, "तिसरी": 3, "चौथी": 4, "पाचवी": 5, "सहावी": 6, "सातवी": 7, "सातवा": 7, "आठवी": 8,
         "नववी": 9, "दहावी": 10, "दहा वी": 10, "अकरावी": 11, "बारावी": 12}
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def normalise_standard(value):
    if value in (None, ""):
        return None
    text = str(value).strip().translate(DEVANAGARI_DIGITS)
    for word, n in WORDS.items():
        if text.startswith(word):
            return str(n)
    m = re.search(r"\d+", text)
    if m:
        return str(int(m.group()))
    return text  # e.g. "B.Sc" is kept as entered
