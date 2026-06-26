"""
challenge_storage.py
====================
Couche de persistance durable du Challenge Cœur d'Hérault.

Deux backends, choisis automatiquement :
  1. PostgreSQL (Supabase / Neon)  -> si une connexion est configurée
     (via st.secrets["postgres"]["url"] ou la variable d'env DATABASE_URL)
  2. Système de fichiers local (dossier data/) -> repli automatique

L'état d'une saison est stocké comme un seul document JSON par année,
dans une table `challenge_saisons (annee INT PRIMARY KEY, etat JSONB,
maj TIMESTAMP)`. Cela colle au modèle « 1 fichier JSON par an » déjà utilisé,
tout en étant durable sur Streamlit Cloud.

Aucune dépendance dure : si psycopg2 ou la config manquent, on bascule
silencieusement sur les fichiers locaux.
"""

from __future__ import annotations
import os
import json
import datetime

try:
    import streamlit as st
except Exception:                      # utilisable hors Streamlit (tests)
    st = None

# --- dossier de repli local --------------------------------------------------
DATA_DIR = "data"
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)


# =============================================================================
# Détection de la connexion Postgres
# =============================================================================
def _db_url() -> str | None:
    """Récupère l'URL de connexion depuis les secrets Streamlit ou l'env."""
    # 1. st.secrets["postgres"]["url"]
    if st is not None:
        try:
            return st.secrets["postgres"]["url"]
        except Exception:
            pass
    # 2. variable d'environnement
    return os.environ.get("DATABASE_URL")


def _get_conn():
    """Ouvre une connexion psycopg2, ou None si indisponible."""
    url = _db_url()
    if not url:
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(url, connect_timeout=8)
        conn.autocommit = True
        return conn
    except Exception:
        return None


_BACKEND_CACHE = {"checked": False, "db": False}


def backend() -> str:
    """Renvoie 'postgres' ou 'fichier' (avec mise en cache)."""
    if not _BACKEND_CACHE["checked"]:
        conn = _get_conn()
        if conn is not None:
            try:
                _init_schema(conn)
                _BACKEND_CACHE["db"] = True
            except Exception:
                _BACKEND_CACHE["db"] = False
            finally:
                conn.close()
        _BACKEND_CACHE["checked"] = True
    return "postgres" if _BACKEND_CACHE["db"] else "fichier"


def reset_backend_cache():
    _BACKEND_CACHE["checked"] = False
    _BACKEND_CACHE["db"] = False


def _init_schema(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS challenge_saisons (
                annee INTEGER PRIMARY KEY,
                etat  JSONB NOT NULL,
                maj   TIMESTAMP DEFAULT NOW()
            );
        """)


# =============================================================================
# Repli fichier
# =============================================================================
def _fichier(annee: int) -> str:
    return os.path.join(DATA_DIR, f"challenge_{annee}.json")


def _migrer_anciens_fichiers():
    for fname in os.listdir("."):
        if fname.startswith("challenge_sauvegarde_") and fname.endswith(".json"):
            try:
                a = int(fname.replace("challenge_sauvegarde_", "").replace(".json", ""))
            except ValueError:
                continue
            dest = _fichier(a)
            if not os.path.exists(dest):
                try:
                    with open(fname, encoding="utf-8") as f:
                        data = json.load(f)
                    with open(dest, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass


def _fichier_charger(annee: int):
    path = _fichier(annee)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _fichier_sauver(annee: int, etat: dict):
    path = _fichier(annee)
    try:
        if os.path.exists(path):
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            import shutil
            shutil.copy2(path, os.path.join(BACKUP_DIR, f"challenge_{annee}_{ts}.json"))
            _nettoyer_backups(annee)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(etat, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _nettoyer_backups(annee: int, garder: int = 10):
    prefixe = f"challenge_{annee}_"
    fichiers = sorted([f for f in os.listdir(BACKUP_DIR)
                       if f.startswith(prefixe)], reverse=True)
    for f in fichiers[garder:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, f))
        except Exception:
            pass


def _fichier_annees() -> list:
    _migrer_anciens_fichiers()
    annees = []
    if os.path.isdir(DATA_DIR):
        for fname in os.listdir(DATA_DIR):
            if fname.startswith("challenge_") and fname.endswith(".json"):
                try:
                    annees.append(int(fname.replace("challenge_", "").replace(".json", "")))
                except ValueError:
                    pass
    return sorted(set(annees), reverse=True)


# =============================================================================
# API publique  (commute automatiquement DB <-> fichier)
# =============================================================================
def charger(annee: int):
    """Charge l'état d'une saison, ou None."""
    if backend() == "postgres":
        conn = _get_conn()
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT etat FROM challenge_saisons WHERE annee=%s",
                                (annee,))
                    row = cur.fetchone()
                    if row:
                        val = row[0]
                        if isinstance(val, str):
                            val = json.loads(val)
                        return val
                    return None
            finally:
                conn.close()
    return _fichier_charger(annee)


def sauver(annee: int, etat: dict):
    """Enregistre l'état d'une saison (DB + repli fichier en secours)."""
    ok_db = False
    if backend() == "postgres":
        conn = _get_conn()
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO challenge_saisons (annee, etat, maj)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (annee)
                        DO UPDATE SET etat = EXCLUDED.etat, maj = NOW();
                    """, (annee, json.dumps(etat, ensure_ascii=False)))
                ok_db = True
            except Exception:
                ok_db = False
            finally:
                conn.close()
    # On garde toujours une copie fichier locale (utile en dev / secours)
    _fichier_sauver(annee, etat)
    return ok_db


def annees() -> list:
    """Liste des années disponibles, fusion DB + fichiers."""
    res = set(_fichier_annees())
    if backend() == "postgres":
        conn = _get_conn()
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT annee FROM challenge_saisons ORDER BY annee DESC")
                    res.update(r[0] for r in cur.fetchall())
            except Exception:
                pass
            finally:
                conn.close()
    return sorted(res, reverse=True)


def supprimer(annee: int):
    if backend() == "postgres":
        conn = _get_conn()
        if conn is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM challenge_saisons WHERE annee=%s", (annee,))
            finally:
                conn.close()
    try:
        os.remove(_fichier(annee))
    except Exception:
        pass


def info_backend() -> dict:
    """Pour l'affichage dans l'UI."""
    b = backend()
    return {
        "backend": b,
        "configure": bool(_db_url()),
        "libelle": ("Base Postgres (durable)" if b == "postgres"
                    else "Fichiers locaux (éphémère sur Streamlit Cloud)"),
    }
