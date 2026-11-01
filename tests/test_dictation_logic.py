import re
import pytest

def normalize_dictation_text(t: str) -> str:
    cleaned = re.sub(r"[.,/#!$%^&*;:{}=\-_`~()?\"'’]", "", t or "").lower()
    return re.sub(r"\s+", " ", cleaned).strip()

CONTRACTION_MAP = {
    "dont": "do not",
    "cant": "cannot",
    "wont": "will not",
    "im": "i am",
    "youre": "you are",
    "theyre": "they are",
    "were": "we are",
    "isnt": "is not",
    "arent": "are not",
    "didnt": "did not",
    "doesnt": "does not",
    "couldnt": "could not",
    "wouldnt": "would not",
    "shouldnt": "should not",
    "ive": "i have",
    "youve": "you have",
    "theyve": "they have",
    "weve": "we have",
    "hes": "he is",
    "shes": "she is",
    "its": "it is",
    "theres": "there is",
    "thats": "that is",
    "gonna": "going to",
    "wanna": "want to",
    "gotta": "got to",
}

def expand_contractions(text: str) -> str:
    words = text.split(" ")
    return " ".join([CONTRACTION_MAP.get(w, w) for w in words])

def calc_levenshtein(a: str, b: str) -> int:
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        dp[i][0] = i
    for j in range(len(b) + 1):
        dp[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[len(a)][len(b)]

def parse_time_str(t: str) -> float:
    t = (t or "").strip().replace(",", ".")
    parts = t.split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(t) if t else 0.0

def parse_srt_or_vtt(text: str):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments = []
    cur = None
    time_regex = re.compile(r"((?:\d{2}:)?\d{2}:\d{2}[,.]\d{3})\s*-->\s*((?:\d{2}:)?\d{2}:\d{2}[,.]\d{3})")

    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            if cur and cur.get("en"):
                segments.append(cur)
                cur = None
            continue
        match = time_regex.search(trimmed)
        if match:
            if cur and cur.get("en"):
                segments.append(cur)
            cur = {
                "start": parse_time_str(match.group(1)),
                "end": parse_time_str(match.group(2)),
                "en": "",
                "pt": "",
            }
        elif cur:
            clean_line = re.sub(r"<[^>]+>", "", trimmed)
            if clean_line and not re.match(r"^\d+$", clean_line):
                cur["en"] = (cur["en"] + " " + clean_line).strip()

    if cur and cur.get("en"):
        segments.append(cur)
    return segments


def test_contraction_expansion():
    raw_1 = "I don't know what you're talking about"
    norm_1 = expand_contractions(normalize_dictation_text(raw_1))
    
    raw_2 = "I do not know what you are talking about"
    norm_2 = expand_contractions(normalize_dictation_text(raw_2))
    
    assert norm_1 == norm_2 == "i do not know what you are talking about"


def test_casual_speech_contractions():
    raw = "I gotta go because I wanna see it"
    norm = expand_contractions(normalize_dictation_text(raw))
    assert norm == "i got to go because i want to see it"


def test_levenshtein_distance_spelling_hints():
    # Minor typos that should trigger smart spelling hints
    assert calc_levenshtein("colegue", "colleague") == 2
    assert calc_levenshtein("honord", "honored") == 1
    assert calc_levenshtein("definately", "definitely") == 1
    assert calc_levenshtein("seperate", "separate") == 1
    assert calc_levenshtein("recieve", "receive") == 2


def test_srt_parsing():
    sample_srt = """1
00:00:23,500 --> 00:00:28,200
I am honored to be with you today.

2
00:00:28,400 --> 00:00:34,000
from one of the finest universities in the world.
"""
    segs = parse_srt_or_vtt(sample_srt)
    assert len(segs) == 2
    assert segs[0]["start"] == 23.5
    assert segs[0]["end"] == 28.2
    assert segs[0]["en"] == "I am honored to be with you today."
    assert segs[1]["start"] == 28.4
    assert segs[1]["end"] == 34.0
