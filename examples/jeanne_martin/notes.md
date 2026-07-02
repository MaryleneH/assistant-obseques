# Cas de test fictif — Jeanne Martin

> Données **entièrement fictives**, utilisées pour tester l'Extracteur et pour
> l'évaluation. Toute ressemblance avec des personnes réelles serait fortuite.
> Présenté en deux pages pour exercer la consolidation multi-pages.


> Entirely fictional data, used to test the Extractor and for evaluation purposes.
> Any resemblance to real persons would be purely coincidental.
> Presented across two pages to exercise multi-page consolidation.
> In French for the sacristan.


## Page 1

Obsèques de Madame Jeanne Martin, 84 ans, mardi 7 juillet à 10h30 à l'église
Saint-Martin.

La famille décrit Jeanne comme une personne discrète, croyante, très attachée à
ses petits-enfants. Elle aimait beaucoup chanter et rendre service.

Ne pas insister sur la maladie dans le mot d'accueil.

## Page 2

Son fils Pierre lira la première lecture. Sa petite-fille Claire aimerait lire
une intention de prière.

Chant d'entrée souhaité : « Trouver dans ma vie ta présence ».
Chant du dernier adieu : « Je vous salue Marie ».

Le prêtre sera le Père Bernard.
Envoyer le déroulé à pere.bernard@example.com et à equipe.obseques@example.com.

---

### Note pour les tests
Pour exercer le scénario « alerte de contradiction », dériver une variante de
cette fiche en changeant l'heure sur la page 2 (par ex. « la cérémonie est à
11h »). L'Extracteur doit alors produire une entrée dans
`extraction.contradictions` plutôt que d'écraser silencieusement l'heure.
