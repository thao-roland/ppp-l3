"""Tests : les données réelles restent EN DEHORS du dépôt git."""

import sqlite3

import pytest

import db


def test_dossier_par_defaut_est_a_cote_du_depot(monkeypatch):
    monkeypatch.delenv("CRM_DONNEES", raising=False)
    assert db.dossier_donnees() == (db.RACINE_DEPOT.parent / "crm-donnees").resolve()


def test_variable_d_environnement_utilisee(monkeypatch, tmp_path):
    monkeypatch.setenv("CRM_DONNEES", str(tmp_path / "ailleurs"))
    assert db.dossier_donnees() == (tmp_path / "ailleurs").resolve()


def test_chemin_relatif_part_de_la_racine_du_depot(monkeypatch):
    monkeypatch.setenv("CRM_DONNEES", "../autre-dossier")
    assert db.dossier_donnees() == (db.RACINE_DEPOT.parent / "autre-dossier").resolve()


def test_dossier_dans_le_depot_refuse(monkeypatch):
    for dedans in (db.RACINE_DEPOT, db.RACINE_DEPOT / "prospection" / "data"):
        with pytest.raises(RuntimeError):
            db.verifier_hors_depot(dedans)
    with pytest.raises(RuntimeError):
        db.preparer_dossier(db.RACINE_DEPOT / "crm-donnees")


def test_dossier_hors_depot_accepte(tmp_path):
    db.verifier_hors_depot(tmp_path / "crm-donnees")  # ne lève rien


def test_preparer_cree_les_sous_dossiers(tmp_path):
    dossier = db.preparer_dossier(tmp_path / "crm-donnees")
    assert (dossier / "exports_facebook").is_dir()
    assert (dossier / "exports_prives").is_dir()


def test_la_base_est_creee_dans_le_dossier_de_donnees(client, dossier_donnees):
    assert (dossier_donnees / "crm.db").is_file()


# --- Déplacement de la base de l'étape 1 -------------------------------------
def _creer_ancienne_base(chemin):
    """Base de l'étape 1 : pas encore de colonne conversation_fb."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.execute("CREATE TABLE prospects (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "code TEXT NOT NULL UNIQUE, nom_entreprise TEXT NOT NULL)")
    conn.execute("INSERT INTO prospects (code, nom_entreprise) VALUES ('P001', 'Fictif')")
    conn.commit()
    conn.close()


def test_ancienne_base_deplacee_une_seule_fois(tmp_path):
    ancienne = tmp_path / "depot" / "data" / "prospection.db"
    _creer_ancienne_base(ancienne)
    dossier = db.preparer_dossier(tmp_path / "crm-donnees")
    assert db.migrer_ancienne_base(ancienne, dossier) is True
    assert not ancienne.exists() and db.chemin_base(dossier).is_file()
    assert db.migrer_ancienne_base(ancienne, dossier) is False


def test_une_base_existante_n_est_jamais_ecrasee(tmp_path):
    ancienne = tmp_path / "depot" / "data" / "prospection.db"
    _creer_ancienne_base(ancienne)
    dossier = db.preparer_dossier(tmp_path / "crm-donnees")
    db.chemin_base(dossier).write_bytes(b"deja la")
    assert db.migrer_ancienne_base(ancienne, dossier) is False
    assert ancienne.exists() and db.chemin_base(dossier).read_bytes() == b"deja la"


def test_initialiser_met_a_niveau_une_ancienne_base(tmp_path):
    chemin = tmp_path / "vieille.db"
    _creer_ancienne_base(chemin)
    conn = db.connecter(chemin)
    db.initialiser(conn)
    colonnes = {l["name"] for l in conn.execute("PRAGMA table_info(prospects)")}
    assert "conversation_fb" in colonnes
    assert conn.execute("SELECT nom_entreprise FROM prospects").fetchone()[0] == "Fictif"
    conn.close()
