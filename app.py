"""
app.py — Challenge Cœur d'Hérault
=================================
Lancer :  streamlit run app.py

Deux modes :
  - Vue utilisateur  : classements seuls (accès libre)
  - Vue administrateur : import tournois, configuration, images, export
    → protégée par mot de passe (défini dans challenge_config.json)
"""

import json, io, zipfile, os, datetime, hashlib
import pandas as pd
import streamlit as st
import challenge_core as cc
import challenge_stats as cs

st.set_page_config(page_title="Challenge Cœur d'Hérault",
                   page_icon="🎾", layout="wide")

# ============================================================================
# Constantes
# ============================================================================
TOURNOIS        = cc.TOURNOIS_DEFAUT
ORDRE_IDS       = [t["id"] for t in sorted(TOURNOIS, key=lambda x: x["ordre"])]
NOM_PAR_ID      = {t["id"]: t["nom"] for t in TOURNOIS}
COLS_JOUEURS    = ["Nom", "Prénom", "Licence", "Club", "Epreuve", "Classement inscription"]
COLS_MATCHS     = ["Résultat", "Licence J1", "Licence J3"]
ANNEE_EN_COURS  = datetime.date.today().year
FICHIER_CONFIG  = "challenge_config.json"


# ============================================================================
# Config : mot de passe admin
# ============================================================================
def _hash(mdp: str) -> str:
    return hashlib.sha256(mdp.encode()).hexdigest()


def charger_config() -> dict:
    if os.path.exists(FICHIER_CONFIG):
        try:
            with open(FICHIER_CONFIG, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Config par défaut : mot de passe "admin"
    cfg = {"mdp_hash": _hash("admin")}
    sauvegarder_config(cfg)
    return cfg


def sauvegarder_config(cfg: dict) -> None:
    with open(FICHIER_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def verifier_mdp(mdp: str) -> bool:
    return _hash(mdp) == charger_config().get("mdp_hash", "")


# ============================================================================
# Persistance durable  (Postgres/Supabase si configuré, sinon fichiers locaux)
# ============================================================================
import challenge_storage as cstg


def _etat_vide() -> dict:
    return {
        "annee": ANNEE_EN_COURS,
        "tournois_data": {},
        "tournois_meta": {},
        "tournois_matchs": {},
        "clubs": list(cc.CHALLENGE_CLUBS_DEFAUT),
        "serie_mapping": {k: list(v) for k, v in cc.SERIE_MAPPING_DEFAUT.items()},
        "participation": "joue",
        "arrondi": "exact",
        "n_master": 8,
    }


def charger_etat(annee: int) -> dict:
    etat = cstg.charger(annee)
    return etat if etat else _etat_vide()


def sauvegarder_etat(etat: dict) -> None:
    try:
        cstg.sauver(etat.get("annee", ANNEE_EN_COURS), etat)
    except Exception as e:
        st.warning(f"Sauvegarde impossible : {e}")


def annees_archivees() -> list:
    return cstg.annees()


def charger_historique_complet() -> dict:
    """
    Charge toutes les années et calcule resultats + clubs pour chacune.
    Retourne {annee: {"resultats": [...], "clubs": [...], "etat": {...}}}.
    """
    hist = {}
    for annee in annees_archivees():
        etat = cstg.charger(annee)
        if not etat:
            continue
        td = etat.get("tournois_data", {})
        if not td:
            continue
        try:
            res, clubs = cc.compute_standings(
                td, ORDRE_IDS,
                participation=etat.get("participation", "joue"),
                mode_arrondi=etat.get("arrondi", "exact"))
            hist[annee] = {"resultats": res, "clubs": clubs, "etat": etat}
        except Exception:
            pass
    return hist


# ============================================================================
# État de session : initialisation
# ============================================================================
ss = st.session_state
if "initialise" not in ss:
    etat = charger_etat(ANNEE_EN_COURS)
    for k, v in etat.items():
        ss[k] = v
    ss["initialise"]    = True
    ss["annee_active"]  = ANNEE_EN_COURS
    ss["mode_archive"]  = False
    ss["est_admin"]     = False   # non connecté par défaut

ss.setdefault("annee_active",  ANNEE_EN_COURS)
ss.setdefault("mode_archive",  False)
ss.setdefault("est_admin",     False)
ss.setdefault("tournois_data", {})
ss.setdefault("tournois_meta", {})
ss.setdefault("tournois_matchs", {})
ss.setdefault("clubs",         list(cc.CHALLENGE_CLUBS_DEFAUT))
ss.setdefault("serie_mapping", {k: list(v) for k, v in cc.SERIE_MAPPING_DEFAUT.items()})
ss.setdefault("participation", "joue")
ss.setdefault("arrondi",       "exact")
ss.setdefault("n_master",      8)


def _etat_courant() -> dict:
    return {
        "annee":         ss.get("annee_active", ANNEE_EN_COURS),
        "tournois_data": ss["tournois_data"],
        "tournois_meta": ss["tournois_meta"],
        "tournois_matchs": ss["tournois_matchs"],
        "clubs":         ss["clubs"],
        "serie_mapping": ss["serie_mapping"],
        "participation": ss["participation"],
        "arrondi":       ss["arrondi"],
        "n_master":      ss["n_master"],
    }


def _autosave():
    if not ss["mode_archive"]:
        sauvegarder_etat(_etat_courant())


# ============================================================================
# Barre latérale
# ============================================================================
with st.sidebar:

    # ── Logo / titre ────────────────────────────────────────────────────────
    st.markdown("## 🎾 Challenge\nCœur d'Hérault")
    st.divider()

    # ── Bloc admin / connexion ───────────────────────────────────────────────
    if ss["est_admin"]:
        st.success("🔑 Mode administrateur")
        if st.button("🔓 Se déconnecter", width='stretch'):
            ss["est_admin"] = False
            st.rerun()
    else:
        st.info("👁️ Vue publique")
        with st.expander("🔑 Connexion administrateur"):
            mdp_saisi = st.text_input("Mot de passe", type="password",
                                      key="input_mdp")
            if st.button("Connexion", width='stretch'):
                if verifier_mdp(mdp_saisi):
                    ss["est_admin"] = True
                    st.success("Connecté !")
                    st.rerun()
                else:
                    st.error("Mot de passe incorrect.")

    st.divider()

    # ── Saison (visible dans les deux modes) ────────────────────────────────
    st.subheader("📅 Saison")
    _bk = cstg.info_backend()
    if _bk["backend"] == "postgres":
        st.caption("🟢 Stockage durable : base Postgres")
    else:
        st.caption("🟠 Stockage local (éphémère sur le cloud) — "
                   "configurez Postgres pour conserver les données")
    annees  = annees_archivees()
    toutes  = sorted(set(annees + [ANNEE_EN_COURS]), reverse=True)
    annee_choisie = st.selectbox(
        "Année",
        toutes,
        index=toutes.index(ss["annee_active"]) if ss["annee_active"] in toutes else 0,
        format_func=lambda a: f"{a}  {'(en cours)' if a == ANNEE_EN_COURS else '🔒 archive'}")

    if annee_choisie != ss["annee_active"]:
        etat = charger_etat(annee_choisie)
        for k, v in etat.items():
            ss[k] = v
        ss["annee_active"] = annee_choisie
        ss["mode_archive"] = (annee_choisie != ANNEE_EN_COURS)
        st.rerun()

    if ss["mode_archive"]:
        st.warning("🔒 Archive — lecture seule")
    else:
        st.caption(f"Saison {ANNEE_EN_COURS} active")

    # ── Options admin uniquement ─────────────────────────────────────────────
    if ss["est_admin"]:
        st.divider()
        st.subheader("⚙️ Configuration")

        with st.expander(f"Clubs du challenge ({len(ss['clubs'])})",
                         expanded=False):
            if not ss["mode_archive"]:
                st.caption("Ajouter un club (nom exact de la colonne « Club »)")
                nouveau = st.text_input("Nouveau club", key="add_club",
                                        label_visibility="collapsed",
                                        placeholder="ex : TC NOUVEAU CLUB")
                if st.button("➕ Ajouter ce club", width='stretch'):
                    n = nouveau.strip()
                    if n and n not in ss["clubs"]:
                        ss["clubs"].append(n)
                        _autosave()
                        st.success(f"Club « {n} » ajouté.")
                        st.rerun()
                    elif n in ss["clubs"]:
                        st.warning("Ce club est déjà présent.")
            clubs_txt = st.text_area(
                "Liste complète (modifiable, un club par ligne)",
                value="\n".join(ss["clubs"]), height=200,
                disabled=ss["mode_archive"])
            if not ss["mode_archive"]:
                ss["clubs"] = [c.strip() for c in clubs_txt.splitlines() if c.strip()]

        with st.expander("Séries (classement → série)", expanded=False):
            st.caption("4e série jusqu'à 30/1 · 30 en 3e série")
            for s in ["2e", "3e", "4e"]:
                v = st.text_input(
                    f"Série {s}",
                    value=", ".join(ss["serie_mapping"].get(s, [])),
                    disabled=ss["mode_archive"])
                if not ss["mode_archive"]:
                    ss["serie_mapping"][s] = [x.strip() for x in
                                              v.replace("\n", ",").split(",") if x.strip()]

        arrondi_opts = ["exact", "proche", "inferieur", "superieur"]
        ss["participation"] = st.radio(
            "Participation (bonus)",
            ["inscrit", "joue"],
            format_func=lambda x: {"inscrit": "Inscrit",
                                   "joue": "A joué ≥ 1 match"}[x],
            index=1 if ss["participation"] == "joue" else 0,
            disabled=ss["mode_archive"])

        ss["arrondi"] = st.selectbox(
            "Arrondi changement de série",
            arrondi_opts,
            format_func=lambda x: {"exact": "Exact", "proche": "Au plus proche",
                                   "inferieur": "Inférieur",
                                   "superieur": "Supérieur"}[x],
            index=arrondi_opts.index(ss["arrondi"]),
            disabled=ss["mode_archive"])

        ss["n_master"] = st.number_input(
            "Qualifiés / série (master)",
            min_value=1, max_value=64, value=int(ss["n_master"]),
            disabled=ss["mode_archive"])

        st.divider()
        st.subheader("🔒 Sécurité")
        with st.expander("Changer le mot de passe admin"):
            new_mdp1 = st.text_input("Nouveau mot de passe", type="password", key="new1")
            new_mdp2 = st.text_input("Confirmer",            type="password", key="new2")
            if st.button("Enregistrer le nouveau mot de passe",
                         width='stretch'):
                if not new_mdp1:
                    st.error("Le mot de passe ne peut pas être vide.")
                elif new_mdp1 != new_mdp2:
                    st.error("Les deux mots de passe ne correspondent pas.")
                else:
                    sauvegarder_config({"mdp_hash": _hash(new_mdp1)})
                    st.success("Mot de passe mis à jour.")

        st.divider()
        st.subheader("💾 Export / import")
        st.download_button(
            "⬇️ Télécharger la sauvegarde",
            data=json.dumps(_etat_courant(), ensure_ascii=False, indent=2),
            file_name=f"challenge_{ss['annee_active']}.json",
            mime="application/json",
            width='stretch')

        if not ss["mode_archive"]:
            up = st.file_uploader("📂 Importer une sauvegarde", type=["json"])
            if up and st.button("Charger", width='stretch'):
                e = json.load(up)
                for k in ("tournois_data", "tournois_meta", "clubs",
                          "serie_mapping", "participation", "arrondi", "n_master"):
                    if k in e:
                        ss[k] = e[k]
                _autosave()
                st.success("Sauvegarde chargée.")
                st.rerun()

            if st.button("➕ Démarrer une nouvelle saison",
                         width='stretch'):
                _autosave()
                for k, v in _etat_vide().items():
                    ss[k] = v
                ss["annee_active"] = ANNEE_EN_COURS
                ss["mode_archive"] = False
                st.success("Nouvelle saison démarrée.")
                st.rerun()


# ============================================================================
# En-tête principal
# ============================================================================
annee_label = ss["annee_active"]
if ss["est_admin"]:
    st.title(f"🎾 Challenge Cœur d'Hérault — {annee_label}  🔑")
    if ss["mode_archive"]:
        st.info("🔒 Archive — lecture seule")
    else:
        st.caption("Sauvegarde automatique activée ✅  ·  "
                   "2 pts/victoire · bonus = (tournois − 1) × 3 · "
                   "changement de série : moitié des points conservée")
else:
    st.title(f"🎾 Challenge Cœur d'Hérault — {annee_label}")
    st.caption("2 pts / victoire · bonus = (nb tournois − 1) × 3 · "
               "classement par genre puis série")


# ============================================================================
# VUE ADMIN — import tournois
# ============================================================================
if ss["est_admin"] and not ss["mode_archive"]:
    st.header("1 · Importer un tournoi")
    c1, c2, c3 = st.columns([1.3, 1, 1])
    with c1:
        tid = st.selectbox(
            "Tournoi", ORDRE_IDS,
            format_func=lambda i: NOM_PAR_ID[i]
            + ("  ✅" if i in ss["tournois_data"] else ""))
    with c2:
        f_joueurs = st.file_uploader("Liste des joueurs (.xlsx)",
                                     type=["xlsx"], key="up_j")
    with c3:
        f_matchs  = st.file_uploader("Liste des matchs (.xlsx)",
                                     type=["xlsx"], key="up_m")

    def _check_cols(df, attendues, nom):
        manquantes = [c for c in attendues if c not in df.columns]
        if manquantes:
            st.error(f"Colonnes manquantes dans « {nom} » : {manquantes}")
            return False
        return True

    if f_joueurs and f_matchs:
        try:
            dj = pd.read_excel(f_joueurs)
            dm = pd.read_excel(f_matchs)
        except Exception as e:
            st.error(f"Lecture impossible : {e}")
            dj = dm = None

        if dj is not None \
                and _check_cols(dj, COLS_JOUEURS, "joueurs") \
                and _check_cols(dm, COLS_MATCHS,  "matchs"):
            data, rapport = cc.parse_tournoi(dj, dm, ss["clubs"],
                                             ss["serie_mapping"])
            m1, m2, m3 = st.columns(3)
            m1.metric("Joueurs (total)", rapport.get("nb_joueurs_total",
                                                     rapport["nb_joueurs_challenge"]))
            m2.metric("Dont clubs du challenge", rapport["nb_joueurs_challenge"])
            m3.metric("Invités (hors challenge)",
                      sum(rapport["clubs_supprimes"].values()))
            if rapport["clubs_supprimes"]:
                with st.expander("Clubs hors challenge (joueurs conservés comme invités)"):
                    st.dataframe(
                        pd.DataFrame(
                            sorted(rapport["clubs_supprimes"].items(),
                                   key=lambda x: -x[1]),
                            columns=["Club", "Nb joueurs"]),
                        hide_index=True, width='stretch')
            apercu = pd.DataFrame([
                {"Nom": v["nom"], "Prénom": v["prenom"], "Club": v["club"],
                 "Clt inscription": v["classement"], "Série": v["serie"],
                 "Genre": v["genre"], "Victoires": v["victoires"]}
                for v in data.values()])
            with st.expander(f"Aperçu des {len(apercu)} joueurs retenus"):
                st.dataframe(apercu, hide_index=True, width='stretch')

            if st.button(f"➕ Ajouter / remplacer « {NOM_PAR_ID[tid]} »",
                         type="primary"):
                ss["tournois_data"][tid] = data
                ss["tournois_meta"][tid] = {"nom": NOM_PAR_ID[tid],
                                            "rapport": rapport}
                ss["tournois_matchs"][tid] = cs.build_records(dm, data, tid)
                _autosave()
                st.success(f"« {NOM_PAR_ID[tid]} » enregistré.")
                st.rerun()

    # ── Liste des tournois importés ─────────────────────────────────────────
    st.header("2 · Tournois importés")
    if not ss["tournois_data"]:
        st.info("Aucun tournoi importé pour l'instant.")
    else:
        for i in ORDRE_IDS:
            if i not in ss["tournois_data"]:
                continue
            ca, cb = st.columns([5, 1])
            r = ss["tournois_meta"][i]["rapport"]
            ca.write(f"**{NOM_PAR_ID[i]}** — "
                     f"{r['nb_joueurs_challenge']} joueurs, "
                     f"{r['nb_matchs']} matchs")
            if cb.button("🗑️ Retirer", key=f"del_{i}"):
                ss["tournois_data"].pop(i, None)
                ss["tournois_meta"].pop(i, None)
                ss["tournois_matchs"].pop(i, None)
                _autosave()
                st.rerun()

elif ss["mode_archive"] and ss["est_admin"]:
    # Archive : juste la liste
    st.header(f"Tournois — saison {ss['annee_active']}")
    for i in ORDRE_IDS:
        if i not in ss["tournois_data"]:
            continue
        r = ss["tournois_meta"][i]["rapport"]
        st.write(f"**{NOM_PAR_ID[i]}** — "
                 f"{r['nb_joueurs_challenge']} joueurs, {r['nb_matchs']} matchs")


# ============================================================================
# Classements (communs aux deux vues)
# ============================================================================
hdr = "3 · Classements" if (ss["est_admin"] and not ss["mode_archive"]) \
    else "Classements"
st.header(hdr)

if not ss["tournois_data"]:
    if ss["est_admin"]:
        st.info("Importez au moins un tournoi pour voir les classements.")
    else:
        st.info("Aucun résultat disponible pour l'instant.")
    st.stop()

resultats, clubs = cc.compute_standings(
    ss["tournois_data"], ORDRE_IDS,
    participation=ss["participation"], mode_arrondi=ss["arrondi"])

df = pd.DataFrame(resultats)

# Fiches de match (toutes) + statistiques
match_records = []
for _t in ORDRE_IDS:
    match_records.extend(ss["tournois_matchs"].get(_t, []))
stats = cs.compute_stats(resultats, match_records) if match_records else None
dom_par_lic = {d["licence"]: d["ratio"] for d in stats["domination"]} if stats else {}

SERIES = ["2e", "3e", "4e", "1re"]


def table_serie(genre: str, serie: str, club_filtre=None, challenge_only=False):
    sub = df[(df["genre"] == genre) & (df["serie"] == serie)].copy()
    if challenge_only:
        sub = sub[sub["dans_challenge"]]
    if club_filtre and club_filtre != "Tous les clubs":
        sub = sub[sub["club"] == club_filtre]
    if sub.empty:
        st.caption("— aucun joueur —")
        return
    sub = sub.sort_values("total", ascending=False).reset_index(drop=True)
    sub.insert(0, "Rang", range(1, len(sub) + 1))
    sub["chall"] = sub["dans_challenge"].map(lambda b: "" if b else "invité")
    show = sub[["Rang", "nom", "prenom", "club", "chall",
                "classement_inscription", "classement_actuel",
                "nb_tournois", "points_match", "bonus", "total"]]
    show.columns = ["Rang", "Nom", "Prénom", "Club", "",
                    "Clt inscription", "Clt actuel",
                    "Tournois", "Pts match", "Bonus", "Total"]
    st.dataframe(show, hide_index=True, width='stretch')


# ── Onglets (communs aux deux vues, + 2 onglets admin) ──────────────────────
LABELS = ["👨 Hommes", "👩 Femmes", "🏛️ Clubs", "🏆 Master",
          "📊 Stats", "🔍 Fiche joueur", "📈 Course master", "⚖️ Comparateur",
          "📅 Historique"]
if ss["est_admin"]:
    LABELS += ["🔎 Détail / export", "🖼️ Images"]

tabs = st.tabs(LABELS)
tab_h, tab_f, tab_clubs, tab_master, tab_stats, tab_fiche, tab_course, tab_comp, tab_hist = tabs[:9]
tab_detail = tabs[9] if ss["est_admin"] else None
tab_img    = tabs[10] if ss["est_admin"] else None


# ── Hommes / Femmes (filtre club + option challenge uniquement) ──────────────
def render_genre(tab, genre):
    with tab:
        st.caption("Le classement individuel inclut tous les participants. "
                   "Les joueurs des clubs hors challenge sont marqués « invité ».")
        col_a, col_b = st.columns([2, 1])
        with col_a:
            clubs_dispo = ["Tous les clubs"] + sorted(
                {d["club"] for d in resultats if d["genre"] == genre})
            cf = st.selectbox("Filtrer par club", clubs_dispo, key=f"cf_{genre}")
        with col_b:
            chall_only = st.checkbox("Clubs du challenge uniquement",
                                     key=f"chall_{genre}")
        for s in SERIES:
            if not df[(df["genre"] == genre) & (df["serie"] == s)].empty:
                st.subheader(f"{s} série")
                table_serie(genre, s, cf, chall_only)


render_genre(tab_h, "Hommes")
render_genre(tab_f, "Femmes")

# ── Clubs ────────────────────────────────────────────────────────────────────
with tab_clubs:
    cdf = pd.DataFrame(clubs)[["rang", "club", "nb_joueurs",
                               "points_match", "bonus", "total"]]
    cdf.columns = ["Rang", "Club", "Joueurs", "Pts match", "Bonus", "Total"]
    st.dataframe(cdf, hide_index=True, width='stretch')
    st.bar_chart(cdf.set_index("Club")["Total"])

# ── Master ───────────────────────────────────────────────────────────────────
with tab_master:
    st.caption(f"Top {ss['n_master']} par genre et par série — "
               "clubs du challenge uniquement (les invités ne disputent "
               "pas le master).")
    master = cc.selection_master(resultats, ss["n_master"])
    for genre in ["Hommes", "Femmes"]:
        for s in SERIES:
            joueurs = master.get((genre, s))
            if joueurs:
                st.subheader(f"{genre} — {s} série")
                mdf = pd.DataFrame(joueurs)[
                    ["nom", "prenom", "club",
                     "classement_inscription", "classement_actuel",
                     "nb_tournois", "total"]]
                mdf.insert(0, "Rang", range(1, len(mdf) + 1))
                mdf.columns = ["Rang", "Nom", "Prénom", "Club",
                               "Clt inscription", "Clt actuel",
                               "Tournois", "Total"]
                st.dataframe(mdf, hide_index=True, width='stretch')

# ── Statistiques ─────────────────────────────────────────────────────────────
with tab_stats:
    if not stats:
        st.info("Les statistiques apparaîtront une fois des matchs importés.")
    else:
        st.subheader("🏅 Faits marquants")
        ca, cb = st.columns(2)
        with ca:
            if stats["giant_kills"]:
                g = stats["giant_kills"][0]
                st.metric("💥 Plus gros exploit",
                          f"{g['nom_g']} ({g['clt_g']})",
                          f"bat {g['nom_p']} ({g['clt_p']}) · {g['score']}")
            if stats["match_net"]:
                mn = stats["match_net"]
                st.metric("🎯 Victoire la plus nette",
                          mn["nom_g"], f"{mn['score']} vs {mn['nom_p']}")
        with cb:
            if stats["progressions"]:
                p = stats["progressions"][0]
                st.metric("📈 Meilleure progression",
                          p["nom"], f"{p['de']} → {p['vers']}")
            if stats["match_serre"]:
                msr = stats["match_serre"]
                st.metric("🔥 Match le plus serré",
                          msr["score"], f"{msr['nom_g']} vs {msr['nom_p']}")

        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**👑 Indice de domination** (% de jeux gagnés, min. 2 matchs)")
            dd = pd.DataFrame(stats["domination"][:15])
            if not dd.empty:
                dd = dd[["nom", "club", "matchs", "ratio"]]
                dd.columns = ["Joueur", "Club", "Matchs", "% jeux"]
                st.dataframe(dd, hide_index=True, width='stretch')
        with c2:
            st.markdown("**🥯 Bagels infligés** (sets 6/0)")
            bb = pd.DataFrame(stats["bagels"][:15])
            if not bb.empty:
                bb = bb[["nom", "club", "bagels"]]
                bb.columns = ["Joueur", "Club", "Bagels"]
                st.dataframe(bb, hide_index=True, width='stretch')

        st.divider()
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**🎖️ Les plus assidus**")
            aa = pd.DataFrame(stats["assidus_joueurs"][:15])
            aa.columns = ["Joueur", "Club", "Tournois"]
            st.dataframe(aa, hide_index=True, width='stretch')
        with c4:
            st.markdown("**⚖️ Clubs les plus performants** (points / joueur)")
            cd = pd.DataFrame(stats["club_depth"])
            cd = cd[["club", "joueurs", "total", "par_joueur"]]
            cd.columns = ["Club", "Joueurs", "Total", "Pts/joueur"]
            st.dataframe(cd, hide_index=True, width='stretch')

        st.divider()
        st.markdown(f"**💥 Tous les exploits** ({len(stats['giant_kills'])} "
                    "victoires contre un mieux classé)")
        if stats["giant_kills"]:
            gk = pd.DataFrame(stats["giant_kills"])[
                ["nom_g", "clt_g", "nom_p", "clt_p", "score", "tournoi"]]
            gk.columns = ["Vainqueur", "Clt", "Adversaire", "Clt adv.",
                          "Score", "Tournoi"]
            st.dataframe(gk, hide_index=True, width='stretch')

        st.divider()
        st.markdown("**🚫 Joueurs des clubs hors challenge** "
                    "(écartés à l'import, par club)")
        if hasattr(cs, "clubs_hors_challenge"):
            hors = cs.clubs_hors_challenge(ss["tournois_meta"])
            if hors:
                hdf = pd.DataFrame([{"Club": d["club"],
                                     "Présences (total)": d["total"]}
                                    for d in hors])
                st.dataframe(hdf, hide_index=True, width='stretch')
                st.caption(f"{len(hors)} clubs hors challenge · "
                           f"{sum(d['total'] for d in hors)} présences écartées "
                           "au total. Une présence = un joueur inscrit à un tournoi.")
            else:
                st.caption("Aucun joueur hors challenge écarté.")
        else:
            st.warning("Mettez à jour challenge_stats.py pour cette statistique.")

# ── Fiche joueur ─────────────────────────────────────────────────────────────
with tab_fiche:
    options = {f"{d['nom']} {d['prenom']} — {d['club']}": d["licence"]
               for d in sorted(resultats, key=lambda x: (x["nom"], x["prenom"]))}
    if not options:
        st.info("Aucun joueur.")
    else:
        choix = st.selectbox("Rechercher un joueur", list(options.keys()),
                             key="fiche_select")
        lic = options[choix]
        fj = cs.fiche_joueur(lic, resultats, match_records,
                             ss["tournois_data"], ORDRE_IDS)
        d = fj["joueur"]
        # rang dans sa série
        meme = sorted([r for r in resultats
                       if r["genre"] == d["genre"] and r["serie"] == d["serie"]],
                      key=lambda r: -r["total"])
        rang = next((i + 1 for i, r in enumerate(meme)
                     if r["licence"] == lic), None)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total", f"{d['total']:g} pts")
        k2.metric("Rang série", f"{rang} / {len(meme)}" if rang else "—")
        k3.metric("Tournois", d["nb_tournois"])
        k4.metric("% jeux gagnés",
                  f"{dom_par_lic.get(lic, '—')}" + ("%" if lic in dom_par_lic else ""))

        st.caption(f"{d['serie']} série {d['genre']} · "
                   f"classement {d['classement_inscription']} → "
                   f"{d['classement_actuel']}")

        cpt = pd.DataFrame(fj["par_tournoi"])
        if not cpt.empty:
            cpt["tournoi"] = cpt["tournoi"].map(lambda i: NOM_PAR_ID.get(i, i))
            st.markdown("**Points par tournoi**")
            st.bar_chart(cpt.set_index("tournoi")["points"])

        if fj["matchs"]:
            st.markdown("**Tous les matchs**")
            mm = pd.DataFrame(fj["matchs"])
            mm["tournoi"] = mm["tournoi"].map(lambda i: NOM_PAR_ID.get(i, i))
            mm = mm[["tournoi", "resultat", "adversaire", "clt_adv", "score"]]
            mm.columns = ["Tournoi", "Résultat", "Adversaire", "Clt adv.", "Score"]
            st.dataframe(mm, hide_index=True, width='stretch')

        # Image fiche (admin)
        if ss["est_admin"]:
            try:
                import challenge_images as ci_f
                if st.button("🖼️ Générer la carte de ce joueur (story)"):
                    fiche_img = {
                        "nom": d["nom"], "prenom": d["prenom"], "club": d["club"],
                        "serie": d["serie"], "genre": d["genre"], "rang": rang,
                        "clt_inscription": d["classement_inscription"],
                        "clt_actuel": d["classement_actuel"],
                        "nb_tournois": d["nb_tournois"],
                        "victoires": int(d["points_match"] // 2),
                        "points_match": d["points_match"], "bonus": d["bonus"],
                        "total": d["total"], "domination": dom_par_lic.get(lic),
                    }
                    noms_t = [ss["tournois_meta"][t]["nom"]
                              for t in ORDRE_IDS if t in ss["tournois_meta"]]
                    b = ci_f.image_fiche_joueur(fiche_img, noms_t, "story")
                    st.image(b, width='stretch')
                    st.download_button("⬇️ Télécharger la carte",
                                       data=b,
                                       file_name=f"fiche_{d['nom']}_{d['prenom']}.png",
                                       mime="image/png")
            except ImportError:
                pass

# ── Course au master ─────────────────────────────────────────────────────────
with tab_course:
    st.caption("Évolution des points cumulés tournoi après tournoi.")
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        g_course = st.selectbox("Genre", ["Hommes", "Femmes"], key="course_g")
    with cc2:
        series_course = sorted(
            {d["serie"] for d in resultats if d["genre"] == g_course and d["serie"]},
            key=lambda s: {"1re": 0, "2e": 1, "3e": 2, "4e": 3}.get(s, 9))
        s_course = st.selectbox("Série", series_course, key="course_s") \
            if series_course else None
    with cc3:
        n_course = st.number_input("Nb joueurs suivis", 2, 15, 6, key="course_n")

    if s_course:
        groupe = [d for d in resultats
                  if d["genre"] == g_course and d["serie"] == s_course]
        groupe = sorted(groupe, key=lambda d: -d["total"])[:int(n_course)]
        serie_lic = {d["licence"]: d["serie"] for d in groupe}
        ordre_t, courbes = cs.course_master(ss["tournois_data"], ORDRE_IDS, serie_lic)
        if ordre_t:
            noms_t = [NOM_PAR_ID.get(t, t) for t in ordre_t]
            data_courbe = {}
            for d in groupe:
                data_courbe[f"{d['nom']} {d['prenom']}"] = courbes[d["licence"]]
            chart_df = pd.DataFrame(data_courbe, index=noms_t)
            st.line_chart(chart_df)
            if ss["n_master"] and len(groupe) >= ss["n_master"]:
                seuil = groupe[ss["n_master"] - 1]["total"]
                st.caption(f"Seuil de qualification master (top {ss['n_master']}) "
                           f"≈ {seuil:g} pts")
        else:
            st.info("Pas encore de tournoi importé.")

# ── Comparateur ──────────────────────────────────────────────────────────────
with tab_comp:
    opts = {f"{d['nom']} {d['prenom']} — {d['club']}": d["licence"]
            for d in sorted(resultats, key=lambda x: (x["nom"], x["prenom"]))}
    if len(opts) < 2:
        st.info("Il faut au moins deux joueurs.")
    else:
        keys = list(opts.keys())
        col1, col2 = st.columns(2)
        with col1:
            j1 = st.selectbox("Joueur 1", keys, key="comp1")
        with col2:
            j2 = st.selectbox("Joueur 2", keys,
                              index=min(1, len(keys) - 1), key="comp2")
        d1 = next(r for r in resultats if r["licence"] == opts[j1])
        d2 = next(r for r in resultats if r["licence"] == opts[j2])

        comp = pd.DataFrame({
            "Critère": ["Club", "Genre", "Série", "Clt inscription",
                        "Clt actuel", "Tournois", "Pts match", "Bonus",
                        "Total", "% jeux gagnés"],
            d1["nom"] + " " + d1["prenom"]: [
                str(d1["club"]), str(d1["genre"]), str(d1["serie"]),
                str(d1["classement_inscription"]), str(d1["classement_actuel"]),
                str(d1["nb_tournois"]), f"{d1['points_match']:g}", str(d1["bonus"]),
                f"{d1['total']:g}", str(dom_par_lic.get(opts[j1], "—"))],
            d2["nom"] + " " + d2["prenom"]: [
                str(d2["club"]), str(d2["genre"]), str(d2["serie"]),
                str(d2["classement_inscription"]), str(d2["classement_actuel"]),
                str(d2["nb_tournois"]), f"{d2['points_match']:g}", str(d2["bonus"]),
                f"{d2['total']:g}", str(dom_par_lic.get(opts[j2], "—"))],
        })
        st.dataframe(comp, hide_index=True, width='stretch')


# ── Historique multi-années ──────────────────────────────────────────────────
with tab_hist:
    if not hasattr(cs, "palmares_multi_annees"):
        st.warning("La version de challenge_stats.py déployée n'inclut pas "
                   "encore l'historique multi-années. Mettez à jour ce fichier "
                   "sur votre dépôt pour activer cet onglet.")
        historique = {}
    else:
        historique = charger_historique_complet()

    if not hasattr(cs, "palmares_multi_annees"):
        pass
    elif len(historique) < 1:
        st.info("Aucune saison archivée pour l'instant. "
                "L'historique se remplit automatiquement à chaque saison.")
    else:
        annees_dispo = sorted(historique.keys())
        st.caption(f"Saisons disponibles : {', '.join(map(str, annees_dispo))}")

        pm = cs.palmares_multi_annees(historique)

        # Participation & points par année
        st.subheader("📊 Évolution générale")
        eg = pd.DataFrame({
            "Année": annees_dispo,
            "Joueurs classés": [pm["participation"].get(a, 0) for a in annees_dispo],
            "Total points distribués": [pm["points_annee"].get(a, 0) for a in annees_dispo],
        })
        ca, cb = st.columns(2)
        with ca:
            st.markdown("**Nombre de joueurs classés**")
            st.bar_chart(eg.set_index("Année")["Joueurs classés"])
        with cb:
            st.markdown("**Points distribués**")
            st.bar_chart(eg.set_index("Année")["Total points distribués"])

        # Palmarès par genre/série
        st.divider()
        st.subheader("🏆 Palmarès (vainqueurs par an)")
        for genre in ["Hommes", "Femmes"]:
            for s in ["2e", "3e", "4e", "1re"]:
                lignes = pm["palmares"].get((genre, s))
                if lignes:
                    st.markdown(f"**{genre} — {s} série**")
                    pdf = pd.DataFrame(lignes)[["annee", "nom", "club", "total"]]
                    pdf.columns = ["Année", "Vainqueur", "Club", "Total"]
                    st.dataframe(pdf, hide_index=True, width='stretch')

        # Classement cumulé des clubs
        st.divider()
        st.subheader("🏛️ Classement cumulé des clubs (toutes saisons)")
        cm = cs.clubs_multi_annees(historique)
        if cm:
            rows = []
            for d in cm:
                row = {"Rang": d["rang"], "Club": d["club"],
                       "Saisons": d["annees"], "Total cumulé": d["total"]}
                for a in annees_dispo:
                    row[str(a)] = round(d["detail"].get(a, 0), 1)
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')

        # Progression d'un joueur sur plusieurs années
        st.divider()
        st.subheader("📈 Progression d'un joueur sur plusieurs années")
        noms_hist = cs.liste_joueurs_historique(historique)
        if noms_hist:
            joueur_sel = st.selectbox("Joueur", noms_hist, key="hist_joueur")
            suivi = cs.progression_joueur_multi_annees(historique, joueur_sel)
            if suivi:
                sdf = pd.DataFrame(suivi)[
                    ["annee", "club", "genre", "serie",
                     "clt_inscription", "clt_actuel", "nb_tournois", "total"]]
                sdf.columns = ["Année", "Club", "Genre", "Série",
                               "Clt insc.", "Clt actuel", "Tournois", "Total"]
                st.dataframe(sdf, hide_index=True, width='stretch')
                if len(suivi) > 1:
                    st.line_chart(
                        pd.DataFrame({"Total": [s["total"] for s in suivi]},
                                     index=[str(s["annee"]) for s in suivi]))


# ── Détail / export (admin seulement) ────────────────────────────────────────
if tab_detail is not None:
    with tab_detail:
        st.caption("Tableau complet avec le détail tournoi par tournoi.")
        full = df[["nom", "prenom", "club", "genre", "serie",
                   "classement_inscription", "classement_actuel",
                   "nb_tournois", "points_match", "bonus",
                   "total", "detail"]].copy()
        full.columns = ["Nom", "Prénom", "Club", "Genre", "Série",
                        "Clt inscription", "Clt actuel",
                        "Tournois", "Pts match", "Bonus", "Total",
                        "Détail calcul"]
        st.dataframe(full, hide_index=True, width='stretch')
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            full.to_excel(w, index=False, sheet_name="Classement")
            pd.DataFrame(clubs).to_excel(w, index=False, sheet_name="Clubs")
        st.download_button(
            "⬇️ Exporter le classement (.xlsx)",
            data=buf.getvalue(),
            file_name=f"challenge_{ss['annee_active']}_classement.xlsx",
            mime="application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet")


# ── Images (admin seulement) ─────────────────────────────────────────────────
if tab_img is not None:
    with tab_img:
        try:
            import challenge_images as ci
        except ImportError:
            st.error("Installez matplotlib et pillow : "
                     "pip install matplotlib pillow")
            st.stop()

        noms_tournois = [ss["tournois_meta"][t]["nom"]
                        for t in ORDRE_IDS if t in ss["tournois_meta"]]

        st.subheader("Générer une image")
        ci1, ci2, ci3 = st.columns(3)
        with ci1:
            img_type = st.selectbox("Type", [
                "Tableau de classement", "Podium (top 3)",
                "Classement des clubs", "Qualifiés Master"])
        with ci2:
            img_fmt = st.selectbox("Format", [
                "social  (1080×1080 — WhatsApp / réseaux)",
                "print   (A4 300 dpi — impression)",
                "story   (1080×1920 — story verticale)"])
            fmt_key = ("social" if img_fmt.startswith("social")
                       else "print" if img_fmt.startswith("print")
                       else "story")
        with ci3:
            top_n_img = st.number_input("Nb joueurs affichés",
                                        min_value=3, max_value=30,
                                        value=int(ss["n_master"]))

        need_gs = img_type in ("Tableau de classement", "Podium (top 3)",
                               "Qualifiés Master")
        if need_gs:
            cg1, cg2 = st.columns(2)
            with cg1:
                img_genre = st.selectbox("Genre", ["Hommes", "Femmes"])
            with cg2:
                series_dispo = sorted(
                    {d["serie"] for d in resultats
                     if d["genre"] == img_genre and d["serie"]},
                    key=lambda s: {"1re": 0, "2e": 1, "3e": 2,
                                   "4e": 3}.get(s, 9))
                img_serie = (st.selectbox("Série", series_dispo)
                             if series_dispo else None)
        else:
            img_genre = img_serie = None

        if st.button("🎨 Générer l'image", type="primary"):
            with st.spinner("Génération en cours…"):
                try:
                    if img_type == "Tableau de classement":
                        img_bytes = ci.image_classement(
                            resultats, img_genre, img_serie,
                            noms_tournois, fmt_key, int(top_n_img))
                        fname = (f"classement_{img_genre}_"
                                 f"{img_serie}_{fmt_key}.png")
                    elif img_type == "Podium (top 3)":
                        img_bytes = ci.image_podium(
                            resultats, img_genre, img_serie,
                            noms_tournois, fmt_key)
                        fname = f"podium_{img_genre}_{img_serie}_{fmt_key}.png"
                    elif img_type == "Classement des clubs":
                        img_bytes = ci.image_clubs(clubs, noms_tournois,
                                                   fmt_key)
                        fname = f"clubs_{fmt_key}.png"
                    else:
                        img_bytes = ci.image_master(
                            resultats, img_genre, img_serie,
                            noms_tournois, int(top_n_img), fmt_key)
                        fname = (f"master_{img_genre}_"
                                 f"{img_serie}_{fmt_key}.png")
                    st.image(img_bytes, width='stretch')
                    st.download_button(f"⬇️ Télécharger {fname}",
                                       data=img_bytes, file_name=fname,
                                       mime="image/png")
                except Exception as e:
                    st.error(f"Erreur : {e}")

        st.divider()
        st.subheader("Tout exporter (ZIP)")
        bulk_fmt = st.selectbox(
            "Format",
            ["social  (1080×1080)", "print   (A4 300 dpi)"],
            key="bulk_fmt")
        bulk_key = "social" if bulk_fmt.startswith("social") else "print"

        if st.button("📦 Générer & télécharger toutes les images"):
            with st.spinner("Génération de toutes les images…"):
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w",
                                     zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr(f"clubs_{bulk_key}.png",
                                ci.image_clubs(clubs, noms_tournois,
                                               bulk_key))
                    for genre in ["Hommes", "Femmes"]:
                        for s in ["2e", "3e", "4e", "1re"]:
                            if not any(d["genre"] == genre
                                       and d["serie"] == s
                                       for d in resultats):
                                continue
                            px = f"{genre}_{s}"
                            zf.writestr(
                                f"classement_{px}_{bulk_key}.png",
                                ci.image_classement(
                                    resultats, genre, s,
                                    noms_tournois, bulk_key, 20))
                            zf.writestr(
                                f"podium_{px}_{bulk_key}.png",
                                ci.image_podium(
                                    resultats, genre, s,
                                    noms_tournois, bulk_key))
                            zf.writestr(
                                f"master_{px}_{bulk_key}.png",
                                ci.image_master(
                                    resultats, genre, s, noms_tournois,
                                    int(ss["n_master"]), bulk_key))
                zip_buf.seek(0)
                st.download_button(
                    "⬇️ Télécharger le ZIP",
                    data=zip_buf.getvalue(),
                    file_name=(f"challenge_{ss['annee_active']}"
                               f"_{bulk_key}.zip"),
                    mime="application/zip")

        # ── QR code de partage de la vue publique ───────────────────────────
        st.divider()
        st.subheader("🔗 QR code de partage")
        st.caption("Collez l'adresse publique de l'appli pour générer un QR "
                   "code à afficher au club.")
        url_pub = st.text_input("Adresse publique (URL)",
                                placeholder="https://...")
        if st.button("Générer le QR code") and url_pub:
            try:
                import qrcode
                img = qrcode.make(url_pub)
                qbuf = io.BytesIO()
                img.save(qbuf, format="PNG")
                qbuf.seek(0)
                st.image(qbuf.getvalue(), width=300)
                st.download_button("⬇️ Télécharger le QR code",
                                   data=qbuf.getvalue(),
                                   file_name="qr_challenge.png",
                                   mime="image/png")
            except ImportError:
                st.error("Module qrcode absent : pip install \"qrcode[pil]\"")
