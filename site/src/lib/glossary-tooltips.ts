/**
 * Wires glossary tooltips on .markdown-body content. Loads /glossary.json
 * once, scans <em> elements, attaches data-* attributes for CSS-driven
 * tooltips. Tap-to-toggle on touch devices.
 */

interface GlossaryTerm {
  en: string;
  ua_term?: string;
  short?: string;
  explanation?: string;
}

interface GlossaryDoc {
  terms: GlossaryTerm[];
  do_not_translate?: string[];
}

let cached: GlossaryTerm[] | null = null;

async function loadGlossary(): Promise<GlossaryTerm[]> {
  if (cached) return cached;
  try {
    const res = await fetch("/glossary.json");
    if (!res.ok) return [];
    const data = (await res.json()) as GlossaryDoc;
    cached = (data.terms || []).filter((t) => t.explanation);
    return cached;
  } catch {
    return [];
  }
}

function normalize(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, " ");
}

function attachTooltips(): void {
  void loadGlossary().then((terms) => {
    if (terms.length === 0) return;
    const byKey = new Map<string, GlossaryTerm>();
    for (const t of terms) {
      byKey.set(normalize(t.en), t);
      if (t.short) byKey.set(normalize(t.short), t);
    }

    const containers = document.querySelectorAll<HTMLElement>(".markdown-body");
    containers.forEach((container) => {
      container.querySelectorAll<HTMLElement>("em").forEach((em) => {
        const key = normalize(em.textContent || "");
        const term = byKey.get(key);
        if (!term || !term.explanation) return;
        em.classList.add("g-term");
        em.setAttribute("data-tooltip", term.explanation);
        if (term.ua_term) {
          em.setAttribute("data-ua", `(укр.: ${term.ua_term})`);
        }
        em.setAttribute("tabindex", "0");
        em.setAttribute("aria-label", `${term.en}: ${term.explanation}`);
      });
    });
  });

  // Mobile: tap-to-toggle (since :hover doesn't work)
  document.addEventListener("click", (e) => {
    const target = e.target as HTMLElement;
    if (target.classList?.contains("g-term")) {
      // close any others
      document.querySelectorAll(".g-term.g-active").forEach((el) => {
        if (el !== target) el.classList.remove("g-active");
      });
      target.classList.toggle("g-active");
    } else {
      document
        .querySelectorAll(".g-term.g-active")
        .forEach((el) => el.classList.remove("g-active"));
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", attachTooltips);
} else {
  attachTooltips();
}
