# Search Bench

Benchmark comparant plusieurs stratégies de recherche sur un même corpus documentaire (D&D 5e PDFs).

## Objectif

Évaluer et comparer la qualité de recherche de 7 stratégies :

### Agents contraints (stratégie imposée)
1. **BM25 simple** — Recherche lexicale en 2 passes max (initial + gap-filling)
2. **BM25 2-round** — Passe 1 = expansion + recherche large, Passe 2 = recherche ciblée sur les manques
3. **Vector DB naive** — Embedding + recherche cosine via Qdrant (1 passe)
4. **Vector DB 2-round** — Vector search en 2 passes (même logique que BM25 2-round)

### Agents libres (stratégie au choix du LLM)
5. **BM25 libre** — BM25 sans contrainte de tours, le LLM décide sa stratégie
6. **Vector libre** — Qdrant sans contrainte de tours
7. **Hybride libre** — BM25 + Qdrant combinés, sans contrainte

## Architecture du benchmark

- **Agent de recherche** : Claude Sonnet, reçoit une question + un outil de recherche (un par stratégie)
- **Corpus** : Documents PDF D&D dans `docs/`
- **Arbitre** : Claude Opus évalue la qualité des résultats obtenus par chaque stratégie
- Chaque stratégie expose un outil MCP ou une fonction que l'agent Sonnet peut appeler
- Le scoring est standardisé pour permettre une comparaison objective

## Stack technique

- **Approche** : Chaque stratégie = un script standalone (Python ou TS, peu importe), appelé par un agent
- **BM25** : `bm25s` + PyStemmer (Python, via `uv`)
- **Vector DB** : Qdrant via Docker (`qdrant/qdrant`)
- **Embeddings** : FastEmbed (`sentence-transformers/all-MiniLM-L6-v2`, 384 dims)
- **LLM** : Claude API (Anthropic SDK) — Sonnet pour les agents, Opus pour l'arbitrage
- **PDF parsing** : Extraction de texte depuis les PDFs du corpus
- **Python** : géré via `uv` (venv local)
- **TS** : `yarn` + `tsx`

## Commandes

```bash
# Indexation BM25 (une seule fois, ou après ajout de PDFs)
PYTHONIOENCODING=utf-8 uv run python tools/bm25_index.py

# Recherche BM25
PYTHONIOENCODING=utf-8 uv run python tools/bm25_search.py "query" --top-k 10
```

## Scoring

Voir `scoring.md` pour la grille de notation complète. En résumé :

- **Score final = Quality (80%) + Efficiency (20%)**
- **Quality (0–10)** : Accuracy (0–5) + Completeness (0–3) + Faithfulness (0–2), jugé par Opus
- **Efficiency (0–10)** : Latency (0–5) + Token usage (0–5), normalisé par groupe
- Questions de benchmark dans `questions.json` (simple → complex)
- Résultats détaillés dans `results/`

## Agents

### Agents contraints

| Agent | Stratégie | Moteur | Passes | maxTurns |
|-------|-----------|--------|--------|----------|
| `dnd-5e-researcher` | BM25 simple | bm25s | 1 | 2 |
| `dnd-5e-researcher-2round` | BM25 2-round | bm25s | 2 | 4 |
| `dnd-5e-researcher-vector` | Vector naive | Qdrant | 1 | 2 |
| `dnd-5e-researcher-vector-2round` | Vector 2-round | Qdrant | 2 | 4 |

### Agents libres

| Agent | Moteur | maxTurns |
|-------|--------|----------|
| `dnd-5e-researcher-bm25-free` | bm25s | défaut |
| `dnd-5e-researcher-vector-free` | Qdrant | défaut |
| `dnd-5e-researcher-hybrid-free` | bm25s + Qdrant | défaut |

## Conventions

- Package manager : **yarn** (pas npm/pnpm)
- Python : toujours lancer avec `PYTHONIOENCODING=utf-8` (Windows charmap fix)
- Langue du code : anglais
- Langue des commentaires / docs : français accepté
- Utiliser `rtk` pour toutes les commandes shell (cf. instructions globales)
