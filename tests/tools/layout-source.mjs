// Fonte única da varredura de layout: usada pelos testes (tests/support/layout.ts)
// e pelo motor de auditoria (tests/tools/audit-page.mjs). Roda DENTRO da página.
export const layoutIssuesSource = () => {
    const out = [];
    const vw = document.documentElement.clientWidth;
    const sel = (el) => {
      if (el.id) return `#${el.id}`;
      const cls = (el.getAttribute("class") || "").trim().split(/\s+/).slice(0, 2).join(".");
      return `${el.tagName.toLowerCase()}${cls ? "." + cls : ""}`;
    };
    if (document.documentElement.scrollWidth > vw + 1) {
      out.push({ kind: "page-overflow-x", detail: `scrollWidth ${document.documentElement.scrollWidth}px > viewport ${vw}px` });
    }
    const vistos = new Set();
    for (const el of Array.from(document.body.querySelectorAll("*"))) {
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.position === "fixed") continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      // Dentro de um contêiner com rolagem horizontal (tabela responsiva) é intencional.
      let rolavel = false;
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const o = getComputedStyle(p).overflowX;
        if (o === "auto" || o === "scroll" || o === "hidden" || o === "clip") { rolavel = true; break; }
      }
      if (!rolavel && r.right > vw + 1 && !vistos.has(sel(el))) {
        vistos.add(sel(el));
        out.push({ kind: "element-overflow", detail: `direita em ${Math.round(r.right)}px (viewport ${vw}px)`, selector: sel(el) });
      }
      if (el.closest(".sr-only, .visually-hidden")) continue;
      if (el.scrollWidth > el.clientWidth + 2 && cs.overflowX === "hidden" && cs.textOverflow !== "ellipsis" && el.children.length === 0 && (el.textContent || "").trim()) {
        out.push({ kind: "clipped-text", detail: `texto cortado sem reticências: “${(el.textContent || "").trim().slice(0, 40)}”`, selector: sel(el) });
      }
      if (el.matches("a,button,input:not([type=hidden]),select,[role=button]") && vw < 500 && (r.width < 24 || r.height < 24)) {
        out.push({ kind: "tiny-target", detail: `alvo de toque ${Math.round(r.width)}×${Math.round(r.height)}px (< 24px, WCAG 2.5.8)`, selector: sel(el) });
      }
    }
    return out.slice(0, 80);
  };
