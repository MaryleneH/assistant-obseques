---
name: deroule-obseques
description: Renders a validated funeral ceremony record as an elegant one-page A4 Word document (.docx) — the format the sacristan actually works in. Georgia font, slate palette, liturgical emojis, bold rubric labels, italic song titles, reference on the main line with title/citation on an indented sub-line. Invoked by the orchestrator AFTER human validation. Ported from a battle-tested personal skill.
---

# Runtime skill — Déroulé des obsèques → one-page Word document

This is a **runtime product skill** (rules + script): it packages the
formatting knowledge and a Node.js script (`scripts/build_deroule.js`, using
the `docx` library) that turns a **validated** ceremony record into a polished
**one-page A4** Word document.

**Position in the pipeline:** invoked by the Orchestrator *after*
`security.humanValidated == true` and after the Writer has produced the order
of service. It renders — it never composes or decides content.

## Contract

**Input:** the validated record (see `specs/schema.json`) + the Writer output.
The skill maps them to the script's input JSON (`entree.json`):

```json
{
  "defunt": "Madame Jeanne Martin, 84 ans",
  "eglise": "Église Saint-Martin le Mardi 7 Juillet 2026 / 10h30",
  "celebrant": "Père Bernard",
  "etapes": [
    { "label": "Chant d’entrée", "inline": "N° 8 · Page 5",
      "sub": [ { "t": "Trouver dans ma vie ta présence", "i": true } ] },
    { "label": "1ère Lecture", "sub": "à compléter" }
  ],
  "prochaineMesse": "…"
}
```

Mapping rules from the record:
- `defunt` ← `deceased` (name + `", <age> ans"`).
- `eglise` ← `ceremony.church` + date + time (French long date).
- **`etapes` ← `ceremony.liturgySteps`, 1:1 and in order** (this structure was
  validated against a real, complete one-page déroulé):
  - `label` ← `label` (e.g. "Chant d’entrée", "Rite de la lumière", "Psaume").
  - `inline` ← `reference` (hymn-book ref like "N° 8 · Page 5", or a performer
    like "Célébrant" / "Famille"); if there is no reference but a `title`
    (e.g. the Universal Prayer refrain), the title goes in `inline` as an
    *italic* segment.
  - `sub` ← `title` as an *italic* segment (song title, psalm antiphon),
    followed by `detail` as a roman segment (separator " — "); or `detail`
    alone (citation, reading reference, intention codes like "A1, B2, C1/3").
- `prochaineMesse` ← `ceremony.nextMass`.
- **A `null` liturgical field renders as the placeholder "à compléter"** on its
  sub-line — never invented, never silently dropped.
- Every field comes from the record or the Writer output. **No new content.**
- `deceased.avoidMentioning` topics must not appear anywhere in the document.

**Output:** `deroule.docx` — exactly **one A4 page** (recto).

## Hard rules (inherited from AGENTS.md)

1. **Render only** — no invention, no reformulation of validated content.
2. **One page, verified** — convert to PDF and assert `Pages == 1` (see below).
3. **`avoidMentioning` holds** in the rendered document.
4. Orthography fixes only (accents, typographic apostrophe ’, sentence case for
   handwritten ALL-CAPS); proper nouns keep their capitals. Never add/remove
   words.

## Generate

```bash
NODE_PATH=$(npm root -g) node skills/deroule-obseques/scripts/build_deroule.js entree.json deroule.docx
```

The script auto-picks a font size to target one page (by rubric count).
Override with `--size N` (half-points; `--size 24` = 12 pt).

## Verify "one page" (mandatory loop)

```bash
soffice --headless --convert-to pdf deroule.docx
pdfinfo deroule.pdf | grep Pages
```

- `Pages > 1` → retry with `--size 23`, then `22`.
- Page very empty → retry larger (`26`, `27`). Target ~75–85 % fill.

## Style (what the script produces)

- **Georgia**, sober slate palette; title + deceased's name centered on top.
- **Bold rubric labels**; value to the right; **song titles / psalm antiphons
  in italics**.
- **Reference on the main line, title/citation on the indented sub-line** —
  mirroring how the sacristan's handwritten sheets are organized.
- Thin rules under the header and before the footer; "Prochaine Messe" centered
  in italics at the bottom; ~2 cm margins.
- Liturgical emojis assigned automatically by label (🕊️ header, 🎵 chants,
  📖 readings, 📜 psaume, 🙏 prières, ⚜️ Marie, ✝️ bénédiction, ⛪ église…);
  unknown labels get a neutral "•".
- Typographic conventions: `·` between reference and page/citation, `—`
  between a title and a note, apostrophe ’, ellipsis ….

## Delivery to the sacristan

The `.docx` is produced as a downloadable artifact. If the Gmail MCP server
supports draft attachments, attach it; otherwise the sacristan attaches it
herself when she reviews and sends the draft — one more human touchpoint,
consistent with the human-in-the-loop design.

## Files

- `scripts/build_deroule.js` — the renderer (Node.js + `docx`), ported as-is
  from the author's proven personal skill.
- `references/exemple_deroule.json` — a complete input example.

## Dependencies

Node.js + the `docx` npm package (the runtime image must provide them);
LibreOffice (`soffice`) + poppler (`pdfinfo`) for the one-page verification.
