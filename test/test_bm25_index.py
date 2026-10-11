"""Search the filename while preserving the original chunk corpus."""

from copy import deepcopy
from unittest.mock import Mock

import bm25s
import pytest
import Stemmer

from bm25_index import build_bm25_index


@pytest.mark.parametrize("separator", ["/", "\\"])
def test_filename_search_survives_reload_without_changing_chunks(
    tmp_path, monkeypatch, separator
):
    title = "Éveil.v2 - 3e édition (Révélation)"
    source = separator.join(["MJ", "PJ", "N3", title + ".pdf"])
    chunks = [
        {"source": source, "text": "magie alchimie", "pages": [1], "chunk_id": 0},
        {"source": source, "text": "soleil lune", "pages": [2], "chunk_id": 1},
        {"source": "Autre.txt", "text": "magie lune", "pages": [1], "chunk_id": 0},
    ]
    original = deepcopy(chunks)
    tokenize = Mock(wraps=bm25s.tokenize)
    monkeypatch.setattr(bm25s, "tokenize", tokenize)
    build_bm25_index(chunks, {"bm25_index_dir": tmp_path, "stemmer_language": "french"})
    assert tokenize.call_args.args[0] == [
        title + "\nmagie alchimie",
        title + "\nsoleil lune",
        "Autre\nmagie lune",
    ]
    loaded = bm25s.BM25.load(str(tmp_path), load_corpus=True)
    assert chunks == original
    assert list(loaded.corpus) == original
    stemmer = Stemmer.Stemmer("french")
    for query in ("Éveil", "3e", "Révélation", "Éveil 3e édition"):
        results = loaded.retrieve(bm25s.tokenize(query, stemmer=stemmer), k=2)
        assert {doc["chunk_id"] for doc in results.documents[0]} == {0, 1}
        assert all(doc["source"] == source for doc in results.documents[0])
        assert all(score > 0 for score in results.scores[0])
    assert not {"mj", "pj", "n3", "pdf", "txt"} & loaded.vocab_dict.keys()
