"""clean_text() removes the per-page purchase watermark of bought PDFs."""

import pytest

from tools.pdf_utils import clean_text

WATERMARK = (
    "PDF réservé à l'usage de THOMAS HOUSSIN. Commande n°10160. Partage interdit."
)


def test_exact_watermark_is_removed():
    assert clean_text(WATERMARK).strip() == ""


@pytest.mark.parametrize(
    "variant",
    [
        "PDF réservé à l'usage de THOMAS HOUSSIN.\nCommande n°10160.\nPartage interdit.",
        "PDF\nréservé\nà\nl'usage\nde THOMAS HOUSSIN.\n\nCommande\nn°10160.\nPartage\ninterdit.",
        "PDF réservé à l’usage de THOMAS HOUSSIN. Commande n°10160. Partage interdit.",
        "PDF réservé à l'usage de THOMAS HOUSSIN. Commande n° 10160. Partage interdit.",
        "PDF réservé à l'usage de THOMAS HOUSSIN. Commande n 10160. Partage interdit.",
        "PDF réservé à l'usage de THOMAS HOUSSIN. Commande n°10160. Partage interdit",
        "PDF réservé à l'usage de THOMAS HOUSSIN. Commande nº10160. Partage interdit.",
        "pdf RÉSERVÉ à l'usage de thomas houssin. commande N°10160. partage INTERDIT.",
    ],
    ids=[
        "newlines-between-parts",
        "newlines-everywhere",
        "typographic-apostrophe",
        "space-after-degree",
        "no-degree-sign",
        "missing-final-dot",
        "ordinal-indicator",
        "case-insensitive",
    ],
)
def test_watermark_variants_are_removed(variant):
    result = clean_text(variant)
    assert result.strip() == ""
    assert "Commande" not in result and "interdit" not in result.lower()


def test_different_buyer_name_and_order_number_are_removed():
    text = "PDF réservé à l'usage de Marie-Claire Dupont-Martin. Commande n°7. Partage interdit."
    assert clean_text(text).strip() == ""


def test_surrounding_text_is_preserved():
    text = f"Chapitre 1 : le feu.\n{WATERMARK}\nChapitre 2 : l'eau."
    result = clean_text(text)
    assert "Chapitre 1 : le feu." in result
    assert "Chapitre 2 : l'eau." in result
    assert "THOMAS" not in result and "10160" not in result
    assert result.split() == [
        "Chapitre",
        "1",
        ":",
        "le",
        "feu.",
        "Chapitre",
        "2",
        ":",
        "l'eau.",
    ]


def test_watermark_inline_between_words_keeps_words_separated():
    # The match is replaced by a space, so neighbouring words do not fuse.
    result = clean_text(f"avant{WATERMARK}après")
    assert result.split() == ["avant", "après"]


def test_watermark_repeated_twice_is_removed_twice():
    text = f"{WATERMARK}\nPremier paragraphe.\n{WATERMARK}\nSecond paragraphe."
    result = clean_text(text)
    assert result.split() == ["Premier", "paragraphe.", "Second", "paragraphe."]


def test_watermark_removed_alongside_other_normalizations():
    text = f"Voir http://example.com <br>{WATERMARK}"
    assert clean_text(text).split() == ["Voir", "[url", "deleted]"]


@pytest.mark.parametrize(
    "text",
    [
        "La Commande n°12 du roi fut exécutée.",
        "Commande n°10160. Partage interdit.",
        "Partage interdit dans la forêt.",
        "Le Partage des terres. La Commande suivante.",
        "PDF réservé à l'usage interne.",
        "Commande",
        "Partage",
    ],
)
def test_text_with_only_part_of_the_watermark_is_unchanged(text):
    assert clean_text(text) == text
