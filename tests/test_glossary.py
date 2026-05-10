"""Tests for glossary loading and prompt formatting."""

from pipeline.glossary import Glossary


def test_load_default_glossary():
    g = Glossary.load()
    assert len(g.terms) > 30
    assert len(g.do_not_translate) >= 10


def test_glossary_has_both_term_kinds():
    g = Glossary.load()
    translated = [t for t in g.terms if t.ua_term]
    kept = [t for t in g.terms if t.keep_english]
    assert len(translated) >= 10
    assert len(kept) >= 10


def test_no_term_is_simultaneously_translated_and_kept_english():
    """Sanity: a term either translates or stays English, not both."""
    g = Glossary.load()
    for t in g.terms:
        assert not (t.ua_term and t.keep_english), (
            f"Term '{t.en}' has both ua_term and keep_english=True"
        )


def test_format_for_prompt_includes_all_sections():
    g = Glossary.load()
    text = g.format_for_prompt()
    assert "### Translate" in text
    assert "### Keep English" in text
    assert "### Never translate" in text
    # Spot check known entries
    assert "трансформер" in text
    assert "*embedding*" in text
    assert "PyTorch" in text


def test_known_canonical_translations_present():
    """Anchor tests — these terms must always have these UA mappings."""
    g = Glossary.load()
    by_en = {t.en: t for t in g.terms}
    assert by_en["transformer"].ua_term == "трансформер"
    assert by_en["loss function"].ua_term == "функція втрат"
    assert by_en["overfitting"].ua_term == "перенавчання"


def test_known_keep_english_terms():
    """These should always stay English in italics."""
    g = Glossary.load()
    by_en = {t.en: t for t in g.terms}
    for term in ("embedding", "attention", "fine-tuning", "prompt", "inference"):
        assert by_en[term].keep_english is True, f"{term} should keep_english"
