"""Connexion à la base SQLite. Tout reste en local, dans un simple fichier."""

import os
import sqlite3
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent

# Fichier de la base : dans data/, ignoré par git (voir .gitignore).
# On peut le changer avec la variable d'environnement PROSPECTION_DB.
CHEMIN_PAR_DEFAUT = DOSSIER / "data" / "prospection.db"


def chemin_base():
    """Renvoie le chemin du fichier de base à utiliser."""
    return Path(os.environ.get("PROSPECTION_DB", CHEMIN_PAR_DEFAUT))


def connecter(chemin=None):
    """Ouvre la base (et crée le dossier si besoin)."""
    chemin = Path(chemin) if chemin else chemin_base()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row  # accès aux colonnes par leur nom
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite l'ignore par défaut
    return conn


def initialiser(conn):
    """Crée les tables si elles n'existent pas encore."""
    schema = (DOSSIER / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()
