# Behaviour — Assistant Obsèques (BDD acceptance scenarios)

These Gherkin scenarios are the **acceptance contract**. The coding agent must
make them pass; `eval/` should exercise them against `examples/jeanne_martin/`.
"Record" = the structure in `schema.json`.

---

## Feature: Multi-page note extraction (Extractor)

```gherkin
Scenario: Consolidate several pages into one record
  Given the sacristan provides 2 or more photos/PDF pages of notes
  When the Extractor runs
  Then it returns exactly ONE record following schema.json
  And information from every page is merged into that single record

Scenario: Flag missing information instead of inventing it
  Given the notes do not mention the Gospel reading
  When the Extractor runs
  Then ceremony.gospel is null
  And "gospel" is listed in extraction.missingFields
  And no value is fabricated for it

Scenario: Alert on a cross-page contradiction
  Given page 1 states the time is "10:30"
  And page 3 states the time is "11:00"
  When the Extractor runs
  Then an entry is added to extraction.contradictions
  And that entry records the field, both values, and the page numbers
  And the field is not silently overwritten

Scenario: Mark handwriting-derived fields for human review
  Given a field is read from handwriting with low confidence
  When the Extractor runs
  Then that field's key appears in extraction.fieldConfidences with a score
  And that field is listed in extraction.needsHumanReview

Scenario: Capture ordered liturgical steps with hymn-book references
  Given the notes or annotated sheet mention liturgical steps
  And some steps carry a hymn-book reference such as "N° 8 · Page 5"
  When the Extractor runs
  Then ceremony.liturgySteps lists those steps in liturgical order
  And each step keeps its reference, title, and assignment note verbatim
  And steps not mentioned in the input are NOT fabricated

Scenario: Carry avoidMentioning forward
  Given the notes say "do not dwell on her illness"
  When the Extractor runs
  Then "ne pas insister sur la maladie" is in deceased.avoidMentioning
```

---

## Feature: Quality & safety check (Checker / Safety)

```gherkin
Scenario: Required field missing raises a warning
  Given the record has no ceremony.date
  When the Checker runs
  Then qualityCheck.status is "WARNING" or "BLOCKING"
  And an alert names the missing required field

Scenario: Missing recipient blocks the flow
  Given communication.priestEmail is null
  When the Checker runs
  Then qualityCheck.status is "BLOCKING"
  And a recommended action asks for the recipient before any draft is created

Scenario: Unresolved contradiction surfaces as a warning
  Given extraction.contradictions is not empty
  When the Checker runs
  Then qualityCheck.status is at least "WARNING"
  And the contradiction is included in the alerts

Scenario: Suggest follow-up questions for the family
  Given the record has gaps that a family conversation could fill
  When the Checker runs
  Then qualityCheck.suggestedQuestions lists concrete questions
  And each question targets a specific missing or uncertain field

Scenario: Clean record passes
  Given all required fields are present and there are no contradictions
  When the Checker runs
  Then qualityCheck.status is "OK"
```

---

## Feature: Human validation gate (A2UI)

```gherkin
Scenario: Generation is blocked until the human validates
  Given security.humanValidated is false
  When any downstream step (Writer, Doc, Gmail draft, Sheet write) is attempted
  Then it is refused
  And the user is directed to the validation screen

Scenario: A BLOCKING status cannot be validated
  Given qualityCheck.status is "BLOCKING"
  When the sacristan opens the validation screen
  Then the Validate action is disabled until the blocking issue is resolved

Scenario: Editing and validating unlocks the pipeline
  Given the sacristan corrects the flagged fields
  And qualityCheck.status is not "BLOCKING"
  When she clicks Validate
  Then security.humanValidated becomes true
  And status advances to ready_for_generation
```

---

## Feature: Order of service & universal prayer (Writer)

```gherkin
Scenario: Generate from a validated record only
  Given security.humanValidated is true
  When the Writer runs
  Then it produces an order of service and a universal prayer
  And the tone is sober and respectful

Scenario: Respect avoidMentioning
  Given deceased.avoidMentioning contains "ne pas insister sur la maladie"
  When the Writer runs
  Then no generated text refers to the illness

Scenario: Do not invent biographical details
  Given the record contains only the provided facts
  When the Writer runs
  Then the text introduces no biographical claim absent from the record

Scenario: Flag missing liturgical elements
  Given ceremony.firstReading is null
  When the Writer runs
  Then the output marks the first reading as "to be completed"
  And does not invent a reading
```

---

## Feature: Outputs via MCP (never auto-send)

```gherkin
Scenario: Create the Google Doc
  Given a validated order of service
  When the orchestrator calls the Docs MCP server
  Then a Google Doc is created
  And its link is stored in communication.documentLink

Scenario: Create a Gmail draft, never send
  Given recipients are present and the record is validated
  When the orchestrator calls the Gmail MCP server
  Then a draft is created
  And no email is sent
  And communication.emailDraftCreated becomes true

Scenario: Append one row per ceremony to the Sheet
  Given a validated ceremony
  When the orchestrator calls the Sheets MCP server
  Then exactly one row is appended to the sacristan's Google Sheet
  And list fields are written to readers_json and intentions_json
  And no raw photo is written to the Sheet
```

---

## Feature: One-page Word order of service (runtime skill)

```gherkin
Scenario: Produce a one-page Word document from the validated record
  Given security.humanValidated is true
  And the Writer has produced the order of service
  When the deroule-obseques skill runs
  Then a .docx file is produced
  And its PDF conversion has exactly ONE page

Scenario: Missing elements appear as placeholders, never invented
  Given ceremony.firstReading is null
  When the skill runs
  Then the document shows the first reading as "à compléter"
  And no reading is fabricated

Scenario: Formatting conventions are applied
  Given the record contains songs and readings
  When the skill runs
  Then song titles are rendered in italics
  And rubric labels are bold
  And references sit on the main line with titles/citations on the sub-line

Scenario: avoidMentioning holds in the rendered document
  Given deceased.avoidMentioning contains a topic
  When the skill runs
  Then the topic does not appear anywhere in the document
```

---

## Feature: Security & privacy

```gherkin
Scenario: Only allowlisted users get access
  Given an email that is not in ALLOWED_EMAILS
  When access is attempted
  Then it is denied

Scenario: No secrets in the codebase
  Given the repository
  When it is scanned
  Then no API key, password, or service-account JSON is present
  And credentials are read from environment variables only
```
