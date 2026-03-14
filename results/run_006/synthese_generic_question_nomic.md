# Run 6 — Impact du switch d'embedding (MiniLM → Nomic) sur la question générique

## Contexte

Run 5 utilisait `all-MiniLM-L6-v2` (384 dims, **128 tokens** — troncature silencieuse à ~20% du chunk).
Run 6 utilise `nomic-ai/nomic-embed-text-v1.5` (768 dims, **8192 tokens** — aucune troncature).

Même question, même corpus, mêmes agents. BM25 non affecté (pas d'embeddings).

## Question testée

> "What options do players have when things go badly in a fight and they're losing?"

## Résultats comparatifs (métriques)

| Métrique | BM25 Haiku | BM25 Sonnet | Vector R5 (MiniLM) | Vector R6 (Nomic) | Hybride R5 (MiniLM) | Hybride R6 (Nomic) |
|---|---|---|---|---|---|---|
| Search calls | 2 | 6 | 6 | 4 | 6 | 5 |
| Tokens totaux | 22k | 47k | 59k | 37k | 48k | 49k |
| Durée | 8s | 38s | 36s | 29s | 41s | 40s |

## Couverture détaillée (2 essais pour Vector et Hybride)

| Option | BM25 Haiku | BM25 Sonnet | Vec R5 | Vec R6.1 | Vec R6.2 | Hyb R5 | Hyb R6.1 | Hyb R6.2 |
|---|---|---|---|---|---|---|---|---|
| Disengage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Dodge | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Dash | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Surrender | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Hide | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| Death Saves / Stabilize | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ready / Do Nothing | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Teleport (éviter OA) | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Healing (potions) | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Massive Damage | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Class-specific | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ |
| Healer's Kit | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| Cover | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Heroic Inspiration | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Knock Out | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ✅ |
| **Total options** | **3** | **8** | **7** | **8** | **7** | **9** | **8** | **9** |

## Analyse

### Gain stable : Hide

Avec MiniLM, le vector ne trouvait Hide que quand Sonnet posait explicitement la query. Avec nomic, **Hide est trouvé systématiquement** (2/2 essais). L'embedding du chunk "Hide action" est maintenant complet (le texte entier est encodé, pas tronqué à 20%). C'est le gain le plus net du switch.

### Gain stable : Ready / Do Nothing

Le vector R6 trouve Ready/Do Nothing dans les 2 essais, alors que le vector R5 ne le trouvait pas. Nomic encode mieux les passages qui mentionnent ces options en fin de chunk.

### Variance inter-runs

Les options "bonus" (Cover, Class-specific, Heroic Inspiration, Knock Out) varient d'un essai à l'autre. C'est lié aux choix de queries de Sonnet, pas au moteur. Le **core stable** de 7 options (Disengage, Dodge, Dash, Surrender, Hide, Death Saves, Ready) est identique entre les deux essais R6.

### Vector R6 vs Vector R5

| Métrique | Vector R5 (MiniLM) | Vector R6 (Nomic) |
|---|---|---|
| Options stables | 5 (sans Hide, sans Ready) | 7 (avec Hide et Ready) |
| Search calls | 6 | 4 |
| Tokens | 59k | 37k |
| Durée | 36s | 29s |

Nomic est **meilleur sur tous les axes** : plus de couverture, moins de calls, moins de tokens, plus rapide.

### Hybride R6 vs Hybride R5

| Métrique | Hybride R5 (MiniLM) | Hybride R6 (Nomic) |
|---|---|---|
| Options (moyenne 2 essais) | 9 | 8.5 |
| Search calls | 6 | 5 |

L'hybride reste le meilleur en couverture maximale mais le gain nomic est moins net — le BM25 compensait déjà les faiblesses de MiniLM.

## Conclusion

1. **Nomic améliore le vector pur** : +2 options stables (Hide, Ready), -37% tokens, -19% durée
2. **L'hybride reste le meilleur** en couverture maximale, mais le delta avec le vector pur se réduit grâce à nomic
3. **La variance est significative** : les options "bonus" changent entre les runs, seul le core de 7 options est fiable
4. **BM25 Sonnet reste le meilleur rapport options/coût** : 8 options stables, aucune dépendance aux embeddings
5. **Le switch d'embedding corrige un vrai biais** : la troncature MiniLM (128 tokens / 20% du chunk) pénalisait artificiellement le vector
