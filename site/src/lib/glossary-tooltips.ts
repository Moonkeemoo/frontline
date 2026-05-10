/**
 * Wires glossary tooltips on .markdown-body content.
 *
 * V2: walks ALL text nodes (not just <em>) so translated UA terms
 * (трансформер, перенавчання, функція втрат) get tooltips too —
 * not just the English-in-italic forms.
 */

interface GlossaryTerm {
  en: string;
  ua_term?: string;
  short?: string;
  explanation?: string;
}

interface GlossaryDoc {
  terms: GlossaryTerm[];
}

const SKIP_TAGS = new Set([
  "CODE",
  "PRE",
  "SCRIPT",
  "STYLE",
  "A",
  "H1",
  "H2",
  "H3",
  "H4",
  "BUTTON",
]);

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

function buildLookups(
  terms: GlossaryTerm[],
): Array<[string, GlossaryTerm]> {
  const list: Array<[string, GlossaryTerm]> = [];
  for (const t of terms) {
    if (!t.explanation) continue;
    list.push([t.en, t]);
    if (t.short) list.push([t.short, t]);
    if (t.ua_term) list.push([t.ua_term, t]);
  }
  // Longest first so "language model" matches before "model"
  list.sort((a, b) => b[0].length - a[0].length);
  return list;
}

function escapeRegex(s: string): string {
  return s.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
}

function collectTextNodes(root: HTMLElement): Text[] {
  const nodes: Text[] = [];
  const stack: Node[] = [root];
  while (stack.length) {
    const node = stack.pop()!;
    if (node.nodeType === Node.TEXT_NODE) {
      nodes.push(node as Text);
      continue;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) continue;
    const el = node as Element;
    if (SKIP_TAGS.has(el.tagName)) continue;
    if (el.classList && el.classList.contains("g-term")) continue;
    for (let i = el.childNodes.length - 1; i >= 0; i--) {
      stack.push(el.childNodes[i]);
    }
  }
  return nodes;
}

function wrapInTextNode(
  textNode: Text,
  lookups: Array<[string, GlossaryTerm]>,
): void {
  const text = textNode.textContent || "";
  if (text.length < 3 || !text.trim()) return;

  let earliest: {
    start: number;
    end: number;
    matched: string;
    term: GlossaryTerm;
  } | null = null;

  for (const [key, term] of lookups) {
    // Word-boundary using Unicode letter class (\p{L}) so Cyrillic works.
    const re = new RegExp(
      `(?<![\\p{L}\\d])${escapeRegex(key)}(?![\\p{L}\\d])`,
      "iu",
    );
    const m = re.exec(text);
    if (m && m.index !== undefined) {
      if (!earliest || m.index < earliest.start) {
        earliest = {
          start: m.index,
          end: m.index + m[0].length,
          matched: m[0],
          term,
        };
      }
    }
  }

  if (!earliest || !earliest.term.explanation) return;

  const parent = textNode.parentNode;
  if (!parent) return;

  const before = text.substring(0, earliest.start);
  const matched = earliest.matched;
  const after = text.substring(earliest.end);

  if (before) {
    parent.insertBefore(document.createTextNode(before), textNode);
  }

  const span = document.createElement("span");
  span.className = "g-term";
  span.setAttribute("data-tooltip", earliest.term.explanation);
  span.setAttribute("tabindex", "0");
  span.setAttribute(
    "aria-label",
    `${earliest.term.en}: ${earliest.term.explanation}`,
  );
  span.textContent = matched;
  parent.insertBefore(span, textNode);

  if (after) {
    const afterNode = document.createTextNode(after);
    parent.insertBefore(afterNode, textNode);
    parent.removeChild(textNode);
    wrapInTextNode(afterNode, lookups);
  } else {
    parent.removeChild(textNode);
  }
}

function attachTooltips(): void {
  void loadGlossary().then((terms) => {
    if (terms.length === 0) return;
    const lookups = buildLookups(terms);
    document
      .querySelectorAll<HTMLElement>(".markdown-body")
      .forEach((container) => {
        const nodes = collectTextNodes(container);
        for (const node of nodes) wrapInTextNode(node, lookups);
      });
  });

  // Mobile tap-to-toggle (since :hover doesn't fire)
  document.addEventListener("click", (e) => {
    const target = e.target as HTMLElement;
    if (target.classList?.contains("g-term")) {
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
