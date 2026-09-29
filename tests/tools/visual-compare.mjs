#!/usr/bin/env node
/**
 * Compara duas capturas (ou duas pastas de capturas) e gera before/after/diff.
 *
 *   node tests/tools/visual-compare.mjs <antes.png|pasta> <depois.png|pasta> [--out reports/visual/<nome>] [--threshold 0.1]
 *
 * Fluxo típico antes/depois de uma mudança de UI:
 *   node tests/tools/audit-page.mjs --path /viagens/oficios/ --label antes
 *   (faz a mudança; reinicia o servidor do lab)
 *   node tests/tools/audit-page.mjs --path /viagens/oficios/ --label depois
 *   node tests/tools/visual-compare.mjs reports/audit/viagens-oficios-antes reports/audit/viagens-oficios-depois
 *
 * Para cada par grava before.png, after.png, diff.png e um compare.json com a razão de pixels
 * diferentes e a mudança de tamanho (largura/altura) — mudança de altura costuma ser o
 * primeiro sinal de espaçamento/overflow alterado.
 */
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";

const [a, b, ...rest] = process.argv.slice(2);
if (!a || !b) { console.error("uso: visual-compare.mjs <antes> <depois> [--out dir] [--threshold 0.1]"); process.exit(2); }
const opt = (n, d) => { const i = rest.indexOf(`--${n}`); return i >= 0 ? rest[i + 1] : d; };
const threshold = Number(opt("threshold", "0.1"));
const outRoot = opt("out", path.join("reports", "visual", `${path.basename(a)}__vs__${path.basename(b)}`));

function pad(img, w, h) {
  if (img.width === w && img.height === h) return img;
  const out = new PNG({ width: w, height: h });
  out.data.fill(255);
  PNG.bitblt(img, out, 0, 0, img.width, img.height, 0, 0);
  return out;
}

function comparar(fa, fb, out) {
  mkdirSync(out, { recursive: true });
  const A = PNG.sync.read(readFileSync(fa)), B = PNG.sync.read(readFileSync(fb));
  const w = Math.max(A.width, B.width), h = Math.max(A.height, B.height);
  const pa = pad(A, w, h), pb = pad(B, w, h), diff = new PNG({ width: w, height: h });
  const n = pixelmatch(pa.data, pb.data, diff.data, w, h, { threshold, includeAA: false });
  copyFileSync(fa, path.join(out, "before.png"));
  copyFileSync(fb, path.join(out, "after.png"));
  writeFileSync(path.join(out, "diff.png"), PNG.sync.write(diff));
  const r = { before: fa, after: fb, width: [A.width, B.width], height: [A.height, B.height], diffPixels: n, diffRatio: +(n / (w * h)).toFixed(5), sizeChanged: A.width !== B.width || A.height !== B.height };
  writeFileSync(path.join(out, "compare.json"), JSON.stringify(r, null, 2));
  return r;
}

const resultados = [];
if (statSync(a).isDirectory()) {
  for (const f of readdirSync(a).filter((f) => f.endsWith(".png") && !["before.png", "after.png", "diff.png"].includes(f)).sort()) {
    const fb = path.join(b, f);
    if (!existsSync(fb)) { resultados.push({ file: f, missingAfter: true }); continue; }
    resultados.push({ file: f, ...comparar(path.join(a, f), fb, path.join(outRoot, path.basename(f, ".png"))) });
  }
} else {
  resultados.push(comparar(a, b, outRoot));
}
mkdirSync(outRoot, { recursive: true });
writeFileSync(path.join(outRoot, "summary.json"), JSON.stringify(resultados, null, 2));
for (const r of resultados) console.log(`${r.file ?? path.basename(a)}: ${r.missingAfter ? "sem captura depois" : `${(r.diffRatio * 100).toFixed(2)}% pixels diferentes${r.sizeChanged ? ` · tamanho ${r.width.join("→")} × ${r.height.join("→")}` : ""}`}`);
console.log(`→ ${outRoot}/`);
