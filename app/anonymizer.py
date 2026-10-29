"""
Removes personal data from CV text before it is sent to the LLM.

The model only needs job-relevant content. Names, contact details and
protected attributes (age, gender, nationality, marital status, religion)
are replaced with placeholders so they cannot influence the assessment
(GDPR data minimisation, EU AI Act bias mitigation for hiring systems).
"""
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AnonymizationResult:
    text: str
    redactions: dict[str, int] = field(default_factory=dict)


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|\b(?:linkedin\.com|github\.com|xing\.com|gitlab\.com)/\S*",
    re.IGNORECASE,
)
PHONE = re.compile(
    # Separators exclude newlines so a number never runs into the next line
    r"\(?(?:\+|00)\d{1,3}\)?[ \t\-/.]*\d[\d \t\-/.()]{5,}\d"  # international, e.g. (+49) 911 123456
    r"|\b0\d{2,5}[ \t\-/]*\d{3,}(?:[ \t\-]\d{2,})*\b"         # national, e.g. 0911 / 123456
    r"|\b\d{3}[\-. ]\d{3}[\-. ]\d{4}\b"                       # 555-123-4567
)
DATE_OF_BIRTH = re.compile(
    r"\b(?:date of birth|d\.?o\.?b\.?|born(?: on)?|birthday|geburtsdatum|geboren(?: am)?)"
    r"\s*[:\-]?\s*[^\n|]{0,40}",
    re.IGNORECASE,
)
AGE = re.compile(
    r"\b(?:age|alter)\s*[:\-]\s*\d{2}\b"
    r"|\b\d{2}\s*(?:years old|jahre alt)\b",
    re.IGNORECASE,
)
PERSONAL_ATTRIBUTE = re.compile(
    r"\b(?:gender|sex|geschlecht|marital status|familienstand|nationality|nationalit[äa]t"
    r"|staatsangeh[öo]rigkeit|citizenship|religion|konfession|place of birth|geburtsort"
    r"|children|kinder)\s*[:\-][^\n|]*",
    re.IGNORECASE,
)
TITLE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Herr|Frau)\b\.?\s*")
ADDRESS = re.compile(
    r"\b[A-ZÄÖÜ][a-zäöüß\-]+(?:straße|strasse|str\.|weg|allee|platz|gasse|ring|damm)\s*\d+[a-z]?\b"
    r"|\b\d+\s+[A-Z][a-z]+\s+(?:Street|St\.|Road|Rd\.|Avenue|Ave\.|Lane|Drive)\b"
    r"|\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß]+(?:[\s\-][A-ZÄÖÜ][a-zäöüß]+)?\b"
)

# Words that appear in CV filenames and headings but are not part of a name
NON_NAME_WORDS = {
    "cv", "resume", "résumé", "lebenslauf", "curriculum", "vitae", "final", "updated",
    "new", "english", "german", "deutsch", "en", "de", "v1", "v2", "copy", "draft",
}


def guess_name_parts(text: str, filename: str | None = None) -> set[str]:
    """
    Guesses the candidate's name from a "Name:" label, the first line of the CV
    and the filename. Returns the individual name parts in lowercase.
    """
    candidates: list[str] = []

    label = re.search(r"^\s*(?:full\s+)?name\s*[:\-]\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
    if label:
        candidates.append(label.group(1))

    for line in text.splitlines():
        line = TITLE.sub("", line).strip()
        if not line:
            continue
        words = line.split()
        if (
            2 <= len(words) <= 4
            and len(line) <= 40
            and all(re.fullmatch(r"[A-ZÄÖÜ][\w'\-]+", w) for w in words)
            and not {w.lower() for w in words} & NON_NAME_WORDS
        ):
            candidates.append(line)
        break

    if filename:
        stem = Path(filename).stem
        candidates.append(" ".join(re.split(r"[_\-.\s]+", stem)))

    parts: set[str] = set()
    for candidate in candidates:
        for word in re.split(r"[\s_\-.]+", candidate):
            word = word.strip().lower()
            if len(word) >= 3 and word.isalpha() and word not in NON_NAME_WORDS:
                parts.add(word)
    return parts


def anonymize(text: str, filename: str | None = None) -> AnonymizationResult:
    """
    Replaces personal data in the CV text with placeholders such as [EMAIL].
    Returns the redacted text and how many items of each kind were removed.
    """
    redactions: dict[str, int] = {}

    def apply(pattern: re.Pattern, placeholder: str, category: str, value: str) -> str:
        new_value, count = pattern.subn(placeholder, value)
        if count:
            redactions[category] = redactions.get(category, 0) + count
        return new_value

    # Name parts are guessed before anything is replaced
    name_parts = guess_name_parts(text, filename)

    text = apply(EMAIL, "[EMAIL]", "email", text)
    text = apply(URL, "[URL]", "url", text)
    text = apply(DATE_OF_BIRTH, "[DATE_OF_BIRTH]", "date_of_birth", text)
    text = apply(PERSONAL_ATTRIBUTE, "[PERSONAL_ATTRIBUTE]", "personal_attribute", text)
    text = apply(AGE, "[AGE]", "age", text)
    text = apply(PHONE, "[PHONE]", "phone", text)
    text = apply(ADDRESS, "[ADDRESS]", "address", text)
    text = apply(TITLE, "", "title", text)

    if name_parts:
        name_pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(p) for p in sorted(name_parts, key=len, reverse=True)) + r")\b",
            re.IGNORECASE,
        )
        text = apply(name_pattern, "[CANDIDATE]", "name", text)

    return AnonymizationResult(text=text, redactions=redactions)
