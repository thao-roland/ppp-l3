"""Tests de l'étape 4 : tableau de bord (données fictives uniquement)."""

import re

import pytest

import importation
import modeles
import tableau
from conftest import FAUX_EXPORT, formulaire_valide


def prospect(**changements):
    """Prospect fictif contacté, sans réponse."""
    valeurs = {"statut": "contacté", "interet": "aucun", "date_reponse": None,
               "date_premier_message": "2026-10-05", "version_message": "A",
               "canal": "Messenger", "dates_estimees": 0}
    valeurs.update(changements)
    return valeurs


# --- Définitions -------------------------------------------------------------
@pytest.mark.parametrize("changements, attendu", [
    ({}, False),
    ({"date_reponse": "2026-10-06"}, True),
    ({"statut": "a répondu"}, True),
    ({"statut": "intéressé"}, True),
    ({"statut": "signé"}, True),
    ({"interet": "curieux"}, True),
    ({"statut": "perdu"}, False),
    ({"statut": "relancé"}, False),
])
def test_a_repondu(changements, attendu):
    assert tableau.a_repondu(prospect(**changements)) is attendu


@pytest.mark.parametrize("changements, attendu", [
    ({}, False),
    ({"date_reponse": "2026-10-06"}, False),
    ({"interet": "curieux"}, True),
    ({"interet": "demande de prix"}, True),
    ({"statut": "intéressé"}, True),
    ({"statut": "signé"}, True),
])
def test_est_interesse(changements, attendu):
    assert tableau.est_interesse(prospect(**changements)) is attendu


def test_taux_sans_personne_est_none_pas_zero():
    assert tableau.taux(0, 0) is None


def test_taux_arrondi():
    assert tableau.taux(1, 3) == 33.3


@pytest.mark.parametrize("valeur, attendu", [(46.9, "46,9 %"), (0.0, "0,0 %"), (None, "—")])
def test_format_pourcent(valeur, attendu):
    assert tableau.format_pourcent(valeur) == attendu


def test_bilan():
    groupe = [prospect(), prospect(date_reponse="2026-10-06"),
              prospect(date_reponse="2026-10-06", interet="curieux"), prospect(statut="signé")]
    assert tableau.bilan(groupe) == {
        "contacts": 4, "reponses": 3, "interesses": 2, "signes": 1,
        "taux_reponse": 75.0, "taux_interet": 50.0, "taux_signature": 25.0}


def test_bilan_vide():
    resultat = tableau.bilan([])
    assert resultat["contacts"] == 0 and resultat["taux_reponse"] is None


# --- Comparaisons ------------------------------------------------------------
def test_versions_a_et_b_toujours_presentes():
    lignes = tableau.comparer_versions([prospect()])
    assert [l["libelle"] for l in lignes] == ["A", "B"]
    assert lignes[1]["contacts"] == 0 and lignes[1]["taux_reponse"] is None


def test_versions_comptees_separement():
    groupe = [prospect(version_message="A", date_reponse="2026-10-06"),
              prospect(version_message="B"), prospect(version_message="B")]
    a, b = tableau.comparer_versions(groupe)
    assert (a["contacts"], a["taux_reponse"]) == (1, 100.0)
    assert (b["contacts"], b["taux_reponse"]) == (2, 0.0)


def test_version_vide_ligne_a_part():
    lignes = tableau.comparer_versions([prospect(version_message=None)])
    assert lignes[-1]["libelle"] == tableau.NON_RENSEIGNE
    assert lignes[-1]["contacts"] == 1


def test_canaux_tries_et_vide_a_la_fin():
    groupe = [prospect(canal=None), prospect(canal=None), prospect(canal=None),
              prospect(canal="Instagram"), prospect(canal="Messenger"), prospect(canal="Messenger")]
    assert [l["libelle"] for l in tableau.comparer_canaux(groupe)] == [
        "Messenger", "Instagram", tableau.NON_RENSEIGNE]


# --- Semaines ----------------------------------------------------------------
def test_semaine_commence_le_lundi():
    groupe = [prospect(date_premier_message="2026-10-05"), prospect(date_premier_message="2026-10-11")]
    semaines = tableau.par_semaine(groupe)
    assert [(s["lundi"], s["contacts"]) for s in semaines] == [("2026-10-05", 2)]


def test_dimanche_et_lundi_dans_deux_semaines():
    groupe = [prospect(date_premier_message="2026-10-11"), prospect(date_premier_message="2026-10-12")]
    assert [s["lundi"] for s in tableau.par_semaine(groupe)] == ["2026-10-05", "2026-10-12"]


def test_semaines_vides_gardees():
    groupe = [prospect(date_premier_message="2026-10-05"), prospect(date_premier_message="2026-10-26")]
    semaines = tableau.par_semaine(groupe)
    assert [s["contacts"] for s in semaines] == [1, 0, 0, 1]


def test_passage_d_annee():
    groupe = [prospect(date_premier_message="2025-12-29"), prospect(date_premier_message="2026-01-05")]
    assert [s["lundi"] for s in tableau.par_semaine(groupe)] == ["2025-12-29", "2026-01-05"]


def test_reponse_rattachee_a_la_semaine_du_premier_message():
    semaines = tableau.par_semaine([prospect(date_reponse="2026-11-02")])
    assert [(s["lundi"], s["reponses"]) for s in semaines] == [("2026-10-05", 1)]


def test_sans_date_exclu_des_semaines():
    assert tableau.par_semaine([prospect(date_premier_message=None)]) == []


# --- Graphique ---------------------------------------------------------------
@pytest.mark.parametrize("maximum, pas", [(1, 1), (4, 1), (7, 2), (20, 5), (21, 10), (205, 100)])
def test_pas_de_graduation(maximum, pas):
    assert tableau._pas_graduation(maximum) == pas


def test_graphique_sans_donnees():
    assert tableau.graphique_semaines([]) is None


def semaines_exemple():
    return tableau.par_semaine([
        prospect(date_premier_message="2026-10-05", date_reponse="2026-10-06"),
        prospect(date_premier_message="2026-10-05"),
        prospect(date_premier_message="2026-10-19"),
    ])


def test_une_barre_par_semaine():
    assert len(tableau.graphique_semaines(semaines_exemple())["barres"]) == 3


def test_segments_selon_les_reponses():
    barres = tableau.graphique_semaines(semaines_exemple())["barres"]
    assert [s["classe"] for s in barres[0]["segments"]] == ["serie-reponse", "serie-sans"]
    assert barres[1]["segments"] == []
    assert [s["classe"] for s in barres[2]["segments"]] == ["serie-sans"]


def test_titre_de_barre_ne_contient_que_des_chiffres():
    titre = tableau.graphique_semaines(semaines_exemple())["barres"][0]["titre"]
    assert titre == "Semaine du 05/10/2026 : 2 contacts, 1 réponse (50,0 %)"


def test_graduations_de_zero_au_plafond():
    graduations = tableau.graphique_semaines(semaines_exemple())["graduations"]
    assert [g["valeur"] for g in graduations] == [0, 1, 2]


def test_barres_jamais_plus_de_24_de_large():
    semaines = tableau.par_semaine([prospect()])  # une seule barre : la place ne manque pas
    chemin = tableau.graphique_semaines(semaines)["barres"][0]["segments"][0]["chemin"]
    gauche, droite = map(float, re.findall(r"Q([\d.]+)", chemin))
    assert droite - gauche == 24


def test_etiquettes_limitees():
    groupe = [prospect(date_premier_message=f"2026-{m:02d}-15") for m in range(1, 13)]
    barres = tableau.graphique_semaines(tableau.par_semaine(groupe))["barres"]
    assert sum(b["etiquette"] is not None for b in barres) <= tableau.MAX_ETIQUETTES


# --- La page -----------------------------------------------------------------
def test_page_vide(client):
    reponse = client.get("/tableau")
    assert reponse.status_code == 200
    assert "Aucun prospect pour l'instant" in reponse.get_data(as_text=True)


def test_lien_dans_l_entete(client):
    assert 'href="/tableau"' in client.get("/").get_data(as_text=True)


def test_page_avec_chiffres(client):
    client.post("/prospects/nouveau", data=formulaire_valide(date_reponse="2026-10-03"))
    client.post("/prospects/nouveau", data=formulaire_valide(version_message="B"))
    page = client.get("/tableau").get_data(as_text=True)
    assert "50,0 %" in page
    assert "1 sur 2" in page
    assert "<svg" in page


def test_message_si_aucune_version(client):
    client.post("/prospects/nouveau", data=formulaire_valide(version_message=""))
    assert "Aucune version renseignée" in client.get("/tableau").get_data(as_text=True)


def test_prudence_affichee_si_versions(client):
    client.post("/prospects/nouveau", data=formulaire_valide())
    assert "ne prouve rien" in client.get("/tableau").get_data(as_text=True)


def test_dates_estimees_signalees(client):
    client.post("/prospects/nouveau", data=formulaire_valide(dates_estimees="1"))
    assert "1 prospect(s) ont des dates estimées" in client.get("/tableau").get_data(as_text=True)


def test_prospect_sans_date_signale(client):
    client.post("/prospects/nouveau", data=formulaire_valide(date_premier_message=""))
    page = client.get("/tableau").get_data(as_text=True)
    assert "1 prospect(s) sans date" in page
    assert "Aucun prospect n'a de date" in page


def test_la_page_ne_montre_aucun_nom_ni_message(client, conn):
    importation.importer(conn, FAUX_EXPORT)
    page = client.get("/tableau").get_data(as_text=True)
    prospects = modeles.lister(conn)
    assert prospects
    for p in prospects:
        assert p["nom_entreprise"] not in page
        assert not p["texte_envoye"] or p["texte_envoye"] not in page
