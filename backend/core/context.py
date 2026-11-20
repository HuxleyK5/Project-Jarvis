"""Deterministic conversation signals; summaries remain untrusted session data."""

import re
from backend.memory.privacy import normalize

STOP = set('the and you your what with that this can for how are was were have has had about from into some any our not but does did will would could should please tell more previous conversation conversations chat chats last time remember discuss discussed earlier yesterday again said say we me my to of in on is it a an'.split())


def terms(text: str) -> set[str]:
    words = re.findall(r"[^\W_]{3,}", normalize(text))
    return {word[:-3] + 'y' if len(word) > 5 and word.endswith('ies') else word[:-1]
            if len(word) > 4 and word.endswith('s') and not word.endswith('ss') else word
            for word in words if word not in STOP}


def follow_up(question: str) -> bool:
    return bool(re.search(r"\b(it|its|that|those|them|this|both|former|latter)\b", question, re.I)
                or re.match(r"\s*(and\b|why\b|what about\b|how about\b|tell me more\b|continue\b|yes\b|no\b)", question, re.I))


def recalling_archive(question: str) -> bool:
    return bool(re.search(r"\b(last time|last week|yesterday|previous (?:conversation|chat)|past (?:conversation|chat)|"
                          r"earlier (?:conversation|chat)|do you remember|what did we (?:decide|discuss))\b", question, re.I))


def retrieval_query(messages: list[dict[str, str]]) -> str:
    question = messages[-1]['content']
    if follow_up(question) and len(messages) >= 3:
        return question + ' ' + messages[-3]['content'][:600]
    return question
