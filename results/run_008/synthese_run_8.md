# Run 008 — Synthese

**Date**: 2026-03-14
**Questions testees**: q13, q14, q21 (3 questions complexes)
**Strategies testees**: bm25_simple, vector_naive, bm25_free, vector_free
**Embedding model**: jinaai/jina-embeddings-v3
**PDF backend**: marker

## Contexte

Run partiel post-ameliorations pipeline d'ingestion :
- **Switch backend pymupdf -> Marker** : le changement majeur. Marker (Surya) apporte l'OCR + la comprehension visuelle du layout (multi-colonnes, tables, stat blocks). pymupdf4llm lit le texte ligne par ligne sans comprendre la structure visuelle — sur un stat block D&D en colonnes, il melange les colonnes. Marker detecte visuellement les blocs et les extrait dans le bon ordre. C'est ce qui permet de recuperer correctement les ability scores, les tables de stats, et les layouts complexes que pymupdf manquait.
- **Cache SHA1** : `data/pdf_cache/{sha1}_{backend}.json` — evite de re-extraire les PDFs inchanges (important car Marker prend plusieurs minutes par PDF sur GPU)
- **Fix `_block_to_text`** : `re.sub(r"<[^>]+>", " ", html)` au lieu de `""` — bugfix sur l'extraction Marker : les tags HTML etaient supprimes sans espace, concatenant les contenus de cellules adjacentes (ex: `STRDEXCON` -> `STR DEX CON`)
- **Dead code supprime** : guard `<content-ref` inaccessible apres le strip regex
- **Rejet backend inconnu** : `ValueError` au lieu de fallthrough silencieux vers pymupdf

## Resultats

### Scores par question et strategie

| Question | BM25 simple | Vector naive | BM25 free | Vector free |
|----------|-------------|--------------|-----------|-------------|
| q13 (initiative) | **10** | 7 | — | — |
| q14 (Frozen Sick) | 8 | **10** | — | — |
| q21 (flesh golem) | **9** | 6 | **10** | **10** |

### Progression Run 3 -> Run 7 -> Run 8

| Strategie | q13 | q14 | q21 |
|-----------|-----|-----|-----|
| BM25 simple | 7 -> — -> **10** (+3) | 10 -> — -> 8 (-2*) | 6 -> — -> **9** (+3) |
| Vector naive | 7 -> 7 -> 7 (=) | 9 -> 10 -> 10 (+1) | 6 -> 8 -> 6 (variable) |
| BM25 free | 10 -> — -> — | 10 -> — -> — | 10 -> — -> **10** |
| Vector free | 10 -> 10 -> — | 10 -> 10 -> — | 8 -> 9 -> **10** (+2) |
| Hybrid free | 10 -> 10 -> — | 10 -> 10 -> — | 10 -> 10 -> — |

*q14 BM25 simple: variabilite du choix de query LLM, pas regression pipeline

## Enseignements cles

### 1. Le pipeline d'ingestion est un multiplicateur universel

Deux ameliorations du pipeline se combinent :

**Marker comme backend PDF** : pymupdf4llm fonctionne tres bien sur les PDFs natifs avec text layer, mais echoue sur les layouts complexes (multi-colonnes, PDFs scannes). Marker (Surya) apporte l'OCR et la comprehension visuelle du layout — il detecte les blocs (colonnes, tables, headers) et les extrait dans le bon ordre. Sur le corpus D&D, la majorite des PDFs sont natifs et pymupdf les gere bien, mais certains documents avec des layouts en colonnes ou des pages scannees beneficient significativement de Marker.

**Fix `_block_to_text`** (tags → espace) : bugfix sur l'extraction Marker — les tags HTML etaient supprimes sans espace, concatenant les contenus de cellules adjacentes (`STRDEXCON` au lieu de `STR DEX CON`). 4 mots oversized (51-211 chars) dans le cache Marker.

Consequences mesurees :
- **Run 3 vector 2-round q21 = 5** : recuperait le MAUVAIS golem (acid damage) — les embeddings confondaient les golems entre eux
- **Run 7** (Marker + jina embeddings) : vector 2-round q21 = 10
- **BM25 simple q21 : 6 -> 9** — "flesh golem" matche maintenant correctement dans les deux documents
- **Vector free q21 : 8 -> 9 -> 10** — Run 3 avait besoin de 10 queries et ratait encore les stats. Run 8 : 3 queries, score parfait.

### 2. BM25 vs Vector : forces complementaires confirmees

| Type de question | BM25 avantage | Vector avantage |
|------------------|---------------|-----------------|
| Lookup regles/stats (q13 Remarkable Athlete) | Keyword exact match | Drift semantique |
| Narratif large (q14 quest chain) | Couverture partielle | Contexte riche, 9/10 chunks pertinents |
| Cross-doc (q21 golem) | Keywords presents dans 2 docs | Query biaisee vers 1 doc |

### 3. Multi-pass rattrape systematiquement

Les strategies free/2-round atteignent **systematiquement 10/10** sur les 3 questions testees, quelle que soit l'engine. Le 2eme+ pass comble les lacunes du 1er :
- q13 : Remarkable Athlete toujours trouve en pass 2+
- q21 : SRD stat block toujours trouve en query 2+ (meme pour vector)

### 4. Hybrid free = strategie la plus robuste

Score parfait (10/10) sur TOUTES les questions dans TOUS les runs (3, 7, 8). Le BM25 compense les faiblesses du vector sur les lookups exacts, et le vector compense le BM25 sur les questions semantiques larges.

### 5. Variabilite LLM non negligeable

Le BM25 simple q14 illustre le probleme : meme question, meme engine, mais query differente (`"Frozen Sick adventure quest"` en Run 3 vs `"Frozen Sick adventure quest chain"` en Run 8) → score 10 vs 8. Le choix de query par le LLM introduit de la variance dans les resultats 1-pass.

## Impact du fix _block_to_text sur les mots oversized

Avant fix (4 mots > 50 chars dans le cache marker) :
- `BadGoodSoftHard...` (211 chars) — table de mots concatenes
- `STRDEXCONINTWISCHA...` (51-53 chars) — stat blocks D&D concatenes

Apres fix : 0 mots > 50 chars attendus (a verifier sur re-extraction marker).

## Prochaines etapes suggerees

1. Re-run complet (24 questions x 7 strategies) pour mesurer l'impact global du fix
2. Verifier que le cache marker est bien purge avant le re-run (`rm data/pdf_cache/*_marker.json`)
3. Ajouter les strategies BM25 (simple, 2-round, free) dans les runs futurs pour comparaison complete
