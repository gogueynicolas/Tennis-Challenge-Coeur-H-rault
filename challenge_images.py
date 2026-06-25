"""
challenge_images.py
===================
Génération d'images pour le Challenge Cœur d'Hérault.

Trois types d'images :
  1. Tableau de classement par série (style affiche)
  2. Podium visuel top 3 (style réseau social)
  3. Classement des clubs (barre horizontale)

Deux formats :
  - "social"    : 1080×1080 px (carré, WhatsApp / Instagram)
  - "print"     : 2480×3508 px (A4 à 300 dpi, impression)

Retourne des bytes PNG prêts à télécharger.
"""

from __future__ import annotations
import io
import math
import textwrap
from typing import List, Dict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.patheffects as pe
import numpy as np

# ── Palette ────────────────────────────────────────────────────────────────
C_BG       = "#0D1B2A"   # fond sombre
C_HEADER   = "#1B4F72"   # bleu foncé bande titre
C_ACCENT   = "#F4D03F"   # or
C_GREEN    = "#27AE60"   # vert (1re place)
C_SILVER   = "#BDC3C7"   # argent (2e)
C_BRONZE   = "#D35400"   # bronze (3e)
C_ROW_ODD  = "#152535"
C_ROW_EVEN = "#1A2D40"
C_TEXT     = "#FFFFFF"
C_SUBTEXT  = "#AED6F1"
C_CLUB_BAR = "#2E86C1"

MEDAL_COLORS = [C_GREEN, C_SILVER, C_BRONZE]

FONT_TITLE  = 28
FONT_SUB    = 18
FONT_TABLE  = 14
FONT_SMALL  = 11


def _fig_to_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _pts_label(d: dict) -> str:
    return f"{d['total']:.0f} pts" if d['total'] == int(d['total']) else f"{d['total']} pts"


def _serie_color(serie: str) -> str:
    return {"4e": "#E67E22", "3e": "#2980B9", "2e": "#8E44AD",
            "1re": "#C0392B"}.get(serie, C_ACCENT)


# ── Dimensions ─────────────────────────────────────────────────────────────
FORMATS = {
    "social": {"px": (1080, 1080), "dpi": 96},
    "print":  {"px": (2480, 3508), "dpi": 300},
    "story":  {"px": (1080, 1920), "dpi": 96},
}


def _fig_size(fmt: str) -> tuple[float, float]:
    px = FORMATS[fmt]["px"]
    dpi = FORMATS[fmt]["dpi"]
    return px[0] / dpi, px[1] / dpi


# ═══════════════════════════════════════════════════════════════════════════
# 1. TABLEAU DE CLASSEMENT (style affiche)
# ═══════════════════════════════════════════════════════════════════════════

def image_classement(
    resultats: List[Dict],
    genre: str,
    serie: str,
    tournois_affiches: List[str],
    fmt: str = "social",
    top_n: int = 20,
) -> bytes:
    """
    Tableau de classement pour un genre + série.
    tournois_affiches : liste des noms de tournois importés (pour le sous-titre).
    """
    sub = [d for d in resultats if d["genre"] == genre and d["serie"] == serie]
    sub = sorted(sub, key=lambda d: -d["total"])[:top_n]

    w, h = _fig_size(fmt)
    dpi = FORMATS[fmt]["dpi"]
    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.axis("off")

    # ── En-tête ────────────────────────────────────────────────────────────
    scale = w / 11.25          # facteur d'échelle vs format de référence
    fs_title = FONT_TITLE * scale
    fs_sub   = FONT_SUB   * scale
    fs_tab   = FONT_TABLE * scale
    fs_small = FONT_SMALL * scale

    fig.text(0.5, 0.97, "🎾 Challenge Cœur d'Hérault",
             ha="center", va="top", color=C_ACCENT,
             fontsize=fs_title * 1.1, fontweight="bold")

    tournois_str = " · ".join(tournois_affiches) if tournois_affiches else "—"
    fig.text(0.5, 0.935, tournois_str,
             ha="center", va="top", color=C_SUBTEXT, fontsize=fs_small)

    serie_c = _serie_color(serie)
    fig.text(0.5, 0.905,
             f"{genre}  —  {serie} série",
             ha="center", va="top", color=serie_c,
             fontsize=fs_sub * 1.15, fontweight="bold")

    # ── Tableau ────────────────────────────────────────────────────────────
    if not sub:
        fig.text(0.5, 0.5, "Aucun joueur", ha="center", va="center",
                 color=C_TEXT, fontsize=fs_sub)
        return _fig_to_bytes(fig)

    n = len(sub)
    row_h = min(0.72 / n, 0.06)          # hauteur d'une ligne
    y_start = 0.875
    pad = 0.012

    # colonnes : rang / nom-prénom / club / tournois / pts
    cols_x  = [0.03, 0.10, 0.44, 0.76, 0.89]
    cols_w  = [0.07, 0.34, 0.32, 0.13, 0.11]
    headers = ["#",  "Nom / Prénom",  "Club",  "T",  "Pts"]
    haligns = ["center", "left", "left", "center", "center"]

    # en-tête colonnes
    y_hdr = y_start - pad
    ax2 = fig.add_axes([0.03, y_hdr - row_h * 0.9, 0.94, row_h * 0.9])
    ax2.set_facecolor(C_HEADER)
    ax2.axis("off")
    for j, (hdr, cx, ha) in enumerate(zip(headers, cols_x, haligns)):
        fig.text(cx + (cols_w[j] / 2 if ha == "center" else 0.005),
                 y_hdr - row_h * 0.45,
                 hdr, ha=ha, va="center",
                 color=C_ACCENT, fontsize=fs_tab * 0.95, fontweight="bold")

    y_cur = y_hdr - row_h * 1.05
    for i, d in enumerate(sub):
        bg = C_ROW_ODD if i % 2 == 0 else C_ROW_EVEN
        # médailles top 3
        if i < 3:
            bg = {0: "#1A3A1A", 1: "#1C2020", 2: "#2A1A0A"}[i]
        axr = fig.add_axes([0.03, y_cur - row_h * 0.92, 0.94, row_h * 0.92])
        axr.set_facecolor(bg)
        axr.axis("off")

        rang_c = MEDAL_COLORS[i] if i < 3 else C_TEXT
        vals = [
            (f"{i+1}", cols_x[0], "center"),
            (f"{d['nom']} {d['prenom']}", cols_x[1], "left"),
            (d["club"], cols_x[2], "left"),
            (str(d["nb_tournois"]), cols_x[3], "center"),
            (_pts_label(d), cols_x[4], "center"),
        ]
        for k, (val, cx, ha) in enumerate(vals):
            c = rang_c if k == 0 else (C_ACCENT if k == 4 else C_TEXT)
            fw = "bold" if k in (0, 4) else "normal"
            # tronquer le texte long
            if k in (1, 2):
                val = val[:28] + "…" if len(val) > 28 else val
            fig.text(cx + (cols_w[k] / 2 if ha == "center" else 0.005),
                     y_cur - row_h * 0.46,
                     val, ha=ha, va="center",
                     color=c, fontsize=fs_tab * (0.9 if k == 2 else 1.0),
                     fontweight=fw)
        y_cur -= row_h * 1.02

    # ── Pied de page ───────────────────────────────────────────────────────
    fig.text(0.5, 0.015,
             "2 pts/victoire  ·  bonus = (tournois − 1) × 3  ·  Challenge Cœur d'Hérault",
             ha="center", va="bottom", color=C_SUBTEXT, fontsize=fs_small * 0.85)

    return _fig_to_bytes(fig)


# ═══════════════════════════════════════════════════════════════════════════
# 2. PODIUM VISUEL top 3
# ═══════════════════════════════════════════════════════════════════════════

def image_podium(
    resultats: List[Dict],
    genre: str,
    serie: str,
    tournois_affiches: List[str],
    fmt: str = "social",
) -> bytes:
    """Podium visuel des 3 premiers d'un genre/série."""
    sub = [d for d in resultats if d["genre"] == genre and d["serie"] == serie]
    sub = sorted(sub, key=lambda d: -d["total"])[:3]

    w, h = _fig_size(fmt)
    dpi = FORMATS[fmt]["dpi"]
    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.set_xlim(0, 3)
    ax.set_ylim(0, 3)
    ax.axis("off")

    scale = w / 11.25
    fs_title = FONT_TITLE * scale
    fs_sub   = FONT_SUB   * scale
    fs_tab   = FONT_TABLE * scale
    fs_small = FONT_SMALL * scale

    # Titre
    fig.text(0.5, 0.97, "🎾 Challenge Cœur d'Hérault",
             ha="center", va="top", color=C_ACCENT,
             fontsize=fs_title * 1.1, fontweight="bold")
    tournois_str = " · ".join(tournois_affiches) if tournois_affiches else "—"
    fig.text(0.5, 0.935, tournois_str,
             ha="center", va="top", color=C_SUBTEXT, fontsize=fs_small)
    serie_c = _serie_color(serie)
    fig.text(0.5, 0.905, f"Podium  {genre}  —  {serie} série",
             ha="center", va="top", color=serie_c,
             fontsize=fs_sub * 1.15, fontweight="bold")

    if not sub:
        fig.text(0.5, 0.5, "Pas assez de joueurs",
                 ha="center", va="center", color=C_TEXT, fontsize=fs_sub)
        return _fig_to_bytes(fig)

    # Ordre podium : 2 / 1 / 3
    order = [1, 0, 2]  # indices dans sub
    positions_x = [0.22, 0.50, 0.78]
    heights      = [0.34, 0.44, 0.28]   # hauteur du socle (coordonnées fig)
    labels_rang  = ["2e", "1er" if genre == "Hommes" else "1re", "3e"]
    medals       = [C_SILVER, C_GREEN, C_BRONZE]
    emoji_medals = ["🥈", "🥇", "🥉"]

    base_y = 0.18  # bas du socle

    for pos, (idx, cx, ht, rang_lbl, mc, em) in enumerate(
            zip(order, positions_x, heights, labels_rang, medals, emoji_medals)):

        if idx >= len(sub):
            continue
        d = sub[idx]

        # Socle
        rect = FancyBboxPatch(
            (cx - 0.14, base_y), 0.28, ht,
            boxstyle="round,pad=0.005",
            linewidth=2, edgecolor=mc,
            facecolor=mc + "33",   # transparence
            transform=fig.transFigure, figure=fig)
        fig.add_artist(rect)

        # Rang
        fig.text(cx, base_y + ht / 2, em,
                 ha="center", va="center",
                 fontsize=fs_title * 1.6, transform=fig.transFigure)

        # Étiquette rang
        fig.text(cx, base_y + ht + 0.015, rang_lbl,
                 ha="center", va="bottom", color=mc,
                 fontsize=fs_sub * 1.1, fontweight="bold",
                 transform=fig.transFigure)

        # Nom / Prénom
        nom_court = d["nom"][:14] + "." if len(d["nom"]) > 14 else d["nom"]
        prenom_court = d["prenom"][:10] + "." if len(d["prenom"]) > 10 else d["prenom"]
        fig.text(cx, base_y + ht + 0.065,
                 f"{nom_court}\n{prenom_court}",
                 ha="center", va="bottom", color=C_TEXT,
                 fontsize=fs_tab * 1.05, fontweight="bold",
                 linespacing=1.3, transform=fig.transFigure)

        # Club
        club_court = d["club"][:22] + "…" if len(d["club"]) > 22 else d["club"]
        fig.text(cx, base_y + ht + 0.135,
                 club_court,
                 ha="center", va="bottom", color=C_SUBTEXT,
                 fontsize=fs_small * 0.9, transform=fig.transFigure)

        # Points
        fig.text(cx, base_y + ht + 0.17,
                 _pts_label(d),
                 ha="center", va="bottom", color=C_ACCENT,
                 fontsize=fs_sub, fontweight="bold",
                 transform=fig.transFigure)

    fig.text(0.5, 0.015,
             "2 pts/victoire  ·  bonus = (tournois − 1) × 3  ·  Challenge Cœur d'Hérault",
             ha="center", va="bottom", color=C_SUBTEXT, fontsize=fs_small * 0.85)

    return _fig_to_bytes(fig)


# ═══════════════════════════════════════════════════════════════════════════
# 3. CLASSEMENT DES CLUBS
# ═══════════════════════════════════════════════════════════════════════════

def image_clubs(
    clubs: List[Dict],
    tournois_affiches: List[str],
    fmt: str = "social",
) -> bytes:
    """Graphique en barres horizontales du classement des clubs."""
    clubs = sorted(clubs, key=lambda d: d["total"], reverse=True)

    w, h = _fig_size(fmt)
    dpi = FORMATS[fmt]["dpi"]
    scale = w / 11.25
    fs_title = FONT_TITLE * scale
    fs_sub   = FONT_SUB   * scale
    fs_tab   = FONT_TABLE * scale
    fs_small = FONT_SMALL * scale

    fig = plt.figure(figsize=(w, h), dpi=dpi, facecolor=C_BG)

    # zone titre (20 % haut) + zone graphe (75 %)
    ax_title = fig.add_axes([0, 0.80, 1, 0.18])
    ax_title.set_facecolor(C_BG)
    ax_title.axis("off")
    ax_title.text(0.5, 0.85, "🎾 Challenge Cœur d'Hérault",
                  ha="center", va="top", color=C_ACCENT,
                  fontsize=fs_title * 1.1, fontweight="bold",
                  transform=ax_title.transAxes)
    tournois_str = " · ".join(tournois_affiches) if tournois_affiches else "—"
    ax_title.text(0.5, 0.55, tournois_str,
                  ha="center", va="top", color=C_SUBTEXT,
                  fontsize=fs_small, transform=ax_title.transAxes)
    ax_title.text(0.5, 0.25, "Classement des Clubs",
                  ha="center", va="top", color=C_SUBTEXT,
                  fontsize=fs_sub * 1.1, fontweight="bold",
                  transform=ax_title.transAxes)

    ax = fig.add_axes([0.32, 0.06, 0.64, 0.72])
    ax.set_facecolor(C_BG)
    ax.spines[:].set_visible(False)
    ax.tick_params(colors=C_TEXT, labelsize=fs_tab)

    noms  = [c["club"] for c in clubs]
    pts   = [c["total"] for c in clubs]
    y_pos = np.arange(len(noms))

    bar_colors = [C_GREEN if i == 0 else C_CLUB_BAR for i in range(len(noms))]
    bars = ax.barh(y_pos, pts, color=bar_colors, height=0.6, edgecolor="none")

    # noms à gauche
    ax_noms = fig.add_axes([0.01, 0.06, 0.30, 0.72])
    ax_noms.set_facecolor(C_BG)
    ax_noms.axis("off")
    ax_noms.set_ylim(-0.5, len(noms) - 0.5)
    for i, nom in enumerate(noms):
        c = C_ACCENT if i == 0 else C_TEXT
        fw = "bold" if i == 0 else "normal"
        nm = nom[:22] + "…" if len(nom) > 22 else nom
        ax_noms.text(1.0, i, nm, ha="right", va="center",
                     color=c, fontsize=fs_tab, fontweight=fw)

    # valeurs à droite des barres
    for bar, val in zip(bars, pts):
        ax.text(bar.get_width() + max(pts) * 0.01, bar.get_y() + bar.get_height() / 2,
                f"{val:.0f}" if val == int(val) else f"{val}",
                va="center", ha="left", color=C_ACCENT,
                fontsize=fs_tab, fontweight="bold")

    ax.set_yticks([])
    ax.set_xticks([])
    ax.invert_yaxis()
    ax.set_xlim(0, max(pts) * 1.18)

    # nb joueurs
    for i, c in enumerate(clubs):
        ax.text(max(pts) * 0.005, i, f"{c['nb_joueurs']} j.",
                va="center", ha="left", color=C_SUBTEXT,
                fontsize=fs_small * 0.85)

    fig.text(0.5, 0.015,
             "Points = pts match + bonus  ·  Challenge Cœur d'Hérault",
             ha="center", va="bottom", color=C_SUBTEXT, fontsize=fs_small * 0.85)

    return _fig_to_bytes(fig)


# ═══════════════════════════════════════════════════════════════════════════
# 4. SÉLECTION MASTER
# ═══════════════════════════════════════════════════════════════════════════

def image_master(
    resultats: List[Dict],
    genre: str,
    serie: str,
    tournois_affiches: List[str],
    n: int = 8,
    fmt: str = "social",
) -> bytes:
    """Tableau de sélection master pour un genre/série (top n)."""
    sub = [d for d in resultats if d["genre"] == genre and d["serie"] == serie]
    sub = sorted(sub, key=lambda d: -d["total"])[:n]

    # On réutilise la fonction classement avec un titre adapté
    img_bytes = image_classement(sub, genre, serie, tournois_affiches, fmt, top_n=n)
    # On va recréer avec titre "Master" pour distinguer
    w, h = _fig_size(fmt)
    dpi = FORMATS[fmt]["dpi"]
    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.axis("off")

    scale = w / 11.25
    fs_title = FONT_TITLE * scale
    fs_sub   = FONT_SUB   * scale
    fs_tab   = FONT_TABLE * scale
    fs_small = FONT_SMALL * scale

    tournois_str = " · ".join(tournois_affiches) if tournois_affiches else "—"
    fig.text(0.5, 0.97, "🎾 Challenge Cœur d'Hérault",
             ha="center", va="top", color=C_ACCENT,
             fontsize=fs_title * 1.1, fontweight="bold")
    fig.text(0.5, 0.935, tournois_str,
             ha="center", va="top", color=C_SUBTEXT, fontsize=fs_small)

    serie_c = _serie_color(serie)
    fig.text(0.5, 0.905,
             f"🏆 Qualifiés Master  ·  {genre}  ·  {serie} série",
             ha="center", va="top", color=serie_c,
             fontsize=fs_sub * 1.15, fontweight="bold")

    if not sub:
        fig.text(0.5, 0.5, "Aucun joueur", ha="center", va="center",
                 color=C_TEXT, fontsize=fs_sub)
        return _fig_to_bytes(fig)

    n_rows = len(sub)
    row_h = min(0.72 / n_rows, 0.07)
    y_start = 0.875
    pad = 0.012

    cols_x  = [0.03, 0.10, 0.44, 0.76, 0.89]
    cols_w  = [0.07, 0.34, 0.32, 0.13, 0.11]
    headers = ["#",  "Nom / Prénom",  "Club",  "T",  "Pts"]
    haligns = ["center", "left", "left", "center", "center"]

    y_hdr = y_start - pad
    ax2 = fig.add_axes([0.03, y_hdr - row_h * 0.9, 0.94, row_h * 0.9])
    ax2.set_facecolor(C_HEADER)
    ax2.axis("off")
    for j, (hdr, cx, ha) in enumerate(zip(headers, cols_x, haligns)):
        fig.text(cx + (cols_w[j] / 2 if ha == "center" else 0.005),
                 y_hdr - row_h * 0.45,
                 hdr, ha=ha, va="center",
                 color=C_ACCENT, fontsize=fs_tab * 0.95, fontweight="bold")

    y_cur = y_hdr - row_h * 1.05
    for i, d in enumerate(sub):
        bg = C_ROW_ODD if i % 2 == 0 else C_ROW_EVEN
        if i < 3:
            bg = {0: "#1A3A1A", 1: "#1C2020", 2: "#2A1A0A"}[i]
        axr = fig.add_axes([0.03, y_cur - row_h * 0.92, 0.94, row_h * 0.92])
        axr.set_facecolor(bg)
        axr.axis("off")
        rang_c = MEDAL_COLORS[i] if i < 3 else C_TEXT
        vals = [
            (f"{i+1}", cols_x[0], "center"),
            (f"{d['nom']} {d['prenom']}", cols_x[1], "left"),
            (d["club"], cols_x[2], "left"),
            (str(d["nb_tournois"]), cols_x[3], "center"),
            (_pts_label(d), cols_x[4], "center"),
        ]
        for k, (val, cx, ha) in enumerate(vals):
            c = rang_c if k == 0 else (C_ACCENT if k == 4 else C_TEXT)
            fw = "bold" if k in (0, 4) else "normal"
            if k in (1, 2):
                val = val[:28] + "…" if len(val) > 28 else val
            fig.text(cx + (cols_w[k] / 2 if ha == "center" else 0.005),
                     y_cur - row_h * 0.46,
                     val, ha=ha, va="center",
                     color=c, fontsize=fs_tab * (0.9 if k == 2 else 1.0),
                     fontweight=fw)
        y_cur -= row_h * 1.02

    fig.text(0.5, 0.015,
             "2 pts/victoire  ·  bonus = (tournois − 1) × 3  ·  Challenge Cœur d'Hérault",
             ha="center", va="bottom", color=C_SUBTEXT, fontsize=fs_small * 0.85)

    return _fig_to_bytes(fig)


# ═══════════════════════════════════════════════════════════════════════════
# 5. FICHE JOUEUR (carte individuelle, idéale story / partage)
# ═══════════════════════════════════════════════════════════════════════════

def image_fiche_joueur(fiche: dict, tournois_affiches, fmt: str = "story") -> bytes:
    """
    Carte individuelle d'un joueur.
    fiche attend les clés : nom, prenom, club, serie, genre, rang,
      clt_inscription, clt_actuel, nb_tournois, victoires, points_match,
      bonus, total, domination (ou None).
    """
    w, h = _fig_size(fmt)
    dpi = FORMATS[fmt]["dpi"]
    fig, ax = plt.subplots(figsize=(w, h), dpi=dpi)
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    ax.axis("off")

    scale = w / 11.25
    fs_title = FONT_TITLE * scale
    fs_sub   = FONT_SUB   * scale
    fs_tab   = FONT_TABLE * scale
    fs_small = FONT_SMALL * scale

    serie_c = _serie_color(fiche.get("serie"))

    # En-tête
    fig.text(0.5, 0.96, "🎾 Challenge Cœur d'Hérault",
             ha="center", va="top", color=C_ACCENT,
             fontsize=fs_title, fontweight="bold")
    tournois_str = " · ".join(tournois_affiches) if tournois_affiches else "—"
    fig.text(0.5, 0.925, tournois_str, ha="center", va="top",
             color=C_SUBTEXT, fontsize=fs_small)

    # Bandeau nom
    y = 0.86
    fig.text(0.5, y, f"{fiche['prenom']} {fiche['nom']}".strip(),
             ha="center", va="center", color=C_TEXT,
             fontsize=fs_title * 1.3, fontweight="bold")
    fig.text(0.5, y - 0.045, fiche.get("club", ""),
             ha="center", va="center", color=C_SUBTEXT, fontsize=fs_sub)

    # Pastille rang + série
    rang = fiche.get("rang")
    if rang:
        fig.text(0.5, y - 0.10,
                 f"{rang}{'er' if rang == 1 else 'e'} — {fiche.get('serie','?')} série "
                 f"({fiche.get('genre','')})",
                 ha="center", va="center", color=serie_c,
                 fontsize=fs_sub * 1.1, fontweight="bold")

    # Grand total
    fig.text(0.5, 0.66, _pts_label(fiche),
             ha="center", va="center", color=C_ACCENT,
             fontsize=fs_title * 2.0, fontweight="bold")
    fig.text(0.5, 0.605, "points au total",
             ha="center", va="center", color=C_SUBTEXT, fontsize=fs_tab)

    # Tableau de stats clés
    lignes = [
        ("Tournois disputés",  str(fiche.get("nb_tournois", "—"))),
        ("Matchs gagnés",      str(fiche.get("victoires", "—"))),
        ("Points de match",    f"{fiche.get('points_match', 0):g}"),
        ("Points bonus",       f"{fiche.get('bonus', 0):g}"),
        ("Classement",         f"{fiche.get('clt_inscription','?')} → {fiche.get('clt_actuel','?')}"),
    ]
    if fiche.get("domination") is not None:
        lignes.append(("Jeux gagnés", f"{fiche['domination']}%"))

    y0 = 0.50
    dy = 0.058
    for i, (k, v) in enumerate(lignes):
        yy = y0 - i * dy
        bg = C_ROW_ODD if i % 2 == 0 else C_ROW_EVEN
        axr = fig.add_axes([0.12, yy - dy * 0.42, 0.76, dy * 0.8])
        axr.set_facecolor(bg)
        axr.axis("off")
        fig.text(0.16, yy, k, ha="left", va="center",
                 color=C_SUBTEXT, fontsize=fs_tab)
        fig.text(0.84, yy, v, ha="right", va="center",
                 color=C_TEXT, fontsize=fs_tab, fontweight="bold")

    fig.text(0.5, 0.02,
             "2 pts/victoire · bonus = (tournois − 1) × 3 · Challenge Cœur d'Hérault",
             ha="center", va="bottom", color=C_SUBTEXT, fontsize=fs_small * 0.85)

    return _fig_to_bytes(fig)
