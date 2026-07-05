🌍 **Français** · [English](README.md)

# Assistant Obsèques
### Un copilote IA, sous contrôle humain, pour préparer les cérémonies d'obsèques

> **L'IA propose ; c'est toujours vous qui décidez.** Rien n'est jamais envoyé
> automatiquement.

## À quoi ça sert

Préparer une célébration d'obsèques, c'est des heures de travail minutieux :
écouter la famille, déchiffrer des notes manuscrites sur plusieurs pages,
retaper le déroulé, écrire au prêtre et à l'équipe, tenir le registre — sous
pression émotionnelle, sans droit à l'erreur. L'assistant prend en charge la
partie répétitive de ce travail, **pour vous rendre du temps auprès des
familles**.

## Ce que l'assistant fait — et ne fait pas

**Il fait :**
- lire vos notes tapées **ou les photos de vos feuilles de préparation**
  (plusieurs pages), et en tirer une fiche structurée ;
- signaler ce qui manque, ce qui se contredit d'une page à l'autre, et ce qui
  mérite vérification ;
- vous **suggérer les questions à poser à la famille** au prochain rendez-vous ;
- après **votre** validation : générer le **déroulé Word élégant, une page**
  (votre outil de tous les jours), un Google Doc partageable (API Google Docs),
  un **brouillon** d'email au prêtre et à l'équipe (API Gmail — brouillon
  uniquement), et une ligne dans **votre** registre Google Sheet (serveur MCP
  — repli automatique sur l'API directe).

**Il ne fait jamais :**
- envoyer un email tout seul — c'est toujours vous qui appuyez sur « Envoyer » ;
- inventer un contenu manquant — un champ vide devient « à compléter » ;
- mentionner un sujet que la famille a demandé d'éviter.

## Comment ça marche pour vous

1. **Vous vous connectez** — l'application est privée, vous seule y accédez.
2. **Vous photographiez** votre feuille avec votre téléphone (ou collez vos
   notes, ou déposez un PDF).
3. **Vous relisez la fiche extraite** sur l'écran de validation : les champs
   manquants sont signalés, les doutes aussi (« l'année : 2020 ou 2026 ? »).
4. **Vous corrigez et validez.** Tant que vous n'avez pas validé, rien n'est
   généré.
5. **Vous générez** : le déroulé Word à télécharger, le Google Doc, le
   brouillon d'email — que vous relisez et envoyez vous-même.
6. **Votre registre** se met à jour d'une ligne dans votre Google Sheet, et
   vous retrouvez vos cérémonies passées.

L'interface a été **maquettée et validée avec vous** avant toute construction
— elle est faite pour le téléphone d'abord, en français, sobre.

## Vos données sont protégées

- Les fiches vivent dans **votre** Google Sheet, sur **votre** Drive — pas de
  base de données tierce.
- Traitement en **Europe** (région de Paris).
- Les photos ne sont pas conservées après traitement.
- Ce dépôt public ne contient **que des données fictives**.

## Un exemple (fictif)

Le cas de démonstration — **Jeanne Martin, 84 ans** — est entièrement fictif :
deux pages de notes d'entretien, la fiche attendue avec ses champs manquants
et les questions suggérées à la famille. Voir `examples/jeanne_martin/`.

## Installation (aspect technique)

### Prérequis
- Python 3.13 · Node.js 20+ · un projet Google Cloud
- l'outil `gcloud` connecté

### Mise en place
```bash
pip install -e .          # dépendances Python (Python 3.13 requis)
npm install               # dépendances Node (package docx pour le déroulé Word)
cp .env.example .env      # puis remplissez .env avec vos identifiants (jamais versionné)
python agents/auth.py     # consentement OAuth unique (Gmail + Drive)
```

### Lancement
```bash
python ui/app.py          # http://localhost:8002 — AUTH_MODE=off par défaut en local
```

## Comment c'est construit

Quatre agents spécialisés (extraction, vérification, rédaction, orchestration)
construits avec **Google ADK**. Document et Email passent par les **API Google
directes** (Docs, Gmail — brouillons uniquement) ; l'écriture dans le registre
Sheet est **MCP-first** (`@mcp-z/mcp-sheets` via stdio) **avec repli
automatique sur l'API directe**. Un écran de validation **A2UI** au centre —
la porte humaine ; un **skill** dédié met en forme le déroulé Word une page.
Le tout est hébergé sur **Cloud Run** (privé, région Paris, coût quasi nul au
repos). Détails techniques : [README anglais](README.md) et
[`specs/interface.md`](specs/interface.md).

### MCP-first, avec repli gracieux

L'intégration Sheet suit un design **MCP-first** : `append_ceremony_row` ouvre
une session stdio vers `@mcp-z/mcp-sheets`, découvre les outils à l'exécution
via `list_tools()` (jamais devinés), sélectionne `rows-append`, et mappe les
arguments depuis le `inputSchema` de l'outil. En cas d'erreur, repli
automatique sur l'API directe `googleapiclient` — chaque appel enregistre son
`integration_path` (`mcp` | `api_fallback` | `api`).

Trois particularités amont ont été identifiées en lisant le source du serveur
et neutralisées par des contournements minimaux documentés :

1. **Validation inconditionnelle de `GOOGLE_CLIENT_ID`** — `@mcp-z/oauth-google`
   v1.0.6 appelle `requiredEnv('GOOGLE_CLIENT_ID')` avant la branche
   `auth === 'service-account'` ; un dummy étiqueté satisfait la vérification.
2. **URIs `file://C:/` sous Windows** — le parser URL de Node prend la lettre
   du lecteur pour le host de l'URL ; `keyv-registry` double alors le chemin
   (`C:\C:\…`). Contournement : URIs de stockage en `file://~`.
3. **Environnement du processus fils** — construit depuis
   `get_default_environment()` du SDK MCP au lieu de `os.environ`, pour ne
   jamais transmettre de clé API ou de secret de session au code tiers.

Sur Cloud Run, le service tourne volontairement avec `USE_MCP_SHEETS=false` :
même si le conteneur embarque Node.js (pour le skill du déroulé Word), lancer
un serveur MCP communautaire via `npx` au moment de la requête ajouterait une
dépendance supply-chain et une latence de démarrage sur un chemin critique. La
production utilise donc l'API directe, durcie ; le chemin MCP est exercé et
prouvé en local et par la suite de tests (`integration_path=mcp`).

## Déploiement (Cloud Run) — optionnel

Le lancement local est pleinement fonctionnel (voir ci-dessus). Notre instance
tourne sur **europe-west9** (Paris), ouverte au réseau mais protégée par
l'application (Google Sign-In + liste d'adresses autorisées).

Les commandes exactes, les identités (compte de service, OAuth, clé Gemini),
la création des secrets et les notes de sécurité sont documentées dans le
[README anglais § Deployment](README.md#deployment-cloud-run--optional).

**Points clés :**
- Aucun secret, token ou mot de passe dans l'image, le dépôt ou le Dockerfile.
- `--allow-unauthenticated` : la porte est dans l'application, pas dans IAM.
- `--max-instances 1` : état en mémoire, mono-session pour la démo.
- Emails toujours en brouillon — jamais envoyés automatiquement.

## Observabilité (optionnel)

Traçage Langfuse opt-in : trois variables d'environnement (`LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`). **Par défaut, seules les métadonnées
opérationnelles sont transmises** (modèle, durée, statut) — jamais le contenu
des notes. `LANGFUSE_TRACE_CONTENT=true` active les payloads (dev fictif uniquement).

## Feuille de route

- **Aujourd'hui :** le parcours complet — photo → validation → déroulé Word,
  Doc, brouillon, registre. Observabilité Langfuse câblée (opt-in).
- **Ensuite :** IAP pour le contrôle d'accès organisationnel,
  et état par session pour le multi-utilisateur.

## Licence

MIT — voir [LICENSE](LICENSE).
