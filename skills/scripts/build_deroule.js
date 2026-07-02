#!/usr/bin/env node
/*
 * build_deroule.js — Génère un "déroulé des obsèques" mis en forme (.docx, 1 page A4).
 *
 * Usage :
 *   NODE_PATH=$(npm root -g) node build_deroule.js <entree.json> <sortie.docx> [--size N]
 *
 * --size N  : force la taille (en demi-points) des étapes (ex. 24 = 12pt). Sinon : auto.
 *
 * Voir references/exemple_deroule.json pour le format d'entrée.
 */
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun,
  AlignmentType, BorderStyle, LineRuleType,
} = require('docx');

// ---------- Palette & police ----------
const C_LABEL = "1F2A37"; // intitulés (gras)
const C_VAL   = "22303E"; // valeurs saisies
const C_INFO  = "5A6472"; // infos secondaires (église, célébrant, footer)
const C_TITLE = "2E3440"; // titre + nom du défunt
const C_RULE  = "B7BCC4"; // filets de séparation
const FONT    = "Georgia";

// ---------- Carte des émojis par intitulé liturgique ----------
const EMOJI = {
  "entrée": "🎶",
  "accueil": "🤍",
  "présentation du défunt": "🕊️",
  "chant d'entrée": "🎵",
  "rite de la lumière": "🕯️",
  "1ère lecture": "📖", "1ere lecture": "📖", "première lecture": "📖",
  "2ème lecture": "📖", "2eme lecture": "📖", "deuxième lecture": "📖",
  "psaume": "📜",
  "alléluia": "🎶", "alleluia": "🎶",
  "évangile": "📖", "evangile": "📖",
  "homélie": "💬", "homelie": "💬",
  "prière universelle": "🙏", "priere universelle": "🙏",
  "notre père": "🙏", "notre pere": "🙏",
  "chant d'adieu": "🎵",
  "encensement / bénédiction": "🌿", "encensement / benediction": "🌿", "encensement": "🌿",
  "prière à marie": "⚜️", "priere a marie": "⚜️",
  "bénédiction": "✝️", "benediction": "✝️",
  "sortie": "🕊️",
};

function normLabel(s) {
  return String(s)
    .toLowerCase()
    .replace(/[\u2019']/g, "'")     // apostrophes -> '
    .replace(/\s*:\s*$/, "")        // enlève un ":" final
    .replace(/\s+/g, " ")
    .trim();
}
function emojiFor(step) {
  if (step.emoji) return step.emoji;
  return EMOJI[normLabel(step.label)] || "\u2022"; // puce neutre par défaut
}

// Segments de texte : string -> [{t}] ; tableau [{t,i}] -> tel quel
function toSegments(v) {
  if (v == null) return [];
  if (typeof v === "string") return v.length ? [{ t: v }] : [];
  if (Array.isArray(v)) return v.filter(x => x && x.t != null);
  return [];
}

// ---------- Lecture de l'entrée ----------
const inputPath = process.argv[2];
const outPath = process.argv[3] || "deroule.docx";
let sizeOverride = null;
for (let i = 4; i < process.argv.length; i++) {
  if (process.argv[i] === "--size") sizeOverride = parseInt(process.argv[i + 1], 10);
}
if (!inputPath) {
  console.error("Usage: node build_deroule.js <entree.json> <sortie.docx> [--size N]");
  process.exit(1);
}
const data = JSON.parse(fs.readFileSync(inputPath, "utf8"));
const etapes = data.etapes || data.steps || [];

// ---------- Auto-dimensionnement pour tenir sur 1 page ----------
let bodyLines = 0;
for (const s of etapes) bodyLines += 1 + (toSegments(s.sub).length ? 1 : 0);
const totalLines = bodyLines + 7; // en-tête (~5) + footer (1) + marge (1)
function autoSize(n) {
  if (n <= 31) return 26; // 13pt
  if (n <= 35) return 25; // 12.5pt
  if (n <= 39) return 24; // 12pt
  if (n <= 44) return 23; // 11.5pt
  return 22;              // 11pt
}
const S    = sizeOverride || autoSize(totalLines); // taille des étapes (demi-points)
const SUB  = S - 2;
const INFO = S - 3;
const TTL  = S + 7;
const NAME = S + 2;
const FOOT = S - 3;
const EMB  = S + 15;
const lineMain   = Math.round(S * 11.5);
const lineSub    = Math.round(SUB * 11.7);
const beforeLabel = Math.round(S * 5.6);

// ---------- Helpers de rendu ----------
function rule(beforeS, afterS) {
  return new Paragraph({
    spacing: { before: beforeS, after: afterS },
    border: { bottom: { style: BorderStyle.SINGLE, size: 5, color: C_RULE, space: 1 } },
    children: [new TextRun({ text: "", size: 4 })],
  });
}
function info(emoji, label, value) {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 16, after: 16 },
    children: [
      new TextRun({ text: emoji + "\u00A0\u00A0", size: INFO }),
      new TextRun({ text: label, bold: true, size: INFO, color: C_LABEL, font: FONT }),
      new TextRun({ text: value, size: INFO, color: C_INFO, font: FONT }),
    ],
  });
}
function segRuns(segs, size) {
  return segs.map(p => new TextRun({ text: p.t, italics: !!p.i, size, color: C_VAL, font: FONT }));
}
function step(s) {
  const label = String(s.label).replace(/\s*:\s*$/, "") + " :";
  const runs = [
    new TextRun({ text: emojiFor(s) + "\u00A0\u00A0", size: S }),
    new TextRun({ text: label, bold: true, size: S, color: C_LABEL, font: FONT }),
  ];
  const inlineSegs = toSegments(s.inline != null ? s.inline : s.valeur);
  if (inlineSegs.length) {
    runs.push(new TextRun({ text: "\u00A0", size: S }));
    for (const p of inlineSegs) runs.push(new TextRun({ text: p.t, italics: !!p.i, size: S, color: C_VAL, font: FONT }));
  }
  const out = [new Paragraph({
    spacing: { before: beforeLabel, after: 0, line: lineMain, lineRule: LineRuleType.AT_LEAST },
    keepNext: true,
    children: runs,
  })];
  const subSegs = toSegments(s.sub);
  if (subSegs.length) {
    out.push(new Paragraph({
      indent: { left: 700 },
      spacing: { before: 14, after: 0, line: lineSub, lineRule: LineRuleType.AT_LEAST },
      children: segRuns(subSegs, SUB),
    }));
  }
  return out;
}

// ---------- Construction du document ----------
const children = [];

children.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { before: 0, after: 44 },
  children: [new TextRun({ text: data.embleme || "🕊️", size: EMB })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { before: 0, after: 46 },
  children: [new TextRun({ text: data.titre || "CÉLÉBRATION DES OBSÈQUES DE :", bold: true, size: TTL, color: C_TITLE, font: FONT, characterSpacing: 16 })],
}));
if (data.defunt) children.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { before: 0, after: 110 },
  children: [new TextRun({ text: data.defunt, bold: true, size: NAME, color: C_TITLE, font: FONT })],
}));
if (data.eglise) children.push(info("⛪", "Église : ", data.eglise));
if (data.celebrant) children.push(info("✝️", "Célébrant : ", data.celebrant));

children.push(rule(100, 60));

for (const s of etapes) for (const node of step(s)) children.push(node);

children.push(rule(150, 78));

if (data.prochaineMesse) children.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { before: 0, after: 0 },
  children: [
    new TextRun({ text: "📅\u00A0\u00A0", size: FOOT }),
    new TextRun({ text: "Prochaine Messe : ", bold: true, size: FOOT, color: C_LABEL, font: FONT }),
    new TextRun({ text: data.prochaineMesse, italics: true, size: FOOT, color: C_INFO, font: FONT }),
  ],
}));

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: S } } } },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 760, right: 1000, bottom: 720, left: 1000 } } },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(outPath, buf);
  console.log(`OK -> ${outPath}  (etapes ${S/2}pt, ~${totalLines} lignes estimees)`);
});
