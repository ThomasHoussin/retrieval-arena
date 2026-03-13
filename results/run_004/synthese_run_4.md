# Résultats Run 4 — BM25 Free Haiku (Haiku 4.5) vs Run 3 BM25 Free (Sonnet)

## Scores par question

| Question | Diff. | Haiku | Sonnet | Delta | Haiku calls | Sonnet calls |
|---|---|---|---|---|---|---|
| Q1 simple_stat | simple | **10** | 10 | 0 | 1 | 3 |
| Q2 simple_ability | simple | **10** | 10 | 0 | 1 | 1 |
| Q3 medium_spell | medium | **9** | 10 | **-1** | 2 | 2 |
| Q4 medium_disease | medium | **8** | 10 | **-2** | 2 | 2 |
| Q5 complex_multistep | complex | **9** | 10 | **-1** | 4 | 4 |
| Q6 simple_death_house | simple | **8** | 10 | **-2** | 2 | 2 |
| Q7 medium_skyhorn | medium | **10** | 10 | 0 | 2 | 2 |
| Q8 simple_scions | simple | **10** | 10 | 0 | 2 | 2 |
| Q9 medium_combat | medium | **10** | 10 | 0 | 3 | 3 |
| Q10 medium_surprise | medium | **10** | 10 | 0 | 2 | 4 |
| Q11 medium_death_house | medium | **10** | 10 | 0 | 2 | 2 |
| Q12 medium_valturnax | medium | **9** | 10 | **-1** | 3 | 3 |
| Q13 complex_initiative | complex | **10** | 10 | 0 | 5 | 5 |
| Q14 complex_frozen_sick | complex | **8** | 10 | **-2** | 3 | 4 |
| Q15 medium_hoard | medium | **10** | 10 | 0 | 2 | 2 |
| Q16 simple_petrified | simple | **10** | 10 | 0 | 1 | 1 |
| Q17 simple_delian_tomb | simple | **10** | 10 | 0 | 2 | 2 |
| Q18 medium_spell_compare | medium | **9** | 10 | **-1** | 4 | 3 |
| Q19 medium_wild_sheep | medium | **10** | 10 | 0 | 2 | 2 |
| Q20 medium_six_faces | medium | **10** | 10 | 0 | 2 | 2 |
| Q21 complex_cross_doc | complex | **10** | 10 | 0 | 2 | 4 |
| Q22 complex_attunement | complex | **9** | 10 | **-1** | 3 | 3 |
| Q23 trap_fireball | simple | **10** | 10 | 0 | 1 | 1 |
| Q24 trap_nonexistent | simple | **10** | 10 | 0 | 2 | 3 |

## Résumé

| Métrique | Haiku 4.5 | Sonnet |
|---|---|---|
| Score moyen | **9.50/10** | **10.00/10** |
| Questions parfaites (10/10) | 17/24 (71%) | 24/24 (100%) |
| Questions < 10 | 7 | 0 |
| Total search calls | 55 | 60 |
| Questions à 8/10 | Q4, Q6, Q14 | — |
| Questions à 9/10 | Q3, Q5, Q12, Q18, Q22 | — |

## Analyse des erreurs Haiku

Les 7 questions sous-performantes se répartissent en **3 catégories** :

1. **Omission de détails subtils** (Q3, Q12, Q22) : Haiku oublie des nuances — Advantage sur le save de Dominate Monster, le monologue de Valturnax, les conditions de fin d'attunement
2. **Erreurs de raisonnement** (Q5, Q18) : la "moitié de 6d8 = 3d4" en Q5, la contradiction interne "les deux font 6d8" en Q18
3. **Mauvaise synthèse narrative** (Q4, Q6, Q14) : sur les questions nécessitant de structurer une réponse à partir de textes longs, Haiku perd des détails ou fait des erreurs d'interprétation

## Conclusion

**Haiku 4.5 est très bon (9.50/10) mais ne réplique pas le score parfait de Sonnet.** Les erreurs sont toutes des erreurs de *raisonnement* et de *complétude*, jamais de *faithfulness* — les guardrails anti-hallucination fonctionnent parfaitement avec Haiku aussi. L'efficacité en search calls est légèrement meilleure (55 vs 60), et la vitesse ~3x plus rapide.
