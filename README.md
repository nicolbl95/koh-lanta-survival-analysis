# Analyse de survie dans Koh-Lanta

<p align="center">
  <img src="Images/koh_lanta_cover.webp" alt="Épreuve des poteaux de Koh-Lanta" width="900">
</p>

<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/python/python-original.svg" alt="Python" width="48" height="48"/>
  &nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/pandas/pandas-original.svg" alt="pandas" width="48" height="48"/>
  &nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/numpy/numpy-original.svg" alt="NumPy" width="48" height="48"/>
  &nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/matplotlib/matplotlib-original.svg" alt="Matplotlib" width="48" height="48"/>
  &nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/jupyter/jupyter-original.svg" alt="Jupyter" width="48" height="48"/>
  &nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/pytest/pytest-original.svg" alt="pytest" width="48" height="48"/>
  &nbsp;
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/html5/html5-original.svg" alt="HTML5" width="48" height="48"/>
</p>

<p align="center">
  <strong>Python · pandas · NumPy · Matplotlib · statsmodels · pytest · LLM · HTML5</strong>
</p>

Projet de portfolio en **LLM Engineering, Data Engineering et Data Science** consacré à l’analyse de la progression de **340 candidats issus de 17 saisons de Koh-Lanta**.

Le projet combine :

- scraping de données web ;
- nettoyage et normalisation ;
- enrichissement assisté par LLM ;
- validation humaine ;
- contrôles qualité automatisés ;
- analyse statistique ;
- génération de rapports HTML en français et en anglais.

## Rapports

- [Lire le rapport complet en français](https://nicolbl95.github.io/koh-lanta-survival-analysis/report/koh_lanta_rapport_fr.html)
- [Read the full report in English](https://nicolbl95.github.io/koh-lanta-survival-analysis/report/koh_lanta_report_en.html)

---

## Présentation de Koh-Lanta

Koh-Lanta est une émission française d’aventure et de compétition diffusée depuis 2001. Des candidats vivent pendant plusieurs semaines dans des conditions difficiles, participent à des épreuves et cherchent à éviter différents mécanismes d’élimination.

Le jeu combine :

- capacités physiques ;
- endurance ;
- adaptation ;
- stratégie ;
- alliances ;
- relations sociales.

Les candidats peuvent être éliminés par vote, lors d’une épreuve, pour raison médicale ou pendant les différentes étapes finales.

---

## Pourquoi ce projet ?

Koh-Lanta constitue un cas d’étude intéressant pour analyser un parcours dans lequel plusieurs événements peuvent interrompre la progression d’un individu.

La question principale du projet est la suivante :

> Dans quelle mesure l’âge, le sexe et le profil physique sont-ils associés au parcours d’un candidat dans Koh-Lanta, depuis les premières éliminations jusqu’aux étapes finales et à la victoire ?

La structure du problème ressemble à plusieurs cas d’usage professionnels :

- churn client ;
- départ de salariés ;
- parcours médical ;
- risque de crédit ;
- funnel de conversion ;
- analyse du cycle de vie utilisateur.

Un candidat peut rester dans le jeu, être éliminé par vote, quitter pour raison médicale, perdre une épreuve ou atteindre la victoire. Cette structure est proche d’un problème de survie avec plusieurs événements concurrents.

---

## Données analysées

L’analyse finale comprend :

- **340 candidats**
- **17 saisons**
- **20 vainqueurs ou co-vainqueurs**
- **68 profils physiques validés manuellement**

Trois variables principales sont étudiées :

- l’âge ;
- le sexe ;
- le profil physique.

Les candidats sont répartis dans quatre tranches d’âge :

- 18–25 ans ;
- 26–33 ans ;
- 34–41 ans ;
- 42 ans et plus.

La variable `physical_score` est binaire :

- `0` : profil non physique ;
- `1` : profil physique.

---

## Pourquoi le profil physique a-t-il été validé manuellement ?

Une première tentative d’automatisation a essayé d’estimer le profil physique à partir :

- des professions ;
- des biographies ;
- des sports pratiqués ;
- des descriptions disponibles sur les candidats.

Cependant, ces informations ne correspondaient pas toujours à la réalité observable.

Par exemple :

- une profession physique ne signifie pas nécessairement que le candidat possède un profil sportif ;
- un candidat très sportif peut avoir une profession sans rapport avec le sport ;
- certaines biographies sont incomplètes ;
- les informations disponibles varient fortement selon les saisons.

La classification a donc été revue manuellement, candidat par candidat.

Cette démarche constitue une approche **human-in-the-loop** : l’automatisation accélère l’extraction, mais une validation humaine reste nécessaire pour corriger les résultats peu fiables.

---

## Utilisation des LLM

Les LLM ont été utilisés pour assister plusieurs étapes du projet :

- extraction d’informations structurées à partir de textes ;
- classification de descriptions de sortie ;
- enrichissement des profils candidats ;
- détection d’incohérences ;
- génération de justifications ;
- soutien à la recherche documentaire.

Les résultats importants n’ont pas été acceptés automatiquement.

Le processus suivi était :

1. collecte et normalisation des données ;
2. extraction ou classification assistée par LLM ;
3. revue des résultats ambigus ;
4. corrections manuelles ;
5. contrôles automatisés ;
6. génération d’un dataset final versionné.

L’objectif n’était donc pas d’utiliser un LLM comme source de vérité, mais comme composant d’un pipeline contrôlé.

---

## Pipeline du projet

```text
Sources web
    ↓
Scraping
    ↓
Données brutes
    ↓
Nettoyage et normalisation
    ↓
Enrichissement assisté par LLM
    ↓
Validation humaine
    ↓
Audits et tests automatisés
    ↓
Modélisation statistique
    ↓
Rapports HTML en français et en anglais
```

---


## Technologies utilisées

- Python ;
- pandas ;
- NumPy ;
- Matplotlib ;
- statsmodels ;
- scraping web ;
- analyse de survie ;
- extraction assistée par LLM ;
- validation human-in-the-loop ;
- tests automatisés ;
- reporting HTML.

---

## Compétences démontrées

### LLM Engineering

- extraction structurée à partir de textes ;
- classification assistée par LLM ;
- validation humaine ;
- correction de sorties peu fiables ;
- traçabilité des décisions ;
- réflexion sur les limites de l’automatisation.

### Data Engineering

- collecte multi-source ;
- normalisation ;
- rapprochement d’entités ;
- versionnement des datasets ;
- contrôles qualité ;
- construction d’un pipeline reproductible.

### Data Science

- analyse de survie ;
- probabilités conditionnelles ;
- modèles ajustés ;
- contrôle des facteurs confondants ;
- interprétation statistique ;
- communication de l’incertitude.

---

## Pertinence professionnelle

Même si les données proviennent d’une émission de télévision, la structure analytique ressemble à de nombreux problèmes professionnels.

Un candidat peut :

- rester actif ;
- être éliminé par vote ;
- quitter pour raison médicale ;
- perdre une épreuve ;
- atteindre une étape finale ;
- gagner.

Cette logique est comparable à des systèmes dans lesquels un client, un salarié, un patient ou un emprunteur peut connaître plusieurs événements concurrents au cours du temps.

Le projet démontre la capacité à transformer des données hétérogènes et incomplètes en un produit analytique validé, interprétable et présenté de manière professionnelle.

