"""
challenge_stats.py
==================
Statistiques avancées du Challenge Cœur d'Hérault.
Logique pure (testable) : parsing des scores, indices de domination,
exploits (tombeurs), progressions, assiduité, profondeur de club,
fiche joueur, course au master.
"""

from __future__ import annotations
import re
from challenge_core import norm_text, norm_licence, norm_clt


# ---------------------------------------------------------------------------
# Ordre de force des classements (du plus faible au plus fort)
# ---------------------------------------------------------------------------
CLASSEMENT_ORDRE = [
    "NC", "40", "30/5", "30/4", "30/3", "30/2", "30/1", "30",
    "15/5", "15/4", "15/3", "15/2", "15/1", "15",
    "5/6", "4/6", "3/6", "2/6", "1/6", "0",
    "-2/6", "-4/6", "-15", "-30", "-45",
]
_RANK = {c: i for i, c in enumerate(CLASSEMENT_ORDRE)}


def classement_value(clt) -> int | None:
    """Valeur ordinale d'un classement : plus c'est grand, plus c'est fort."""
    c = norm_clt(clt)
    if not c:
        return None
    if c in _RANK:
        return _RANK[c]
    # Classement numérique national (1, 2, 3...) = plus fort que tout
    try:
        rang = int(float(c.replace("/", ".")))
        return len(CLASSEMENT_ORDRE) + (1000 - rang)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Parsing d'un score
# ---------------------------------------------------------------------------
_SET_RE = re.compile(r"^(\d+)/(\d+)(?:\((\d+)\))?$")


def parse_score(score) -> dict:
    """
    Analyse un score type '6/0 6/3', '6/7(3) 7/5 A', 'WO'.
    Le score est écrit du point de vue du VAINQUEUR (ses jeux en premier).
    Retourne jeux/sets gagnant & perdant, bagel, tie-break, abandon, wo.
    """
    s = norm_text(score).upper()
    res = {"jeux_g": 0, "jeux_p": 0, "sets_g": 0, "sets_p": 0,
           "bagel": False, "tie_break": False, "abandon": False,
           "wo": False, "valide": False}
    if not s:
        return res
    if "WO" in s or "W.O" in s:
        res["wo"] = True
        return res

    for token in s.split():
        if token in ("A", "AB", "ABANDON"):
            res["abandon"] = True
            continue
        m = _SET_RE.match(token)
        if not m:
            continue
        g, p = int(m.group(1)), int(m.group(2))
        res["jeux_g"] += g
        res["jeux_p"] += p
        if g > p:
            res["sets_g"] += 1
        elif p > g:
            res["sets_p"] += 1
        if p == 0 and g >= 6:
            res["bagel"] = True
        if m.group(3) is not None:
            res["tie_break"] = True
        res["valide"] = True
    return res


# ---------------------------------------------------------------------------
# Construction des fiches de match enrichies
# ---------------------------------------------------------------------------
def build_records(df_matchs, joueurs_dict, tournoi_id, serie_mapping=None):
    """
    Construit la liste des matchs enrichis pour un tournoi.
    joueurs_dict : sortie de parse_tournoi (licence -> infos) déjà filtrée.
    On ne garde que les matchs dont le vainqueur est un joueur du challenge.
    """
    records = []
    for _, r in df_matchs.iterrows():
        res = norm_text(r.get("Résultat")).upper()
        lic_j1 = norm_licence(r.get("Licence J1"))
        lic_j3 = norm_licence(r.get("Licence J3"))
        if res == "V":
            lic_g, lic_p = lic_j1, lic_j3
            clt_g = norm_clt(r.get("Clt J1")); clt_p = norm_clt(r.get("Clt J3"))
            nom_g = norm_text(r.get("Nom Prénom J1")); nom_p = norm_text(r.get("Nom Prénom J3"))
        elif res == "D":
            lic_g, lic_p = lic_j3, lic_j1
            clt_g = norm_clt(r.get("Clt J3")); clt_p = norm_clt(r.get("Clt J1"))
            nom_g = norm_text(r.get("Nom Prénom J3")); nom_p = norm_text(r.get("Nom Prénom J1"))
        else:
            continue

        if lic_g not in joueurs_dict:
            continue  # vainqueur hors challenge -> on ignore

        sc = parse_score(r.get("Score"))
        info_g = joueurs_dict[lic_g]
        records.append({
            "tournoi": tournoi_id,
            "lic_g": lic_g, "lic_p": lic_p,
            "nom_g": info_g["nom"] + " " + info_g["prenom"],
            "nom_p": nom_p,
            "club_g": info_g["club"],
            "clt_g": clt_g, "clt_p": clt_p,
            "genre": info_g["genre"],
            "serie": info_g["serie"],
            "score": norm_text(r.get("Score")),
            **{f"sc_{k}": v for k, v in sc.items()},
        })
    return records


# ---------------------------------------------------------------------------
# Calcul des statistiques globales
# ---------------------------------------------------------------------------
def compute_stats(resultats, match_records):
    """
    resultats     : sortie de compute_standings (liste de dicts)
    match_records : concat de tous les build_records des tournois importés
    """
    par_lic = {d["licence"]: d for d in resultats}

    # ── Domination : jeux pour / contre par joueur ──────────────────────────
    dom = {}

    def _acc(lic, nom, club, genre, pour, contre):
        if lic not in dom:
            dom[lic] = {"licence": lic, "nom": nom, "club": club,
                        "genre": genre, "pour": 0, "contre": 0, "matchs": 0}
        dom[lic]["pour"] += pour
        dom[lic]["contre"] += contre
        dom[lic]["matchs"] += 1

    bagels = {}
    giant = []
    for m in match_records:
        if not m["sc_valide"] and not m["sc_wo"]:
            continue
        # Vainqueur
        _acc(m["lic_g"], m["nom_g"], m["club_g"], m["genre"],
             m["sc_jeux_g"], m["sc_jeux_p"])
        if m["sc_bagel"]:
            bagels[m["lic_g"]] = bagels.get(m["lic_g"], 0) + 1
        # Exploit : vainqueur moins bien classé que le perdant
        vg, vp = classement_value(m["clt_g"]), classement_value(m["clt_p"])
        if vg is not None and vp is not None and vp > vg:
            giant.append({
                "tournoi": m["tournoi"], "nom_g": m["nom_g"], "clt_g": m["clt_g"],
                "nom_p": m["nom_p"], "clt_p": m["clt_p"], "score": m["score"],
                "ecart": vp - vg, "club_g": m["club_g"], "genre": m["genre"],
            })

    domination = []
    for d in dom.values():
        tot = d["pour"] + d["contre"]
        if tot == 0 or d["matchs"] < 2:   # min 2 matchs pour être significatif
            continue
        d["ratio"] = round(100 * d["pour"] / tot, 1)
        domination.append(d)
    domination.sort(key=lambda d: -d["ratio"])

    bagels_list = sorted(
        [{"licence": l, "nom": par_lic.get(l, {}).get("nom", "") + " "
          + par_lic.get(l, {}).get("prenom", ""),
          "club": par_lic.get(l, {}).get("club", ""), "bagels": n}
         for l, n in bagels.items()],
        key=lambda d: -d["bagels"])

    giant.sort(key=lambda d: -d["ecart"])

    # ── Progressions (montées de classement) ────────────────────────────────
    progressions = []
    for d in resultats:
        vi = classement_value(d["classement_inscription"])
        va = classement_value(d["classement_actuel"])
        if vi is not None and va is not None and va != vi:
            progressions.append({
                "nom": d["nom"] + " " + d["prenom"], "club": d["club"],
                "genre": d["genre"], "de": d["classement_inscription"],
                "vers": d["classement_actuel"], "delta": va - vi,
            })
    progressions.sort(key=lambda d: -d["delta"])

    # ── Assiduité ───────────────────────────────────────────────────────────
    assidus = sorted(resultats, key=lambda d: -d["nb_tournois"])
    assidus_joueurs = [{"nom": d["nom"] + " " + d["prenom"], "club": d["club"],
                        "tournois": d["nb_tournois"]} for d in assidus]

    # ── Profondeur de club ──────────────────────────────────────────────────
    clubs = {}
    for d in resultats:
        c = clubs.setdefault(d["club"], {"club": d["club"], "total": 0,
                                         "joueurs": 0})
        c["total"] += d["total"]
        c["joueurs"] += 1
    club_depth = []
    for c in clubs.values():
        c["par_joueur"] = round(c["total"] / c["joueurs"], 2) if c["joueurs"] else 0
        club_depth.append(c)
    club_depth.sort(key=lambda c: -c["par_joueur"])

    # ── Matchs extrêmes ─────────────────────────────────────────────────────
    valides = [m for m in match_records if m["sc_valide"]
               and not m["sc_abandon"] and not m["sc_wo"]]
    match_serre = match_net = None
    if valides:
        # le plus serré : 3 sets puis plus petit écart de jeux puis tie-break
        match_serre = min(
            valides,
            key=lambda m: (-(m["sc_sets_g"] + m["sc_sets_p"]),
                           m["sc_jeux_g"] - m["sc_jeux_p"],
                           0 if m["sc_tie_break"] else 1))
        # le plus net : plus grand écart de jeux, moins de jeux concédés
        match_net = max(
            valides,
            key=lambda m: (m["sc_jeux_g"] - m["sc_jeux_p"], -m["sc_jeux_p"]))

    return {
        "domination": domination,
        "bagels": bagels_list,
        "giant_kills": giant,
        "progressions": progressions,
        "assidus_joueurs": assidus_joueurs,
        "club_depth": club_depth,
        "match_serre": match_serre,
        "match_net": match_net,
        "nb_matchs": len(match_records),
    }


# ---------------------------------------------------------------------------
# Fiche joueur
# ---------------------------------------------------------------------------
def fiche_joueur(licence, resultats, match_records, tournois_data, ordre_ids):
    """Parcours détaillé d'un joueur : points par tournoi + matchs."""
    d = next((r for r in resultats if r["licence"] == licence), None)
    if d is None:
        return None

    # Points par tournoi (victoires * 2)
    par_tournoi = []
    for tid in ordre_ids:
        data = tournois_data.get(tid, {})
        if licence in data:
            v = data[licence]["victoires"]
            par_tournoi.append({"tournoi": tid, "victoires": v, "points": v * 2,
                                "classement": data[licence]["classement"],
                                "serie": data[licence]["serie"]})

    matchs = [m for m in match_records
              if m["lic_g"] == licence or m["lic_p"] == licence]
    detail_matchs = []
    for m in matchs:
        gagne = (m["lic_g"] == licence)
        detail_matchs.append({
            "tournoi": m["tournoi"],
            "resultat": "Victoire" if gagne else "Défaite",
            "adversaire": m["nom_p"] if gagne else m["nom_g"],
            "clt_adv": m["clt_p"] if gagne else m["clt_g"],
            "score": m["score"],
        })

    return {"joueur": d, "par_tournoi": par_tournoi, "matchs": detail_matchs}


# ---------------------------------------------------------------------------
# Course au master : points cumulés par tournoi
# ---------------------------------------------------------------------------
def course_master(tournois_data, ordre_ids, serie_finale_par_lic):
    """
    Renvoie, par licence, la liste des points cumulés après chaque tournoi
    (sans la règle de série, juste cumul des victoires*2) pour le graphique.
    serie_finale_par_lic : {licence: serie} pour filtrer/grouper.
    """
    ordre = [t for t in ordre_ids if t in tournois_data]
    courbes = {}
    for lic, serie in serie_finale_par_lic.items():
        cumul = 0
        pts = []
        for tid in ordre:
            data = tournois_data[tid]
            if lic in data:
                cumul += data[lic]["victoires"] * 2
            pts.append(cumul)
        courbes[lic] = pts
    return ordre, courbes
