"""
Liturgy ontology — single source of truth for canonical rubric labels.

Derived from skills/deroule-obseques/references/exemple_deroule.json (the
reference one-page déroulé), plus "2ème Lecture" inserted after "1ère Lecture"
for ceremonies that include it.

Every consumer (extractor prompt, UI scaffold, déroulé mapper) imports from
here so the ontology cannot drift.
"""
import re

# ---------------------------------------------------------------------------
# The 18 canonical rubric labels in liturgical order.
# The first 17 match exemple_deroule.json; "2ème Lecture" is inserted after
# "1ère Lecture" because some ceremonies include a second reading.
# ---------------------------------------------------------------------------
CANONICAL_LABELS: list[str] = [
    "Entrée",
    "Accueil",
    "Présentation du défunt",
    "Chant d'entrée",
    "Rite de la lumière",
    "1ère Lecture",
    "2ème Lecture",           # not in the 17-step reference, but valid
    "Psaume",
    "Alléluia",
    "Évangile",
    "Homélie",
    "Prière Universelle",
    "Notre Père",
    "Chant d'Adieu",
    "Encensement / Bénédiction",
    "Prière à Marie",
    "Bénédiction",
    "Sortie",
]

# ---------------------------------------------------------------------------
# Content rubrics: these carry ceremony-specific text (song title, reading
# reference, prayer intentions).  When a content rubric is present but empty,
# the déroulé mapper stamps "à compléter" and the checker flags it in
# missingFields.
# ---------------------------------------------------------------------------
CONTENT_RUBRICS: frozenset[str] = frozenset({
    "Chant d'entrée",
    "1ère Lecture",
    "2ème Lecture",
    "Psaume",
    "Évangile",
    "Prière Universelle",
    "Chant d'Adieu",
})

# ---------------------------------------------------------------------------
# Scaffold rubrics: the subset of content rubrics that the UI pre-fills as
# empty rows when the extractor did not return them.  "2ème Lecture" is
# deliberately excluded — most ceremonies have no second reading; scaffolding
# it would add noise.
# ---------------------------------------------------------------------------
SCAFFOLD_RUBRICS: frozenset[str] = frozenset({
    "Chant d'entrée",
    "1ère Lecture",
    "Psaume",
    "Évangile",
    "Prière Universelle",
    "Chant d'Adieu",
})


def norm_label(s: str) -> str:
    """Normalize a rubric label for dedup / comparison.

    Rules: lowercase, typographic ' (U+2019) → ASCII ', strip leading/trailing
    whitespace, collapse internal whitespace to a single space.  Mirrors the
    normLabel helper in the Node.js skill.
    """
    return re.sub(r"\s+", " ", s.replace("\u2019", "'").strip().lower())


def canonical_position(label: str) -> int:
    """Return the liturgical-order index for *label* (normalized comparison).

    Unknown labels sort after Sortie (index = len(CANONICAL_LABELS)).
    """
    n = norm_label(label)
    for i, c in enumerate(CANONICAL_LABELS):
        if norm_label(c) == n:
            return i
    return len(CANONICAL_LABELS)
