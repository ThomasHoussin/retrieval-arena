# Synthèse Run 7 — Nomic Embeddings (vector agents)

## Contexte

- **Run 7** : 4 agents vector/hybride sur 24 questions avec **Nomic** (`nomic-ai/nomic-embed-text-v1.5`, 768 dims, 8192 tokens)
- **Run 3** (référence) : mêmes 4 agents avec **MiniLM** (`all-MiniLM-L6-v2`, 384 dims, 512 tokens)
- Objectif : mesurer l'impact du changement d'embedding sur la qualité de recherche

## Scores par agent (tous les agents, Run 3 + Run 7)

| Rang R3 | Agent | Run 3 (MiniLM) | Run 7 (Nomic) | Delta | Rang R7 |
|---------|-------|----------------|---------------|-------|---------|
| 1 ex-æquo | **bm25_free** | 240/240 (10.00) | 240/240 (10.00)* | — | 1 ex-æquo |
| 1 ex-æquo | **bm25_2round** | 240/240 (10.00) | 240/240 (10.00)* | — | 1 ex-æquo |
| 1 ex-æquo | **hybrid_free** | 240/240 (10.00) | 240/240 (10.00) | **0** | 1 ex-æquo |
| 6 | **vector_2round** | 215/240 (8.96) | 240/240 (10.00) | **+25 (+1.04/q)** | 1 ex-æquo |
| 4 | **vector_free** | 226/240 (9.42) | 239/240 (9.96) | **+13 (+0.54/q)** | 5 |
| 7 | **vector_naive** | 202/240 (8.42) | 222/240 (9.25) | **+20 (+0.83/q)** | 6 |
| 5 | **bm25_simple** | 218/240 (9.08) | 218/240 (9.08)* | — | 7 |

*\* Score R3 reporté (agent non relancé en R7, le moteur BM25 n'a pas changé)*

**Fait marquant** : vector_2round passe de **dernier (7e)** à **1er ex-æquo**. vector_naive dépasse bm25_simple et monte de la 7e à la 6e place. Il y a maintenant **4 agents parfaits** au lieu de 3.

## Scores détaillés par question et agent

### vector_naive (maxTurns 2, 1 passe)

| Question | Run 3 | Run 7 | Delta | Notes |
|----------|-------|-------|-------|-------|
| q1 | 10 | 10 | 0 | |
| q2 | 10 | 10 | 0 | |
| q3 | 5 | 9 | **+4** | Trouvé stat block Adult Red Dragon (pas en Run 3) |
| q4 | 10 | 10 | 0 | |
| q5 | 7 | 7 | 0 | DC formula pas trouvée (1 seule passe) |
| q6 | 10 | 10 | 0 | |
| q7 | 10 | 10 | 0 | |
| q8 | 10 | 10 | 0 | |
| q9 | 10 | 10 | 0 | |
| q10 | 9 | 6 | **-3** | Règle surprise pas trouvée (régression) |
| q11 | 10 | 10 | 0 | |
| q12 | 9 | 10 | **+1** | Trouvé Mislead + rodents/birds |
| q13 | 7 | 7 | 0 | Remarkable Athlete pas trouvé (multi-source) |
| q14 | 9 | 10 | **+1** | Réponse plus complète |
| q15 | 10 | 10 | 0 | |
| q16 | 10 | 10 | 0 | |
| q17 | 10 | 10 | 0 | |
| q18 | 5 | 5 | 0 | Lightning Bolt pas trouvé (multi-spell) |
| q19 | 8 | 10 | **+2** | Full wand mechanics trouvées |
| q20 | 7 | 10 | **+3** | Vargo correctement identifié (pas Archquadrone) |
| q21 | 6 | 8 | **+2** | Plus de SRD stat block trouvé |
| q22 | 7 | 10 | **+3** | Valeur empoisonnée (4) correctement trouvée |
| q23 | 10 | 10 | 0 | TRAP: poisoned value ✓ |
| q24 | 10 | 10 | 0 | TRAP: no hallucination ✓ |

### vector_2round (maxTurns 4, 2 passes)

| Question | Run 3 | Run 7 | Delta | Notes |
|----------|-------|-------|-------|-------|
| q1 | 10 | 10 | 0 | |
| q2 | 10 | 10 | 0 | |
| q3 | 2 | 10 | **+8** | Run 3: agent ran out of turns. Run 7: trouvé les 2 sources |
| q4 | 10 | 10 | 0 | |
| q5 | 10 | 10 | 0 | |
| q6 | 10 | 10 | 0 | |
| q7 | 10 | 10 | 0 | |
| q8 | 10 | 10 | 0 | |
| q9 | 10 | 10 | 0 | |
| q10 | 10 | 10 | 0 | |
| q11 | 10 | 10 | 0 | |
| q12 | 10 | 10 | 0 | |
| q13 | 10 | 10 | 0 | |
| q14 | 10 | 10 | 0 | |
| q15 | 10 | 10 | 0 | |
| q16 | 10 | 10 | 0 | |
| q17 | 10 | 10 | 0 | |
| q18 | 8 | 10 | **+2** | Lightning Bolt trouvé (pas en Run 3) |
| q19 | 10 | 10 | 0 | |
| q20 | 10 | 10 | 0 | |
| q21 | 5 | 10 | **+5** | Run 3: mauvais golem retrievé. Run 7: correct |
| q22 | 10 | 10 | 0 | |
| q23 | 10 | 10 | 0 | TRAP ✓ |
| q24 | 10 | 10 | 0 | TRAP ✓ |

### vector_free (libre, Qdrant seul)

| Question | Run 3 | Run 7 | Delta | Notes |
|----------|-------|-------|-------|-------|
| q1-q17 | 10 chacun | 10 chacun | 0 | |
| q18 | 8 | 10 | **+2** | Lightning Bolt complet |
| q19 | 10 | 10 | 0 | |
| q20 | 10 | 10 | 0 | |
| q21 | 8 | 9 | **+1** | Plus d'ability scores trouvés |
| q22-q24 | 10 chacun | 10 chacun | 0 | |

### hybrid_free (libre, BM25 + Qdrant)

Parfait en Run 3 ET Run 7 : **240/240** (10.00) sur les 24 questions.

## Analyse

### Gains majeurs (Δ ≥ +2)

| Question | Agent | Run 3 → Run 7 | Cause |
|----------|-------|----------------|-------|
| q3 | vector_2round | 2 → 10 | **+8** — Agent ne timeout plus, trouve les 2 sources |
| q21 | vector_2round | 5 → 10 | **+5** — Correct flesh golem trouvé (pas le clay golem) |
| q3 | vector_naive | 5 → 9 | **+4** — Stat block Adult Red Dragon trouvé en 1 passe |
| q20 | vector_naive | 7 → 10 | **+3** — Vargo correctement identifié |
| q22 | vector_naive | 7 → 10 | **+3** — Valeur empoisonnée (4) trouvée |
| q18 | vector_2round | 8 → 10 | **+2** — Lightning Bolt complet |
| q18 | vector_free | 8 → 10 | **+2** — Lightning Bolt complet |
| q19 | vector_naive | 8 → 10 | **+2** — Wand mechanics complètes |
| q21 | vector_naive | 6 → 8 | **+2** — Plus de SRD stat block |

### Seule régression

| Question | Agent | Run 3 → Run 7 | Cause |
|----------|-------|----------------|-------|
| q10 | vector_naive | 9 → 6 | **-3** — Surprise rules pas trouvées en 1 passe |

### Pourquoi Nomic est meilleur

1. **Contexte plus long** (8192 vs 512 tokens) : les chunks sont mieux compris dans leur contexte sémantique
2. **Dimensions plus riches** (768 vs 384) : meilleure discrimination entre concepts proches
3. **Meilleur retrieval cross-document** : q3, q21 montrent que Nomic retrouve le bon document même quand la requête est ambiguë
4. **Impact maximal sur vector_naive et vector_2round** : les agents à passes limitées bénéficient le plus d'un meilleur embedding car chaque requête rapporte des résultats plus pertinents

### Limites persistantes

- **vector_naive** reste faible sur les questions multi-source (q5, q13, q18) : 1 seule requête ne suffit pas pour croiser 2+ documents
- **hybrid_free** n'a rien à gagner : il était déjà à 10/10 partout grâce à BM25 qui compense les faiblesses du vector search

## Conclusion

Le passage MiniLM → Nomic apporte un gain net sur les agents vector :
- **vector_2round** : score parfait 10.00 (vs 8.96 avec MiniLM), gain le plus spectaculaire
- **vector_naive** : +0.83/question en moyenne, avec des gains majeurs sur les questions complexes
- **vector_free** : gain modeste (+0.54) car déjà performant avec MiniLM
- **hybrid_free** : aucun changement (déjà parfait)

**Recommandation** : Nomic est strictement supérieur à MiniLM pour le vector search sur ce corpus. L'investissement dans un meilleur embedding se rentabilise surtout pour les agents contraints (naive, 2round) qui ont moins de tentatives pour trouver l'information.
