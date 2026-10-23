"""Marathi (Devanagari) -> English spelling of personal and place names.

Used to show names in English when the app language is English. It follows common Maharashtrian
spellings (Dnyaneshwari, Shinde, Kamble, Saraswati) and deletes the inherent "a" the way names are
pronounced (Angad, not Angada; Navnath, not Navanath). Latin text is left as it is, apart from
capitalisation. The result is a readable spelling, not an official one.
"""

import re
import unicodedata

CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l",
    "क़": "k", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "dh", "फ़": "f", "य़": "y",
}
VOWELS = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ru", "ए": "e", "ऐ": "ai",
          "ओ": "o", "औ": "au", "ॲ": "a", "ऑ": "o", "ऍ": "e"}
MATRAS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ru", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
          "ॅ": "a", "ॉ": "o"}
VIRAMA, ANUSVARA, CANDRABINDU, VISARGA, NUKTA = "्", "ं", "ँ", "ः", "़"
LABIALS = {"p", "ph", "b", "bh", "m"}
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
# Established spellings the rules cannot derive.
WORDS = {"गायकवाड": "gaikwad", "गायकवाडे": "gaikwade", "कांबळे": "kamble", "कांबले": "kamble"}
# Doubled aspirates are written with one "h": Vitthal, Siddharth.
DOUBLED = {"thth": "tth", "dhdh": "ddh", "khkh": "kkh", "ghgh": "ggh", "chch": "cch", "phph": "pph", "bhbh": "bbh"}


def _syllables(word: str) -> list[dict]:
    """Split a word into aksharas: {"cons": [...], "vowel": str | None, "nasal": bool, "inherent": bool}."""
    out: list[dict] = []
    i = 0
    while i < len(word):
        ch = word[i]
        if ch in VOWELS:
            out.append({"cons": [], "vowel": VOWELS[ch], "nasal": False, "inherent": False})
            i += 1
        elif ch in CONSONANTS:
            cons = [CONSONANTS[ch]]
            i += 1
            if i < len(word) and word[i] == NUKTA:
                i += 1
            # Conjuncts: consonant + virama + consonant ...
            while i + 1 < len(word) and word[i] == VIRAMA and word[i + 1] in CONSONANTS:
                cons.append(CONSONANTS[word[i + 1]])
                i += 2
                if i < len(word) and word[i] == NUKTA:
                    i += 1
            if i < len(word) and word[i] == VIRAMA:  # dead final consonant
                out.append({"cons": cons, "vowel": "", "nasal": False, "inherent": False})
                i += 1
            elif i < len(word) and word[i] in MATRAS:
                out.append({"cons": cons, "vowel": MATRAS[word[i]], "nasal": False, "inherent": False})
                i += 1
            else:
                out.append({"cons": cons, "vowel": "a", "nasal": False, "inherent": True})
        elif ch in (ANUSVARA, CANDRABINDU):
            if out:
                out[-1]["nasal"] = True
            i += 1
        elif ch == VISARGA:
            if out:
                out[-1]["vowel"] = (out[-1]["vowel"] or "") + "h"
                out[-1]["inherent"] = False
            i += 1
        else:  # unknown sign: keep going
            i += 1
    return out


def _cluster(cons: list[str]) -> str:
    """Consonant cluster spelling: क्ष = ksh, ज्ञ = dny, व/य after a consonant = w/y."""
    text = ""
    for k, c in enumerate(cons):
        if k and c == "v":
            c = "w"
        text += c
    return text.replace("jn", "dny")


def _word(word: str) -> str:
    syl = _syllables(word)
    if not syl:
        return word
    # Final inherent "a" is not pronounced (Angad), except after a conjunct (Chaitanya) or in one-letter words.
    last = syl[-1]
    if len(syl) > 1 and last["inherent"] and len(last["cons"]) == 1:
        last["vowel"] = ""
    # Medial inherent "a" is dropped between a vowel and a following consonant+vowel (Navnath, Ganpat),
    # but not next to conjuncts (Dattarav, Saraswati).
    for k in range(1, len(syl) - 1):
        cur, prev, nxt = syl[k], syl[k - 1], syl[k + 1]
        # After a nasal the vowel stays (Anjali, Gitanjali).
        if (cur["inherent"] and len(cur["cons"]) == 1 and prev["vowel"] and not prev["nasal"]
                and len(prev["cons"]) <= 1 and nxt["cons"] and len(nxt["cons"]) == 1 and nxt["vowel"]):
            cur["vowel"] = ""
            cur["inherent"] = False
    text = ""
    for k, s in enumerate(syl):
        text += _cluster(s["cons"]) + s["vowel"]
        if s["nasal"]:
            nxt = syl[k + 1]["cons"][0] if k + 1 < len(syl) and syl[k + 1]["cons"] else ""
            text += "m" if nxt in LABIALS else "n"
    for a, b in DOUBLED.items():
        text = text.replace(a, b)
    # "-राव" is written "-rao": Dattarao, Bapurao, Bhalerao.
    if text.endswith("rav") and len(text) > 3:
        text = text[:-1] + "o"
    return text


def to_latin(text: str | None) -> str | None:
    """English spelling of a (possibly mixed Marathi/English) name, each word capitalised."""
    if not text:
        return text
    text = unicodedata.normalize("NFC", text.replace("‍", "").replace("‌", ""))
    words = []
    for w in text.split():
        w = WORDS.get(w) or _word(w) if DEVANAGARI.search(w) else w
        words.append(w[:1].upper() + w[1:].lower() if w else w)
    return " ".join(words)
