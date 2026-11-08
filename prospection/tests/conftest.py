"""Outils communs aux tests : une base temporaire jetable pour chaque test."""

import pytest

import db
from app import create_app


@pytest.fixture
def chemin_base(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def client(chemin_base):
    """Navigateur de test branché sur une base vide."""
    return create_app(chemin_base).test_client()


@pytest.fixture
def conn(chemin_base, client):
    """Connexion directe à la même base, pour vérifier ce qui est enregistré."""
    connexion = db.connecter(chemin_base)
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
