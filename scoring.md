# Scoring Rubric

## Vue d'ensemble

Chaque question × chaque agent produit un **run**. Chaque run est évalué par un juge (Claude Opus) sur la qualité, puis les métriques d'efficacité sont mesurées automatiquement.

**Score final = Quality Score (pondération 80%) + Efficiency Score (pondération 20%)**

---

## 1. Quality Score (0–10, jugé par Opus)

### 1a. Accuracy (0–5 points)

Le cœur du benchmark : la réponse est-elle factuellement correcte par rapport à la réponse attendue ?

| Score | Critère |
|-------|---------|
| 5 | Tous les faits sont corrects et correspondent exactement à la réponse attendue |
| 4 | Essentiellement correct, imprécisions mineures (ex: arrondi, formulation) |
| 3 | Partiellement correct — quelques éléments justes, quelques erreurs |
| 2 | Erreurs majeures mais le raisonnement va dans la bonne direction |
| 1 | Majoritairement faux, un seul élément correct |
| 0 | Complètement faux, aucune réponse, ou "je n'ai pas trouvé" |

### 1b. Completeness (0–3 points)

Tous les aspects de la question sont-ils couverts ?

| Score | Critère |
|-------|---------|
| 3 | Tous les aspects de la question sont abordés avec le niveau de détail attendu |
| 2 | La plupart des aspects couverts, lacunes mineures |
| 1 | Lacunes significatives — des parties importantes manquent |
| 0 | Réponse très partielle ou hors sujet |

### 1c. Faithfulness — absence d'hallucination (0–2 points)

La réponse est-elle fidèle aux sources retrouvées, sans invention ?

| Score | Critère |
|-------|---------|
| 2 | Aucune hallucination — tout est appuyé par les résultats de recherche |
| 1 | Hallucination mineure — ajout de détails plausibles mais non sourcés |
| 0 | Hallucination majeure — faits inventés ou contredisant les sources |

### Calcul Quality Score

```
quality = accuracy + completeness + faithfulness
# Range: 0–10
```

---

## 2. Efficiency Score (0–10, mesuré automatiquement)

Les métriques d'efficacité sont normalisées par rapport au groupe (les 5 agents sur la même question).

### 2a. Latency (0–5 points)

Temps total du run (du lancement de l'agent à la réponse finale).

| Score | Critère |
|-------|---------|
| 5 | Le plus rapide du groupe (ou < 5s d'écart) |
| 4 | Dans les 25% les plus rapides |
| 3 | Médiane du groupe |
| 2 | Dans les 25% les plus lents |
| 1 | Le plus lent du groupe |
| 0 | Timeout (> 120s) ou échec |

### 2b. Token Usage (0–5 points)

Tokens totaux consommés (input + output de l'agent Sonnet + tokens des appels MCP).

| Score | Critère |
|-------|---------|
| 5 | Le moins de tokens du groupe (ou < 10% d'écart) |
| 4 | Dans les 25% les plus économes |
| 3 | Médiane du groupe |
| 2 | Dans les 25% les plus coûteux |
| 1 | Le plus coûteux du groupe |
| 0 | Échec ou tokens non mesurables |

### Calcul Efficiency Score

```
efficiency = latency_score + token_score
# Range: 0–10
```

---

## 3. Score Final

```
final_score = (quality × 0.8) + (efficiency × 0.2)
# Range: 0–10
```

### Interprétation

| Score | Niveau |
|-------|--------|
| 9–10 | Excellent — réponse parfaite et efficace |
| 7–8 | Bon — réponse correcte avec des imperfections mineures |
| 5–6 | Moyen — réponse partielle ou inefficace |
| 3–4 | Faible — erreurs significatives ou lacunes importantes |
| 0–2 | Échec — réponse incorrecte ou absente |

---

## 4. Métriques reportées par run

Pour chaque run, le benchmark enregistre :

```json
{
  "question_id": "q1_simple_stat",
  "agent": "dnd-5e-researcher-vector",
  "quality": {
    "accuracy": 5,
    "completeness": 3,
    "faithfulness": 2,
    "total": 10
  },
  "efficiency": {
    "latency_s": 4.2,
    "latency_score": 5,
    "tokens_input": 1200,
    "tokens_output": 350,
    "tokens_total": 1550,
    "token_score": 4,
    "total": 9
  },
  "final_score": 9.8,
  "search_calls": 1,
  "agent_response": "..."
}
```

## 5. Agrégation

Par agent, on calcule :
- **Mean Quality** : moyenne du quality score sur toutes les questions
- **Mean Efficiency** : moyenne de l'efficiency score
- **Mean Final** : moyenne du score final
- **Quality par difficulté** : moyenne quality groupée par `simple` / `medium` / `complex`

Le classement principal est sur **Mean Final**, avec **Mean Quality** comme critère de départage.
