"""
challenge_core.py
=================
Moteur de calcul du Challenge Cœur d'Hérault.
Logique 100% pure (pas de Streamlit) -> testable indépendamment.

Règlement appliqué :
  - 2 points par rencontre gagnée
  - points bonus = (nb de tournois auxquels le joueur a participé - 1) x 3
  - en cas de changement de série, le joueur conserve la MOITIÉ des points de
    match acquis (les points bonus sont conservés en totalité)
  - classement club = somme des points (bonus compris) de tous ses joueurs

Le classement final (pour le master) est établi par genre (Hommes / Femmes)
puis par série (4e, 3e, 2e ...). La série finale d'un joueur est celle de son
DERNIER tournoi disputé.
"""

from __future__ import annotations
import math
import unicodedata


# ---------------------------------------------------------------------------
# Configuration par défaut (modifiable depuis l'appli)
# ---------------------------------------------------------------------------

# Les 7 clubs du challenge, tels qu'ils apparaissent dans la colonne "Club".
CHALLENGE_CLUBS_DEFAUT = [
    "AS SAINT PARGOIRE",
    "TENNIS CLUB PAULHAN",
    "TC LODEVE",
    "TC BOHEMIEN - LE POUGET",
    "TC ANIANE",
    "CEYRAS TENNIS",
    "TC CANETOIS",
]

# Ordre officiel des tournois (sert pour rejouer les changements de série).
TOURNOIS_DEFAUT = [
    {"id": "st_pargoire", "nom": "St Pargoire",                 "ordre": 1},
    {"id": "paulhan",     "nom": "Open Paulhan",                "ordre": 2},
    {"id": "lodeve",      "nom": "Tournoi Lodévois et Larzac",  "ordre": 3},
    {"id": "le_pouget",   "nom": "TC Bohémien - Le Pouget",     "ordre": 4},
    {"id": "aniane",      "nom": "Aniane",                      "ordre": 5},
    {"id": "ceyras",      "nom": "Ceyras Tennis",               "ordre": 6},
    {"id": "canet",       "nom": "Canet",                       "ordre": 7},
]

# Mapping classement -> série, propre au Challenge Cœur d'Hérault :
# la 4e série s'arrête à 30/1 ; le 30 est en 3e série.
SERIE_MAPPING_DEFAUT = {
    "4e": ["NC", "40", "30/5", "30/4", "30/3", "30/2", "30/1"],
    "3e": ["30", "15/5", "15/4", "15/3", "15/2", "15/1"],
    "2e": ["15", "5/6", "4/6", "3/6", "2/6", "1/6", "0",
           "-2/6", "-4/6", "-15", "-30", "-45"],
}

SERIE_ORDRE = ["2e", "3e", "4e"]  # ordre d'affichage (forte -> faible)


# ---------------------------------------------------------------------------
# Helpers de normalisation
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def norm_text(x) -> str:
    """Normalise un texte pour comparaison robuste (clubs, etc.)."""
    if x is None:
        return ""
    s = str(x).strip()
    if s.lower() in ("nan", "none"):
        return ""
    return " ".join(s.split())


def norm_club(x) -> str:
    """Clé de comparaison de club : majuscules, sans accents, espaces compactés."""
    return _strip_accents(norm_text(x)).upper()


def norm_licence(x) -> str:
    """Licence -> chaîne d'entier ('1123856'), ou '' si vide."""
    s = norm_text(x)
    if not s:
        return ""
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s


def norm_clt(x) -> str:
    """Classement nettoyé ('30/4 ' -> '30/4')."""
    s = norm_text(x).upper().replace(" ", "")
    return s


def classement_to_serie(clt, serie_mapping=None) -> str | None:
    """Renvoie '4e' / '3e' / '2e' / '1re' / None à partir d'un classement."""
    serie_mapping = serie_mapping or SERIE_MAPPING_DEFAUT
    c = norm_clt(clt)
    if not c:
        return None
    for serie, valeurs in serie_mapping.items():
        if c in [norm_clt(v) for v in valeurs]:
            return serie
    # Classement numérique pur (ex '15', '4') déjà couvert ; sinon -> 1re série
    # (rang national). On le signale comme '1re' pour ne pas le perdre.
    try:
        float(c.replace("/", "."))
        return "1re"
    except ValueError:
        return None


def genre_from_epreuve(ep) -> str | None:
    """Hommes / Femmes à partir de l'épreuve."""
    e = norm_text(ep).lower()
    if "dame" in e or "femme" in e:
        return "Femmes"
    if "messieurs" in e or "homme" in e:
        return "Hommes"
    return None


# ---------------------------------------------------------------------------
# Parsing d'un tournoi (2 DataFrames -> dict par licence)
# ---------------------------------------------------------------------------

def parse_tournoi(df_joueurs, df_matchs, challenge_clubs=None,
                  serie_mapping=None):
    """
    Transforme les fichiers d'un tournoi en un dictionnaire :
        { licence : {nom, prenom, club, classement, serie, genre,
                     victoires, a_joue} }
    Seuls les joueurs appartenant à un club du challenge sont conservés.

    Renvoie aussi un rapport (clubs supprimés, lignes ignorées...).
    """
    challenge_clubs = challenge_clubs or CHALLENGE_CLUBS_DEFAUT
    serie_mapping = serie_mapping or SERIE_MAPPING_DEFAUT
    clubs_ok = {norm_club(c) for c in challenge_clubs}

    # --- 1. Joueurs du challenge ------------------------------------------
    joueurs = {}            # licence -> infos
    clubs_supprimes = {}    # club -> nb joueurs supprimés
    for _, r in df_joueurs.iterrows():
        lic = norm_licence(r.get("Licence"))
        club_raw = norm_text(r.get("Club"))
        if norm_club(club_raw) not in clubs_ok:
            clubs_supprimes[club_raw] = clubs_supprimes.get(club_raw, 0) + 1
            continue
        if not lic:
            continue
        clt = norm_clt(r.get("Classement inscription"))
        joueurs[lic] = {
            "nom": norm_text(r.get("Nom")),
            "prenom": norm_text(r.get("Prénom")),
            "club": club_raw,
            "classement": clt,
            "serie": classement_to_serie(clt, serie_mapping),
            "genre": genre_from_epreuve(r.get("Epreuve")),
            "victoires": 0,
            "a_joue": False,
        }

    # --- 2. Comptage des victoires depuis les matchs ----------------------
    matchs_ignores = 0
    for _, r in df_matchs.iterrows():
        res = norm_text(r.get("Résultat")).upper()
        lic_j1 = norm_licence(r.get("Licence J1"))
        lic_j3 = norm_licence(r.get("Licence J3"))
        # Joueurs présents -> marquer "a joué"
        for lic in (lic_j1, lic_j3):
            if lic in joueurs:
                joueurs[lic]["a_joue"] = True
        # Vainqueur : V -> J1, D -> J3
        if res == "V":
            gagnant = lic_j1
        elif res == "D":
            gagnant = lic_j3
        else:
            matchs_ignores += 1
            continue
        if gagnant in joueurs:
            joueurs[gagnant]["victoires"] += 1

    rapport = {
        "nb_joueurs_challenge": len(joueurs),
        "clubs_supprimes": clubs_supprimes,
        "matchs_ignores": matchs_ignores,
        "nb_matchs": len(df_matchs),
    }
    return joueurs, rapport


# ---------------------------------------------------------------------------
# Calcul cumulé sur l'ensemble des tournois
# ---------------------------------------------------------------------------

def _arrondi_moitie(x, mode="exact"):
    """Comment arrondir la moitié des points lors d'un changement de série."""
    if mode == "exact":
        return x / 2.0
    if mode == "inferieur":
        return math.floor(x / 2.0)
    if mode == "superieur":
        return math.ceil(x / 2.0)
    return round(x / 2.0)  # "proche"


def compute_standings(tournois_data, ordre_ids, participation="inscrit",
                      mode_arrondi="exact"):
    """
    tournois_data : { tournoi_id : { licence : infos_parse } }
    ordre_ids     : liste ordonnée des tournoi_id (ordre du calendrier)
    participation : "inscrit" (présent dans la liste joueurs filtrée)
                    ou "joue"  (a disputé >=1 match)
    mode_arrondi  : exact | proche | inferieur | superieur

    Renvoie (joueurs_resultats, clubs_resultats) sous forme de listes de dicts.
    """
    ordre = [t for t in ordre_ids if t in tournois_data]

    # Rassembler toutes les licences vues
    licences = set()
    for tid in ordre:
        licences.update(tournois_data[tid].keys())

    resultats = []
    for lic in licences:
        serie_courante = None
        genre = None
        points_match = 0.0          # points de match dans la série courante
        nb_participations = 0
        derniere_info = None
        premiere_info = None        # classement au 1er tournoi
        detail = []                 # trace par tournoi

        for tid in ordre:
            data = tournois_data[tid]
            if lic not in data:
                continue
            info = data[lic]
            if premiere_info is None:
                premiere_info = info
            derniere_info = info
            genre = info["genre"] or genre

            # Cette présence compte-t-elle comme participation ?
            compte = (participation == "inscrit") or \
                     (participation == "joue" and info["a_joue"])

            serie_now = info["serie"]
            change = (serie_courante is not None and serie_now is not None
                      and serie_now != serie_courante)
            if change:
                avant = points_match
                points_match = _arrondi_moitie(points_match, mode_arrondi)
                detail.append(
                    f"{tid}: changement {serie_courante}->{serie_now}, "
                    f"points {avant:g}->{points_match:g}")
            if serie_now is not None:
                serie_courante = serie_now

            gagnes = info["victoires"]
            pts_t = gagnes * 2
            points_match += pts_t
            if compte:
                nb_participations += 1
            detail.append(
                f"{tid}: {gagnes} victoire(s) (+{pts_t}), "
                f"série={serie_now}, participe={compte}")

        if derniere_info is None:
            continue
        bonus = max(0, (nb_participations - 1)) * 3
        total = points_match + bonus
        resultats.append({
            "licence": lic,
            "nom": derniere_info["nom"],
            "prenom": derniere_info["prenom"],
            "club": derniere_info["club"],
            "genre": genre,
            "serie": serie_courante,
            "nb_tournois": nb_participations,
            "points_match": round(points_match, 2),
            "bonus": bonus,
            "total": round(total, 2),
            "detail": " | ".join(detail),
            "classement_inscription": premiere_info["classement"] if premiere_info else "",
            "classement_actuel": derniere_info["classement"] if derniere_info else "",
        })

    # Tri : genre, série, total décroissant
    serie_rank = {s: i for i, s in enumerate(["1re"] + SERIE_ORDRE)}
    resultats.sort(key=lambda d: (
        d["genre"] or "zz",
        serie_rank.get(d["serie"], 99),
        -d["total"],
        d["nom"],
    ))

    # Classement clubs (bonus compris)
    clubs = {}
    for d in resultats:
        c = d["club"]
        if c not in clubs:
            clubs[c] = {"club": c, "total": 0.0, "nb_joueurs": 0,
                        "points_match": 0.0, "bonus": 0}
        clubs[c]["total"] += d["total"]
        clubs[c]["points_match"] += d["points_match"]
        clubs[c]["bonus"] += d["bonus"]
        clubs[c]["nb_joueurs"] += 1
    clubs_list = sorted(clubs.values(), key=lambda d: -d["total"])
    for i, c in enumerate(clubs_list, 1):
        c["rang"] = i
        c["total"] = round(c["total"], 2)
        c["points_match"] = round(c["points_match"], 2)

    return resultats, clubs_list


def selection_master(resultats, n_par_serie=8):
    """Top n par (genre, série) pour constituer les tableaux du master."""
    groupes = {}
    for d in resultats:
        key = (d["genre"], d["serie"])
        groupes.setdefault(key, []).append(d)
    master = {}
    for key, joueurs in groupes.items():
        joueurs = sorted(joueurs, key=lambda d: -d["total"])
        master[key] = joueurs[:n_par_serie]
    return master
