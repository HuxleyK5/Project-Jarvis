"""Conservative local storage guard. Rejected text is never written or logged."""

import re
import unicodedata

AUTH = re.compile(
    r"\b(password|passwd|passphrase|api[ _-]?key|access[ _-]?token|refresh[ _-]?token|"
    r"auth(?:entication|orization)?[ _-]?(?:token|secret)|bearer|private[ _-]?key|"
    r"recovery[ _-]?codes?|seed[ _-]?phrase|mnemonic|session[ _-]?(?:cookie|token|key)|"
    r"client[ _-]?secret|one[ _-]?time[ _-]?(?:code|password)|otp|pin[ _-]?code)\b|"
    r"-----BEGIN .*PRIVATE KEY-----|\b(?:sk-|ghp_|github_pat_|xox[baprs]-|AKIA)[A-Za-z0-9_-]{8,}|"
    r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|"
    r"\b(?:secret|token|credential|cookie|pin)\s*[:=]|://[^\s/:]+:[^\s/@]+@",
    re.IGNORECASE,
)
PERSONAL = re.compile(r"\b(?:ssn|social security|credit card|bank account|medical record|diagnosis|diagnosed|"
                      r"passport number|date of birth|home address)\b|\b\d{3}-\d{2}-\d{4}\b|"
                      r"\b(?:\d[ -]?){13,19}\b", re.IGNORECASE)


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip(".!?")


def sensitive(text: str) -> bool:
    text = unicodedata.normalize("NFKC", text)
    if AUTH.search(text) or PERSONAL.search(text):
        return True
    # Unknown credential-shaped values are rejected too, at the cost of false positives.
    return any(len(token) >= 32 and re.search(r"[A-Za-z]", token) and re.search(r"\d", token)
               for token in re.findall(r"[A-Za-z0-9_+/=-]+", text))
