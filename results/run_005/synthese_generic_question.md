# Run 5 — Test de question générique : modèle vs moteur de recherche

## Objectif

Isoler l'impact du **modèle** (Haiku vs Sonnet) vs le **moteur de recherche** (BM25 vs Vector) sur une question volontairement vague, sans mots-clés discriminants.

## Question testée

> "What options do players have when things go badly in a fight and they're losing?"

Question générique, pas de termes D&D spécifiques, réponse dispersée dans plusieurs sections du SRD.

## Résultats comparatifs

| Métrique | BM25 Haiku | BM25 Sonnet | Vector Sonnet | Hybride Sonnet |
|---|---|---|---|---|
| Search calls | 3 | 6 | 6 | 6 |
| Tokens totaux | 31k | 47k | 59k | 48k |
| Durée | 9s | 44s | 36s | 41s |
| Options trouvées | 4 | 7 | 7 | 9 |

## Couverture détaillée

| Option | BM25 Haiku | BM25 Sonnet | Vector Sonnet | Hybride Sonnet |
|---|---|---|---|---|
| Disengage (fuite safe) | ✅ | ✅ | ✅ | ✅ |
| Dodge (défense) | ✅ | ✅ | ✅ | ✅ |
| Dash (double mouvement) | ❌ | ✅ | ✅ | ✅ |
| Surrender (reddition) | ✅ | ✅ | ✅ | ✅ |
| Movement / Retreat | ✅ | ✅ | ✅ | ✅ |
| Hide (se cacher) | ❌ | ❌ | ✅ | ❌ |
| Teleport (éviter OA) | ❌ | ❌ | ✅ | ❌ |
| Death Saving Throws | ❌ | ✅ | ✅ | ✅ |
| Stabilize ally (Medicine) | ❌ | ✅ | ✅ | ✅ |
| Healing (potions/sorts) | ❌ | ✅ | ❌ | ✅ |
| Massive Damage / Instant Death | ❌ | ❌ | ✅ | ❌ |
| Do Nothing / Stall / Ready | ❌ | ✅ | ❌ | ✅ |
| Class-specific (Second Wind, Patient Defense, Step of the Wind) | ❌ | ❌ | ❌ | ✅ |
| Healer's Kit (Utilize action) | ❌ | ❌ | ❌ | ✅ |

## Analyse

### Le delta principal vient du modèle, pas du moteur

BM25 Sonnet et Vector Sonnet trouvent la même profondeur de réponse (7 options chacun). Le facteur discriminant est **Sonnet vs Haiku** :

- **Sonnet** (quel que soit le moteur) fait 6 queries ciblées, explore les Death Saves, la stabilisation, le healing
- **Haiku** s'arrête à 3 queries et couvre uniquement les actions défensives directes (Disengage, Dodge, Movement, Surrender)

### L'hybride domine sur la couverture

L'hybride Sonnet (BM25 + Qdrant) trouve **9 options** — le meilleur résultat. Il est le seul à trouver les options class-specific (Second Wind, Patient Defense, Step of the Wind) et le Healer's Kit. L'alternance BM25/Qdrant dans ses queries lui permet de combiner les forces des deux moteurs :

- BM25 pour les lookups précis ("potion of healing bonus action drink", "death saving throw dying stabilize")
- Qdrant pour les concepts larges ("options when losing a fight, defensive tactics, surrender, retreat, stabilize dying")

### BM25 fonctionne bien sur du vague si le modèle sait reformuler

L'hypothèse initiale était que BM25 galèrerait sur une question générique faute de mots-clés discriminants. En réalité, Sonnet compense en générant des requêtes spécifiques :
- "dropping to zero hit points death saving throws unconscious"
- "Help action stabilize first aid healing potion unconscious"

Ces reformulations transforment une question vague en lookups précis — exactement la force de BM25.

### Vector a un léger avantage sur les concepts latents

Vector Sonnet trouve Hide et Teleport (concepts sémantiquement liés à "losing a fight" sans mots-clés directs) que BM25 Sonnet ne trouve pas. Inversement, BM25 Sonnet trouve Healing et Do Nothing que Vector ne remonte pas. Les différences sont marginales et **complémentaires** — ce que confirme la supériorité de l'hybride.

## Conclusion

1. **Le modèle compte plus que le moteur** : Sonnet vs Haiku fait plus de différence que BM25 vs Vector
2. **L'hybride est le meilleur sur les questions ouvertes** : 9 options trouvées vs 7 pour les moteurs seuls — les forces de BM25 et Vector sont complémentaires
3. **BM25 seul n'est pas pénalisé par le vague** si le modèle sait reformuler en lookups précis
4. **Le moteur ne devient le facteur limitant** que sur du contenu structurellement mal adapté (stat blocks tabulaires pour les embeddings)
