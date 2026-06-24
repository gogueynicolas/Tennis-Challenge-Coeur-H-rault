# Challenge Cœur d'Hérault — comptage des points

Application Streamlit pour calculer le classement du challenge (7 tournois + master).

## Installation

```bash
pip install -r requirements.txt
```

## Lancement

```bash
streamlit run app.py
```
L'appli s'ouvre dans le navigateur.

## Utilisation

1. **Importer un tournoi** : choisir le tournoi dans la liste, déposer les
   2 fichiers Excel (liste des joueurs + liste des matchs), vérifier l'aperçu,
   puis cliquer sur « Ajouter ». Répéter pour chacun des 7 tournois.
2. Les **classements** se mettent à jour automatiquement :
   - onglets Hommes / Femmes, découpés par série (2e / 3e / 4e) ;
   - classement des Clubs (bonus compris) ;
   - sélection du Master (top N par genre et série) ;
   - onglet Détail : tableau complet + export Excel.
3. **Sauvegarde** (barre latérale) : « Télécharger l'état (.json) » pour
   conserver les tournois déjà saisis et les recharger plus tard.

## Règles appliquées

- 2 points par rencontre gagnée.
- Bonus = (nombre de tournois auxquels le joueur a participé − 1) × 3.
- Changement de série : la **moitié** des points de match est conservée,
  les points bonus sont conservés en totalité.
- Classement club = somme des points (bonus compris) de tous ses joueurs.
- Tous les joueurs n'appartenant pas à un des 7 clubs sont supprimés.

## Deux choix à valider (barre latérale → Configuration)

1. **Séries** : barème du challenge — la 4e série s'arrête à **30/1**, le
   **30** est en 3e série (conforme à l'exemple du règlement 30/1 → 30 =
   4e → 3e). Modifiable dans la configuration si besoin.
2. **Participation** (pour le bonus) : « Inscrit » (présent dans la liste
   joueurs) ou « A disputé ≥ 1 match ». Par défaut : Inscrit.

## Fichiers attendus

- *Liste des joueurs* : colonnes `Nom`, `Prénom`, `Licence`, `Club`,
  `Epreuve`, `Classement inscription`.
- *Liste des matchs* : colonnes `Résultat` (V/D), `Licence J1`, `Licence J3`.
  Le vainqueur est J1 si `V`, J3 si `D`.

## Architecture

- `challenge_core.py` : moteur de calcul (logique pure, testable).
- `app.py` : interface Streamlit.
