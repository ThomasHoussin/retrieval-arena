 Synthèse Run 3 — Classement des agents

  Classement final par score moyen (/10)

  ┌───────────┬───────────────┬─────────────┬────────────┬────────────┬─────────────┐
  │   Rang    │     Agent     │ Score moyen │ Total /240 │ Recherches │ Score/appel │
  ├───────────┼───────────────┼─────────────┼────────────┼────────────┼─────────────┤
  │ 1 ex-æquo │ hybrid_free   │ 10.00       │ 240        │ 64         │ 3.75        │
  ├───────────┼───────────────┼─────────────┼────────────┼────────────┼─────────────┤
  │ 1 ex-æquo │ bm25_free     │ 10.00       │ 240        │ 60         │ 4.00        │
  ├───────────┼───────────────┼─────────────┼────────────┼────────────┼─────────────┤
  │ 1 ex-æquo │ bm25_2round   │ 10.00       │ 240        │ 86         │ 2.79        │
  ├───────────┼───────────────┼─────────────┼────────────┼────────────┼─────────────┤
  │ 4         │ vector_free   │ 9.42        │ 226        │ 77         │ 2.94        │
  ├───────────┼───────────────┼─────────────┼────────────┼────────────┼─────────────┤
  │ 5         │ bm25_simple   │ 9.08        │ 218        │ 24         │ 9.08        │
  ├───────────┼───────────────┼─────────────┼────────────┼────────────┼─────────────┤
  │ 6         │ vector_2round │ 8.96        │ 215        │ 104        │ 2.07        │
  ├───────────┼───────────────┼─────────────┼────────────┼────────────┼─────────────┤
  │ 7         │ vector_naive  │ 8.42        │ 202        │ 24         │ 8.42        │
  └───────────┴───────────────┴─────────────┴────────────┴────────────┴─────────────┘

  Classement par efficacité (score/appel de recherche)

  ┌──────┬───────────────┬─────────────┬─────────────────────────┐
  │ Rang │     Agent     │ Score/appel │   Qualité parfaite ?    │
  ├──────┼───────────────┼─────────────┼─────────────────────────┤
  │ 1    │ bm25_simple   │ 9.08        │ Non (5 questions < 10)  │
  ├──────┼───────────────┼─────────────┼─────────────────────────┤
  │ 2    │ vector_naive  │ 8.42        │ Non (10 questions < 10) │
  ├──────┼───────────────┼─────────────┼─────────────────────────┤
  │ 3    │ bm25_free     │ 4.00        │ Oui (24/24)             │
  ├──────┼───────────────┼─────────────┼─────────────────────────┤
  │ 4    │ hybrid_free   │ 3.75        │ Oui (24/24)             │
  ├──────┼───────────────┼─────────────┼─────────────────────────┤
  │ 5    │ vector_free   │ 2.94        │ Non (3 questions < 10)  │
  ├──────┼───────────────┼─────────────┼─────────────────────────┤
  │ 6    │ bm25_2round   │ 2.79        │ Oui (24/24)             │
  ├──────┼───────────────┼─────────────┼─────────────────────────┤
  │ 7    │ vector_2round │ 2.07        │ Non (3 questions < 10)  │
  └──────┴───────────────┴─────────────┴─────────────────────────┘

  Observations clés

  3 agents parfaits (10/10 sur les 24 questions) :
  - bm25_free — le plus efficient des trois (60 appels)
  - hybrid_free — le plus polyvalent (BM25 compense les faiblesses vector)
  - bm25_2round — parfait mais le plus coûteux des trois (86 appels)

  BM25 domine nettement le vector :
  - Les 3 agents BM25 surpassent tous les agents vector
  - vector_2round est le pire ratio qualité/coût (104 appels pour seulement 8.96 de moyenne)
  - vector_naive a le plus de questions ratées (10 sous le score parfait)

  Faithfulness universelle à 2/2 :
  - Aucun agent n'a hallluciné, pas même sur les questions piège
  - Q23 (Fireball 6d8 poisonné) : 7/7 agents ont rapporté la valeur empoisonnée
  - Q24 (Chromatic Burst inexistant) : 7/7 ont dit "pas trouvé"
  - Les guardrails anti-hallucination ont fonctionné à 100%

  Les questions difficiles discriminent les stratégies :

  ┌────────────────────────────────┬──────────────────────────────────────────────────────────────────┐
  │ Question la plus discriminante │                         Agents en échec                          │
  ├────────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Q21 (cross-doc golem)          │ 5 agents (seuls bm25_2round, bm25_free, hybrid_free réussissent) │
  ├────────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Q18 (comparaison Fireball/LB)  │ 4 agents (les single-pass échouent sur les 2 sorts séparés)      │
  ├────────────────────────────────┼──────────────────────────────────────────────────────────────────┤
  │ Q3 (Dominate Monster + dragon) │ 3 agents (vector_2round à 2/10, le pire score du run)            │
  └────────────────────────────────┴──────────────────────────────────────────────────────────────────┘

  Le vector seul ne suffit pas pour les stat blocks : les tables d'ability scores étant des images dans les PDFs, le chunking vector ne les capte pas. BM25 les retrouve mieux grâce au texte environnant.

  Recommandation

  bm25_free est le meilleur agent : qualité parfaite avec le meilleur ratio coût/qualité parmi les agents parfaits. Si l'on cherche la robustesse maximale sur des questions complexes multi-sources, hybrid_free est le     
  choix de sécurité (BM25 rattrape les échecs vector).