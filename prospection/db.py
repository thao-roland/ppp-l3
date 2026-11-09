"""Base SQLite et dossier de données.

RÈGLE : toutes les données réelles (base, exports Facebook, exports privés)
vivent DANS UN DOSSIER SÉPARÉ, EN DEHORS du dépôt git. Le dépôt ne contient
que le code, les tests (avec de fausses données), la doc et les CSV anonymisés.
"""

import os
import shutil
import sqlite3
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent      # prospection/
RACINE_DEPOT = DOSSIER.parent.resolve()        # racine du dépôt (ppp-l3/)

# Par défaut : un dossier « crm-donnees » à côté du dépôt (jamais un chemin
# personnel écrit en dur). On peut le changer avec la variable CRM_DONNEES.
DONNEES_PAR_DEFAUT = "../crm-donnees"
NOM_BASE = "crm.db"
SOUS_DOSSIERS = ("exports_facebook", "exports_prives")

# Emplacement de la base de l'étape 1 (dans le dépôt, ignorée par git).
ANCIENNE_BASE = DOSSIER / "data" / "prospection.db"


def dossier_donnees(valeur=None):
    """Dossier des données réelles. Un chemin relatif part de la racine du dépôt."""
    brut = valeur or os.environ.get("CRM_DONNEES") or DONNEES_PAR_DEFAUT
    return (RACINE_DEPOT / Path(brut).expanduser()).resolve()


def verifier_hors_depot(dossier):
    """Refuse un dossier de données situé dans le dépôt (risque de commit)."""
    dossier = Path(dossier).resolve()
    if dossier == RACINE_DEPOT or RACINE_DEPOT in dossier.parents:
        raise RuntimeError(
            "Le dossier de données doit être EN DEHORS du dépôt git. "
            "Change la variable d'environnement CRM_DONNEES."
        )


def preparer_dossier(dossier):
    """Crée le dossier de données et ses sous-dossiers (accès réservé à moi)."""
    verifier_hors_depot(dossier)
    dossier = Path(dossier)
    for sous in ("",) + SOUS_DOSSIERS:
        (dossier / sous).mkdir(parents=True, exist_ok=True)
    try:
        dossier.chmod(0o700)  # sans effet sous Windows
    except OSError:
        pass
    return dossier


def chemin_base(dossier):
    """Chemin du fichier de base dans le dossier de données."""
    return Path(dossier) / NOM_BASE


def migrer_ancienne_base(ancienne, dossier):
    """Déplace la base de l'étape 1 vers le dossier de données (une seule fois).

    Renvoie True si une base a été déplacée. Ne touche à rien si la nouvelle
    base existe déjà (on n'écrase jamais de données).
    """
    ancienne, nouvelle = Path(ancienne), chemin_base(dossier)
    if not ancienne.is_file() or nouvelle.exists():
        return False
    shutil.move(str(ancienne), str(nouvelle))
    return True


def connecter(chemin):
    """Ouvre la base SQLite."""
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row  # accès aux colonnes par leur nom
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite l'ignore par défaut
    return conn


def initialiser(conn):
    """Crée les tables si besoin et met à niveau une base plus ancienne."""
    schema = (DOSSIER / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    _migrer(conn)
    conn.commit()


def _migrer(conn):
    """Ajoute ce qui manque à une base créée par une étape précédente."""
    colonnes = {l["name"] for l in conn.execute("PRAGMA table_info(prospects)")}
    if "conversation_fb" not in colonnes:
        conn.execute("ALTER TABLE prospects ADD COLUMN conversation_fb TEXT")
    if "reponse_automatique" not in colonnes:
        conn.execute("ALTER TABLE prospects ADD COLUMN reponse_automatique TEXT")
    # Une conversation Facebook ne peut donner qu'un seul prospect.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_prospects_conversation_fb "
        "ON prospects(conversation_fb)"
    )
