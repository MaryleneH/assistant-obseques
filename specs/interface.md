# Interface — Assistant Obsèques (the sacristan's operational app)

> This interface is the product's reason to exist: the screen the sacristan
> actually opens and uses. Beyond the competition, it is *the* deliverable that
> gives real value. The demo shown to judges **is** version 1 of this app — not
> a throwaway. We build one interface, not two.

## 1. The core flow (MVP)

1. **Sign in** — private access, only the sacristan (see Security below).
2. **Input** — she pastes free-form interview notes, **or** uploads photo(s) /
   PDF pages of her annotated preparation sheets (multi-page supported).
3. **Extraction → validation screen** — the record appears as an **editable
   form** with: missing fields flagged, cross-page contradictions alerted,
   per-field confidence / `needsHumanReview` indicators, and the
   `avoidMentioning` list highlighted.
4. **Correct + Validate** — the human gate. Nothing downstream runs until she
   validates (`security.humanValidated == true`); a `BLOCKING` status disables
   the Validate button until resolved.
5. **Generate** — she gets the concrete deliverables: the **one-page Word
   déroulé** (download — her tool of choice), a **Google Doc**, and a **Gmail
   draft** to the priest and team (**never sent**).
6. **History** — a list of past ceremonies read from her own Google Sheet, so
   she can reopen, duplicate, or review a previous dossier.

## 2. Technology

- **Frontend:** a lightweight web app in `ui/`. The **validation screen** (step
  3–4) uses **A2UI** — it is both the human-in-the-loop heart of the product
  and the course concept we showcase. *Fallback:* a plain web UI if A2UI proves
  limiting for daily, non-technical use — the human-in-the-loop behaviour
  matters more than the specific tech.
- **Backend:** the ADK agents (orchestrator + sub-agents) behind the screen.
- Packaged together for a single deployable unit (see Deployment).

## 3. Deployment — Cloud Run (not Agent Engine)

We deploy to **Cloud Run**, the individual-friendly serverless platform:

- `adk deploy cloud_run` — optionally `--with_ui` for a working web interface
  out of the box; a tailored frontend replaces it for the real product.
- **Private / auth-gated** — access restricted to the sacristan (drop
  `--allow-unauthenticated`, or front with Identity-Aware Proxy). **No public
  access.** This reinforces the Concierge-track privacy narrative.
- **Scales to zero** → near-free for a single user. **EU region**
  (`europe-west9`, Paris) for GDPR alignment.
- Ticks the competition's **Deployability** concept — Cloud Run is a
  first-class ADK deployment target recognized by Google judges.

**Why Cloud Run over Agent Engine (rationale, superseding earlier notes):**
Agent Engine is an API-only managed runtime — it exposes the agent's *logic*
but **not a user interface**, and needs an extra proxy service to be reachable
from a web app. Cloud Run hosts the agent **and** the interface as one
operational unit the sacristan can open in her browser. Simpler, cheaper, and
it actually solves the "she needs a screen" requirement.

## 4. Scope split (honest, timeline-aware)

- **Competition (this weekend):** the interface runs **locally** for the demo
  and the video — that is sufficient for judging (a live hosted endpoint is not
  required). One `adk deploy cloud_run` run demonstrates Deployability and
  yields a real URL.
- **Real operational product (post-competition polish):** hardened
  authentication, a daily-use UX tuned for a non-technical user, ceremony
  history, and photo-upload robustness. **Same interface, iterated** — the demo
  is v1, the foundation to build on, not something we throw away.

## 5. Security & privacy

- **Auth-gated:** only the sacristan can open the app; the Cloud Run service is
  private. No public access, no family access in v1.
- **Data stays with her:** ceremony records live in her own Google Sheet /
  Drive; raw photos are not persisted server-side beyond processing.
- **EU-region** processing target.
- The interface never sends anything on its own — every send is a human action.

## 6. Acceptance scenarios (BDD)

```gherkin
Scenario: Nothing is generated before the human validates in the UI
  Given a freshly extracted record shown in the validation screen
  When the sacristan has not clicked Validate
  Then the Generate action is unavailable
  And no Word document, Google Doc, or Gmail draft exists yet

Scenario: Paste notes and see an editable record with flags
  Given the sacristan pastes free-form interview notes
  When extraction completes
  Then the record appears as an editable form
  And missing fields, contradictions, and avoidMentioning are visibly flagged

Scenario: Upload multi-page photos and get one consolidated record
  Given the sacristan uploads several photos of annotated sheets
  When extraction completes
  Then a single consolidated record is shown
  And any cross-page contradiction is surfaced for her to resolve

Scenario: Generate produces the three deliverables, sends nothing
  Given a validated record
  When the sacristan clicks Generate
  Then a one-page Word déroulé is available to download
  And a Google Doc is created
  And a Gmail draft is prepared but NOT sent

Scenario: Only the authenticated sacristan can access the app
  Given a user who is not the authorized sacristan
  When they open the app URL
  Then access is denied
```

## 7. Reference mockup — the validated AI Studio prototype

Ten days before the competition, a UI prototype was built with Google AI
Studio and **validated with the sacristan** (deployed on Cloud Run,
`europe-west2`). It is the **visual and UX reference** for Phase 5: match this
envelope, do not invent a new one. Key facts: **mobile-first** (the sacristan
photographs her preparation sheet with her phone), French labels, a sober
cream / sage / slate palette with a serif brand title — consistent with the
Word déroulé's Georgia/ardoise identity.

### Screen A — « Source du document » (input)
- **Camera-first**: a large dashed drop zone "Prendre une photo / Importer"
  (JPG/PNG drag-and-drop), with an `IMAGE / PDF` toggle.
- **Built-in annotated examples** ("Ou essayez un exemple annoté") — one-tap
  demo cases; keep them (great for demos, judges, and onboarding).
- One primary CTA — "✨ Extraire les informations" — disabled until a source
  is present.
- A **trust box** "Aide & consignes" stating the product rules in the user's
  language: the AI extracts *only* what it can read with certainty; anything
  crossed-out, vague or doubtful is reported under *Incertitudes / Points à
  vérifier*; the assistant synthesizes, it does not rewrite the document.

### Screen B — Extraction results (sectioned cards)
Ordered sections, uppercase micro-labels, one rounded card per topic:
1. **Informations générales** — défunt(e); célébration (date/heure, lieu);
   prêtre/célébrant.
2. **Famille & contacts** — main contact; "membres à mentionner" as chips.
3. **Profil & vie du défunt.**
4. **Déroulé de la célébration** — Textes de l'Écriture, chants…
5. **Musique enregistrée / CD / instruments.**
6. **Prière universelle (intentions).**
7. **Gestes & rites particuliers** — e.g. rite de la lumière with its
   reference and assignment note.
8. **Logistique église** — practical to-dos *derived* from the content
   ("Prévoir lecteur CD pour la musique d'entrée", "Prévoir 2 lumignons")
   → maps to `ceremony.practicalNotes`.
9. **⚠️ Points à vérifier & incertitudes** — amber section with *specific*
   doubts (e.g. « L'année : '2020' ou '2026' ? » ; « à quel recueil les
   références N°/Page se réfèrent-elles ? ») → maps to
   `extraction.needsHumanReview` / `contradictions` / `missingFields`.
10. **Questions suggérées à la famille** — concrete follow-up questions the
    sacristan can ask at the next meeting → maps to
    `qualityCheck.suggestedQuestions`.

**Explicit empty states everywhere** ("Aucune note repérée.", "Aucune
coordonnée visible") — the UI never fills a gap silently.

### What v1 adds on top of the prototype (build deltas)
The prototype's results are **read-only**; v1 turns Screen B into the
**editable validation gate** (Correct / Validate; a `BLOCKING` status disables
Validate), then adds: the **Generate** step (one-page Word déroulé download,
Google Doc, Gmail draft — never sent), **multi-page consolidation** with
cross-page contradiction alerts, **history** read from the Sheet, and hardened
authentication.

> ⚠️ The prototype screenshots contain **real ceremony data**. They must never
> be committed to this repo nor shown in the video; re-shoot any needed visual
> using the built-in annotated examples or the Jeanne Martin case.
