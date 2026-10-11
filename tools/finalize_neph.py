"""Validate a reviewed BM25 build and export its aligned NumPy PJ mask."""

import argparse
from collections import Counter, defaultdict
from importlib.metadata import version
import json
from pathlib import Path, PurePosixPath

import bm25s
import numpy as np

from rebuild_neph import DEFAULT_OUTPUT, fingerprint, now, write_json

INDEX_FILES = (
    "corpus.jsonl",
    "corpus.mmindex.json",
    "data.csc.index.npy",
    "indices.csc.index.npy",
    "indptr.csc.index.npy",
    "params.index.json",
    "vocab.index.json",
)


def make_pj_mask(corpus):
    """One float32 weight per saved corpus row; all paths containing MJ excluded."""
    return np.asarray(
        [0.0 if "mj" in doc["source"].casefold() else 1.0 for doc in corpus],
        dtype=np.float32,
    )


def validate_corpus(corpus, report, source):
    rows = {row["source"]: row for row in report["files"]}
    if len(rows) != len(report["files"]):
        raise ValueError("Duplicate source paths in ingestion report")
    actual = {
        p.relative_to(source).as_posix(): p for p in source.rglob("*") if p.is_file()
    }
    if set(actual) != set(rows) or len(rows) != report["discovered_files"]:
        raise ValueError("Source inventory differs from ingestion report")
    for name, row in rows.items():
        if fingerprint(actual[name]) != row["sha256"]:
            raise ValueError(f"Source changed: {name}")
        if row["status"] not in {"extracted", "ignored", "excluded_after_review"}:
            raise ValueError(f"Unresolved extraction: {name} ({row['status']})")
        if row["status"] == "excluded_after_review" and not row.get("review_note"):
            raise ValueError(f"Missing review evidence: {name}")
    groups = defaultdict(list)
    for doc in corpus:
        name = doc["source"]
        path = PurePosixPath(name)
        if name not in rows or path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError(f"Invalid chunk source: {name}")
        if rows[name]["status"] != "extracted" or not doc["text"].strip():
            raise ValueError(f"Invalid extracted chunk: {name}")
        pages = doc["pages"]
        if (
            not pages
            or pages != sorted(set(pages))
            or any(type(p) is not int or p < 1 for p in pages)
        ):
            raise ValueError(f"Invalid page references: {name}")
        groups[name].append(doc)
    if len(corpus) != report["total_chunks"]:
        raise ValueError("Chunk total differs from ingestion report")
    for name, row in rows.items():
        docs = groups.get(name, [])
        if len(docs) != row["chunks"] or (row["status"] == "extracted" and not docs):
            raise ValueError(f"Chunk count mismatch: {name}")
        if [d["chunk_id"] for d in docs] != list(range(len(docs))):
            raise ValueError(f"Chunk IDs out of sequence: {name}")
    # Check actual page bounds, not the count of nonempty extracted pages.
    import pymupdf

    for name, docs in groups.items():
        if name.lower().endswith(".pdf"):
            with pymupdf.open(actual[name]) as pdf:
                if max(p for d in docs for p in d["pages"]) > len(pdf):
                    raise ValueError(f"Page out of PDF bounds: {name}")
        elif any(d["pages"] != [1] for d in docs):
            raise ValueError(f"Unexpected logical page for non-PDF: {name}")
    return groups


def ocr_overrides(report):
    """Sources whose cached extraction came from another engine (marker2_reextract.py)."""
    cache_dir = Path(report["config"]["cache_dir"])
    overrides = {}
    for row in report["files"]:
        if not row.get("sha1") or not row.get("cache_backend"):
            continue
        path = cache_dir / f"{row['sha1']}_{row['cache_backend']}.json"
        if path.exists():
            engine = json.loads(path.read_text(encoding="utf-8")).get("engine")
            if engine:
                overrides[row["source"]] = engine
    return overrides


def coverage_notes(report, stats, overrides, groups):
    """README paragraphs derived from the reviewed report, not from a fixed text."""
    lines = []
    excluded = [
        row for row in report["files"] if row["status"] == "excluded_after_review"
    ]
    if excluded:
        lines.append("Exclus après validation utilisateur :")
        lines += [f"- `{row['source']}` : {row['review_note']}" for row in excluded]
        lines.append("")
    if overrides:
        lines.append(
            "Ré-extraits avec un autre moteur OCR que celui de `manifest.json` :"
        )
        for source, engine in sorted(overrides.items()):
            options = ", ".join(
                k for k, v in engine.get("config", {}).items() if v is True
            )
            lines.append(
                f"- `{source}` : marker-pdf {engine.get('marker-pdf')}, "
                f"surya-ocr {engine.get('surya-ocr')}"
                + (f" ({options})" if options else "")
            )
        lines.append("")
    ignored = stats["statuses"].get("ignored", 0)
    if ignored:
        lines.append(
            f"Les {ignored} fichiers de formats non pris en charge restent hors index."
        )
    if any("CDA5_ADJ6" in name for name in groups):
        lines += [
            "Le RTF CDA5_ADJ6 utilise une ancienne police Greek : les caractères stockés dans",
            "sa zone de texte ont été préservés, sans conversion conjecturale en grec Unicode.",
        ]
    return "\n".join(lines) + "\n"


def finalize(index_dir):
    index_dir = index_dir.resolve()
    if (index_dir / "manifest.json").exists():
        raise ValueError(
            "Manifest already exists; verify existing artifacts instead of overwriting them"
        )
    report = json.loads(
        (index_dir / "ingestion_report.json").read_text(encoding="utf-8")
    )
    source = Path(report["config"]["docs_dir"])
    retriever = bm25s.BM25.load(str(index_dir), load_corpus=True)
    corpus = retriever.corpus
    if retriever.scores["num_docs"] != len(corpus):
        raise ValueError("BM25 matrix and corpus lengths differ")
    groups = validate_corpus(corpus, report, source)
    mask = make_pj_mask(corpus)
    mask_path = index_dir / "mask_pj.npy"
    if mask_path.exists():
        saved = np.load(mask_path, allow_pickle=False)
        if saved.dtype != np.float32 or not np.array_equal(saved, mask):
            raise ValueError("Existing mask does not match this index")
    else:
        with mask_path.open("xb") as stream:
            np.save(stream, mask, allow_pickle=False)
    saved = np.load(mask_path, allow_pickle=False)
    if (
        saved.shape != (len(corpus),)
        or saved.dtype != np.float32
        or not np.array_equal(saved, mask)
    ):
        raise ValueError("Mask readback failed")
    stats = {
        "source_files": len(report["files"]),
        "indexed_documents": len(groups),
        "chunks": len(corpus),
        "pj_chunks": int(np.count_nonzero(saved)),
        "mj_chunks": int(np.count_nonzero(saved == 0)),
        "pj_documents": sum("mj" not in name.casefold() for name in groups),
        "mj_documents": sum("mj" in name.casefold() for name in groups),
        "statuses": dict(Counter(row["status"] for row in report["files"])),
        "indexed_formats": dict(Counter(Path(name).suffix.lower() for name in groups)),
    }
    reviewed_at = now()
    validation = {
        "status": "passed",
        "validated_at": reviewed_at,
        "statistics": stats,
        "checks": [
            "source_inventory_and_sha256",
            "bm25_reload_and_matrix_length",
            "per_document_chunk_counts_and_ids",
            "source_and_page_references",
            "mask_dtype_shape_and_binary_values",
            "all_MJ_paths_excluded",
            "all_non_MJ_paths_included",
            "saved_mask_readback",
        ],
    }
    write_json(index_dir / "final_validation.json", validation)
    report.update(status="finalized", reviewed_at=reviewed_at)
    write_json(index_dir / "ingestion_report.json", report)
    built = json.loads((index_dir / "index_built.json").read_text(encoding="utf-8"))
    built.update(
        status="finalized",
        chunks=len(corpus),
        empty_documents=0,
        reviewed_exclusions=stats["statuses"].get("excluded_after_review", 0),
        finalized_at=reviewed_at,
        next_step=None,
    )
    write_json(index_dir / "index_built.json", built)
    overrides = ocr_overrides(report)
    indexed_text_notice = (
        "Le nom du fichier sans extension est ajouté une fois avant le texte de chaque "
        "chunk pour l'indexation ; le champ `text` conserve le texte original."
        if report["config"].get("pipeline") == "neph-bm25-v2"
        else "Seul `text` est indexé."
    )
    notice = f"""# Index BM25 Neph et masque PJ

{stats["indexed_documents"]} documents indexés ; {stats["chunks"]} chunks.
Masque PJ : {stats["pj_chunks"]} chunks conservés, {stats["mj_chunks"]} exclus.

Copier ce dossier entier pour utiliser l'index dans un autre projet.
Les sources référencées sont relatives à `docs/Neph`, avec séparateurs `/`.
Le corpus conserve `text`, `source`, `pages`, `chunk_id`.
{indexed_text_notice}
PDF : pages physiques à partir de 1. Autres formats : page logique 1.
Les identifiants de chunks recommencent à zéro pour chaque source.

`mask_pj.npy` est un tableau NumPy float32 de forme ({stats["chunks"]},).
Chargement : `np.load('mask_pj.npy', allow_pickle=False)`.
La position i correspond exactement à la position i du corpus BM25 sauvegardé.
1.0 conserve le chunk ; 0.0 exclut tout chemin contenant MJ, sans distinction
de casse. Les ressources sans marquage PJ/MJ restent incluses dans ce masque.
Le corpus complet s'utilise sans masque. Paramètre natif bm25s : `weight_mask`.
Le masque pondère les scores ; les résultats à score nul doivent être traités
par le projet consommateur. Aucune logique de recherche n'est fournie ici.

Conserver l'index et son masque ensemble : une reconstruction change l'alignement.
`manifest.json` contient les paramètres, versions et empreintes SHA-256.
`ingestion_report.json` et `final_validation.json` détaillent la couverture.

{coverage_notes(report, stats, overrides, groups)}"""
    (index_dir / "README.md").write_text(notice, encoding="utf-8")
    artifacts = list(INDEX_FILES) + [
        "mask_pj.npy",
        "build_config.json",
        "index_built.json",
        "ingestion_report.json",
        "final_validation.json",
        "README.md",
    ]
    manifest = {
        "format_version": 1,
        "status": "finalized",
        "finalized_at": reviewed_at,
        "statistics": stats,
        "configuration": report["config"],
        "bm25_parameters": json.loads(
            (index_dir / "params.index.json").read_text(encoding="utf-8")
        ),
        "versions": {
            **report["versions"],
            "numpy": version("numpy"),
            "surya-ocr": version("surya-ocr"),
        },
        "mask": {
            "file": "mask_pj.npy",
            "dtype": "float32",
            "shape": [len(corpus)],
            "alignment": "saved corpus row order",
            "include": 1.0,
            "exclude": 0.0,
            "exclude_rule": "'mj' in source.casefold()",
        },
        "limitations": [row for row in report["files"] if row.get("review_note")],
        "ocr_overrides": overrides,
        "files": {
            name: {
                "sha256": fingerprint(index_dir / name),
                "bytes": (index_dir / name).stat().st_size,
            }
            for name in artifacts
        },
    }
    write_json(index_dir / "manifest.json", manifest)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(finalize(args.index_dir), ensure_ascii=True, indent=2))
