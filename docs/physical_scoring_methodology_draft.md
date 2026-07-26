# Methodology Draft — Physical Score Attribution (Binary)
## Version Binary V1 — Final Definition

### Variable Definition

physical_score = 1
Le candidat présente des indications suffisamment claires qu'il avait, avant le tournage,
une condition physique supérieure à celle d'une personne moyenne (sport intensif/régulier,
niveau de compétition, profession physique directe).

physical_score = 0
Le candidat correspond à un profil physique ordinaire ou non particulièrement sportif.
Aucun indicateur ne permet de le considérer comme ayant une condition physique
supérieure à la moyenne. Cela ne signifie pas mauvaise condition physique.

physical_score = null
Informations ambiguës ou insuffisantes (sport mentionné sans fréquence, danse sans
intensité documentée, sources contradictoires).

### Decision Logic
1. Profession physique directe → 1
2. Sport intensif/régulier/compétitif documenté → 1
3. Indice sportif vague (judoka sans grade, badminton sans fréquence, danse sans intensité) → null
4. Profil ordinaire sans indicateur qualifiant → 0

### Interdictions
- Aucune inférence à partir du sexe, de l'âge, de l'apparence
- Aucune utilisation des performances dans Koh-Lanta
- Aucune utilisation du rang final ou du type de sortie
