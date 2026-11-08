"""Outils communs aux tests : une base temporaire jetable pour chaque test."""

from pathlib import Path

import pytest

import db
from app import create_app


FAUX_EXPORT = Path(__file__).parent / "faux_export_facebook"


@pytest.fixture
def dossier_donnees(tmp_path):
    """Faux dossier de données : temporaire, donc jamais dans le dépôt."""
    return tmp_path / "crm-donnees"


@pytest.fixture
def client(dossier_donnees):
    """Navigateur de test branché sur une base vide."""
    return create_app(dossier_donnees).test_client()


@pytest.fixture
def conn(dossier_donnees, client):
    """Connexion directe à la même base, pour vérifier ce qui est enregistré."""
    connexion = db.connecter(db.chemin_base(dossier_donnees))
    yield connexion
    connexion.close()


def formulaire_valide(**changements):
    """Un formulaire correct (données fictives) que chaque test peut modifier."""
    donnees = {
        "nom_entreprise": "Boulangerie Test",
        "metier": "boulanger",
        "ville": "Valenciennes",
        "canal": "Messenger",
        "date_premier_message": "2026-10-01",
        "version_message": "A",
        "texte_envoye": "Bonjour, je crée des sites web...",
        "interet": "aucun",
        "statut": "contacté",
    }
    donnees.update(changements)
    return donnees
