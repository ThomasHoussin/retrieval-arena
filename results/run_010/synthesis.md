# Run 010 — Impact de la qualité d'ingestion sur la recherche

## Question
Biographie complète du duc de Saint-Amand (personnage fil rouge de l'univers Nephilim)

## Protocole
3 phases successives avec la même question posée aux agents BM25 free et Hybrid free :
1. **Phase 1** : corpus sans le document `Les_figures.pdf`
2. **Phase 2** : `Les_figures.pdf` ajouté, mais le titre "Les confidences du Duc de Saint-Amand" (p. 96) est absent du scan (mangé par l'OCR)
3. **Phase 3** : titre ajouté manuellement dans le cache du scan, document réindexé

## Résultats par phase

### Phase 1 — Sans Les_figures.pdf

| Agent | Tool uses | Tokens | Durée | Confidences trouvées |
|-------|-----------|--------|-------|---------------------|
| BM25 free | 6 | 92 973 | 94s | N/A (doc absent) |
| Hybrid free | 8 | 82 385 | 93s | N/A (doc absent) |

Les deux agents produisent des biographies solides couvrant : identité, rencontre 1990, Hermès Trismégiste, Archives Secrètes, terrain, rumeur de mort 1999.

**Sources exclusives BM25** : Vision Ka 4 (Héritiers de Babel), L'Atalante Fugitive
**Sources exclusives Hybride** : Les Arcanes Majeurs (Tarot/Roms), Selenim N1 (De Martigny), rapports détaillés du Guide 2e éd.

### Phase 2 — Les_figures.pdf sans titre

| Agent | Tool uses | Tokens | Durée | Confidences trouvées |
|-------|-----------|--------|-------|---------------------|
| BM25 free | 10 | 106 139 | 110s | Titre repéré, contenu NON lu |
| Hybrid free | 10 | 112 136 | 138s | Titre ET contenu lus |

**Observation clé** : le BM25 free repère l'existence de la section "Les confidences du Duc de Saint-Amand" (p. 96) via une référence dans une autre page, mais ne parvient pas à retrouver le contenu du passage lui-même — le titre de la page ayant été mangé par le scan, les mots-clés ne matchent pas.

L'hybride free retrouve le contenu grâce à la **recherche vectorielle** qui matche sémantiquement (proximité d'embedding) même sans les mots-clés exacts du titre.

### Phase 3 — Les_figures.pdf avec titre corrigé

| Agent | Tool uses | Tokens | Durée | Confidences trouvées |
|-------|-----------|--------|-------|---------------------|
| BM25 free | 11 | 116 042 | 110s | Titre ET contenu lus |
| Hybrid free | 6 | 78 410 | 104s | Titre ET contenu lus |

Les deux agents trouvent désormais le contenu complet des confidences :
- Fausse mort de 1998 (attaque des hommes de Tubalcaan)
- Substitution du corps d'un clochard
- Fuite vers un sanctuaire secret
- Rôle dans l'affaire du "Pélican fou" à Lyon (février 1999)
- Motivation : ne pas gêner le Kwisatz Haderach
- Auto-révélation comme Initié Agarthien

**Source inédite BM25** : Codex des Ar-Kaïm (p. 60-62) — fraternité humaine protégée par le duc

## Conclusions

### 1. La qualité d'ingestion est fondamentale
Un titre de page manquant dans le scan suffit à rendre un passage invisible au BM25. Le vecteur compense partiellement grâce au matching sémantique, mais ce n'est pas une garantie.

### 2. BM25 et Vector sont complémentaires
- **BM25** ratisse plus large (plus de requêtes) et trouve des sources obscures (Codex des Ar-Kaïm)
- **Vector** matche sémantiquement et résiste mieux aux défauts d'OCR
- **Hybride** combine les deux mais pas toujours plus efficace en nombre de sources uniques

### 3. En mode agent, les deux moteurs trouvent globalement très bien
Dès lors que l'information est correctement ingérée dans les 16k chunks, BM25 et Vector en mode agent libre trouvent l'essentiel. Les différences portent sur des sources marginales, pas sur le cœur de la biographie.

### 4. L'hybride est plus efficient
En phase 3, l'hybride produit un résultat comparable en 6 recherches là où le BM25 en fait 11. La combinaison BM25+Vector permet de converger plus vite.
