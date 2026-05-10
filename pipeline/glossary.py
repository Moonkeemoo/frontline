"""Load and format the glossary for inclusion in LLM prompts."""

from pathlib import Path

import yaml
from pydantic import BaseModel

DEFAULT_GLOSSARY_PATH = Path(__file__).parent / "glossary.yaml"


class GlossaryTerm(BaseModel):
    en: str
    ua_term: str | None = None
    keep_english: bool = False
    short: str | None = None
    alt_ua: str | None = None
    note: str | None = None


class Glossary(BaseModel):
    terms: list[GlossaryTerm]
    do_not_translate: list[str]

    @classmethod
    def load(cls, path: Path | None = None) -> "Glossary":
        target = path or DEFAULT_GLOSSARY_PATH
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        return cls(**data)

    def format_for_prompt(self) -> str:
        """Render glossary as a compact text block for inclusion in prompts."""
        lines: list[str] = []

        translated = [t for t in self.terms if t.ua_term]
        kept = [t for t in self.terms if t.keep_english]

        if translated:
            lines.append("### Translate (use UA term)")
            for t in translated:
                line = f"- {t.en} → {t.ua_term}"
                if t.note:
                    line += f"  — {t.note}"
                lines.append(line)
            lines.append("")

        if kept:
            lines.append("### Keep English in *italics*")
            for t in kept:
                line = f"- *{t.en}*"
                if t.short:
                    line += f" (alias: {t.short})"
                if t.alt_ua:
                    line += f" (alt UA: {t.alt_ua})"
                if t.note:
                    line += f"  — {t.note}"
                lines.append(line)
            lines.append("")

        if self.do_not_translate:
            lines.append("### Never translate (verbatim)")
            for name in self.do_not_translate:
                lines.append(f"- {name}")

        return "\n".join(lines).strip()
