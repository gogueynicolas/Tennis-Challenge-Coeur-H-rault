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
# Sauvegarde / chargement automatique
# ============================================================================
def _fichier_sauvegarde(annee: int) -> str:
    return f"challenge_sauvegarde_{annee}.json"


def _etat_vide() -> dict:
    return {
        "annee": ANNEE_EN_COURS,
        "tournois_data": {},
        "tournois_meta": {},
        "clubs": list(cc.CHALLENGE_CLUBS_DEFAUT),
        "serie_mapping": {k: list(v) for k, v in cc.SERIE_MAPPING_DEFAUT.items()},
        "participation": "joue",
        "arrondi": "exact",
        "n_master": 8,
    }


def charger_etat(annee: int) -> dict:
    path = _fichier_sauvegarde(annee)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _etat_vide()


def sauvegarder_etat(etat: dict) -> None:
    path = _fichier_sauvegarde(etat.get("annee", ANNEE_EN_COURS))
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(etat, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.warning(f"Sauvegarde impossible : {e}")


def annees_archivees() -> list:
    annees = []
    for fname in os.listdir("."):
        if fname.startswith("challenge_sauvegarde_") and fname.endswith(".json"):
            try:
                annees.append(int(fname.replace("challenge_sauvegarde_", "").replace(".json", "")))
            except ValueError:
                pass
    return sorted(annees, reverse=True)


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

        with st.expander("Clubs du challenge", expanded=False):
            clubs_txt = st.text_area(
                "Un club par ligne",
                value="\n".join(ss["clubs"]), height=160,
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
            file_name=_fichier_sauvegarde(ss["annee_active"]),
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
            m1.metric("Joueurs retenus",  rapport["nb_joueurs_challenge"])
            m2.metric("Matchs",           rapport["nb_matchs"])
            m3.metric("Clubs supprimés",  sum(rapport["clubs_supprimes"].values()))
            if rapport["clubs_supprimes"]:
                with st.expander("Clubs hors challenge supprimés"):
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


def table_serie(genre: str, serie: str):
    sub = df[(df["genre"] == genre) & (df["serie"] == serie)].copy()
    if sub.empty:
        st.caption("— aucun joueur —")
        return
    sub = sub.sort_values("total", ascending=False).reset_index(drop=True)
    sub.insert(0, "Rang", range(1, len(sub) + 1))
    show = sub[["Rang", "nom", "prenom", "club",
                "classement_inscription", "classement_actuel",
                "nb_tournois", "points_match", "bonus", "total"]]
    show.columns = ["Rang", "Nom", "Prénom", "Club",
                    "Clt inscription", "Clt actuel",
                    "Tournois", "Pts match", "Bonus", "Total"]
    st.dataframe(show, hide_index=True, width='stretch')


# ── Onglets : différents selon le mode ──────────────────────────────────────
if ss["est_admin"]:
    tabs = st.tabs(["👨 Hommes", "👩 Femmes", "🏛️ Clubs", "🏆 Master",
                    "🔎 Détail / export", "🖼️ Images"])
    tab_h, tab_f, tab_clubs, tab_master, tab_detail, tab_img = tabs
else:
    tabs = st.tabs(["👨 Hommes", "👩 Femmes", "🏛️ Clubs", "🏆 Master"])
    tab_h, tab_f, tab_clubs, tab_master = tabs
    tab_detail = tab_img = None


# ── Hommes ───────────────────────────────────────────────────────────────────
with tab_h:
    for s in ["2e", "3e", "4e", "1re"]:
        if not df[(df["genre"] == "Hommes") & (df["serie"] == s)].empty:
            st.subheader(f"{s} série")
            table_serie("Hommes", s)

# ── Femmes ───────────────────────────────────────────────────────────────────
with tab_f:
    for s in ["2e", "3e", "4e", "1re"]:
        if not df[(df["genre"] == "Femmes") & (df["serie"] == s)].empty:
            st.subheader(f"{s} série")
            table_serie("Femmes", s)

# ── Clubs ────────────────────────────────────────────────────────────────────
with tab_clubs:
    cdf = pd.DataFrame(clubs)[["rang", "club", "nb_joueurs",
                               "points_match", "bonus", "total"]]
    cdf.columns = ["Rang", "Club", "Joueurs", "Pts match", "Bonus", "Total"]
    st.dataframe(cdf, hide_index=True, width='stretch')
    st.bar_chart(cdf.set_index("Club")["Total"])

# ── Master ───────────────────────────────────────────────────────────────────
with tab_master:
    st.caption(f"Top {ss['n_master']} par genre et par série.")
    master = cc.selection_master(resultats, ss["n_master"])
    for genre in ["Hommes", "Femmes"]:
        for s in ["2e", "3e", "4e", "1re"]:
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
                "print   (A4 300 dpi — impression)"])
            fmt_key = "social" if img_fmt.startswith("social") else "print"
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
