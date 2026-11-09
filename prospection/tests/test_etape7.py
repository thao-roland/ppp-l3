"""Tests : vraies réponses et automatiques dans le tableau, le score et les exports.

Tous les prospects sont inventés.
"""

import csv
import io
from datetime import date, timedelta

import pytest
from openpyxl import load_workbook

import analyse
import exports
import exports_excel
import modeles
import scoring
import tableau
from conftest import formulaire_valide


def prospect(**changements):
    valeurs = {"id": 1, "code": "P001", "statut": "a répondu", "interet": "aucun",
               "date_reponse": "2026-10-06", "date_premier_message": "2026-10-05",
               "version_message": "A", "canal": "Messenger", "dates_estimees": 0,
               "reponse_automatique": None, "a_deja_site": None}
    valeurs.update(changements)
    return valeurs


def marquer(conn, code, valeur):
    modeles.corriger(conn, modeles.obtenir(conn, code)["id"], "reponse_automatique", valeur)


# --- Tableau et analyse ---------------------------------------------------------
@pytest.mark.parametrize("changements, attendu", [
    ({"reponse_automatique": "non"}, "vraie"),
    ({"reponse_automatique": None}, "vraie"),
    ({"reponse_automatique": "oui"}, "automatique"),
    ({"reponse_automatique": "à vérifier"}, "a_verifier"),
    ({"reponse_automatique": "oui", "interet": "curieux"}, "vraie"),
    ({"reponse_automatique": "à vérifier", "statut": "signé"}, "vraie"),
    ({"reponse_automatique": "non", "interet": "à vérifier"}, "vraie"),
    ({"date_reponse": None, "statut": "contacté"}, "aucune"),
])
def test_categorie_de_reponse(changements, attendu):
    assert tableau.categorie_reponse(prospect(**changements)) == attendu


def test_interet_a_verifier_n_est_pas_un_interesse():
    assert tableau.est_interesse(prospect(interet="à vérifier")) is False


def groupe_mixte():
    return [prospect(reponse_automatique="non"), prospect(reponse_automatique="oui"),
            prospect(reponse_automatique="à vérifier"), prospect(date_reponse=None, statut="contacté")]


def test_le_taux_ne_compte_que_les_vraies_reponses():
    resultat = tableau.bilan(groupe_mixte())
    assert (resultat["reponses"], resultat["automatiques"], resultat["a_verifier"],
            resultat["sans_reponse"]) == (1, 1, 1, 1)
    assert resultat["taux_reponse"] == 25.0


def test_wilson_sur_les_vraies_reponses():
    ligne = analyse.construire(groupe_mixte())["total"]
    assert (ligne["reponses"], ligne["contacts"]) == (1, 4)


def test_graphique_a_trois_couches():
    barres = tableau.graphique_semaines(tableau.par_semaine(groupe_mixte()))["barres"]
    assert [s["classe"] for s in barres[0]["segments"]] == ["serie-reponse", "serie-auto", "serie-sans"]


@pytest.mark.parametrize("adresse", ["/tableau", "/analyse"])
def test_pages_montrent_les_automatiques(client, conn, adresse):
    client.post("/prospects/nouveau", data=formulaire_valide(date_reponse="2026-10-03"))
    marquer(conn, "P001", "oui")
    page = client.get(adresse).get_data(as_text=True)
    assert "Réponses automatiques" in page and "Taux de vraies réponses" in page


def test_correction_sur_la_fiche(client, conn):
    client.post("/prospects/nouveau", data=formulaire_valide(date_reponse="2026-10-03"))
    client.post("/prospects/P001/modifier", data=formulaire_valide(
        date_reponse="2026-10-03", reponse_automatique="à vérifier"))
    assert modeles.obtenir(conn, "P001")["reponse_automatique"] == "à vérifier"


def test_fiche_refuse_une_valeur_inconnue(client):
    client.post("/prospects/nouveau", data=formulaire_valide())
    assert client.post("/prospects/P001/modifier", data=formulaire_valide(
        reponse_automatique="peut-être")).status_code == 400


# --- Score et relances : une réponse automatique n'est pas une réponse ----------
JOUR = date(2026, 11, 8)


def il_y_a(jours):
    return (JOUR - timedelta(days=jours)).isoformat()


def ancien(**changements):
    """Prospect dont tous les échanges sont anciens : score de base 10 (site inconnu)."""
    return prospect(date_premier_message=il_y_a(60), date_reponse=il_y_a(50), **changements)


@pytest.fixture
def regles():
    return scoring.charger_regles()


def score_de(regles, fiche_prospect, relances=()):
    return scoring.calculer_score(fiche_prospect, list(relances), regles, JOUR)


@pytest.mark.parametrize("marque, attendu", [(None, 40), ("non", 40), ("oui", 10), ("à vérifier", 10)])
def test_points_de_reponse_selon_la_detection(regles, marque, attendu):
    assert score_de(regles, ancien(reponse_automatique=marque)) == attendu


def test_interesse_garde_ses_points_meme_si_automatique(regles):
    assert score_de(regles, ancien(reponse_automatique="oui", interet="curieux")) == 60


def test_interet_a_verifier_ne_donne_pas_de_points(regles):
    assert score_de(regles, ancien(reponse_automatique="non", interet="à vérifier")) == 40


def test_une_reponse_automatique_recente_ne_donne_pas_le_bonus(regles):
    automatique = prospect(date_premier_message=il_y_a(60), date_reponse=il_y_a(3), reponse_automatique="oui")
    vraie = prospect(date_premier_message=il_y_a(60), date_reponse=il_y_a(3), reponse_automatique="non")
    assert (score_de(regles, automatique), score_de(regles, vraie)) == (10, 50)


def test_relance_avant_une_reponse_automatique_reste_sans_reponse(regles):
    assert score_de(regles, ancien(reponse_automatique="oui"), [il_y_a(55)]) == 5


def test_relance_avant_une_vraie_reponse_sans_malus(regles):
    assert score_de(regles, ancien(reponse_automatique="non"), [il_y_a(55)]) == 40


def a_relancer(regles, fiche_prospect, relances=()):
    return scoring.a_relancer([fiche_prospect], {1: list(relances)}, regles, JOUR)


@pytest.mark.parametrize("marque, nombre", [("oui", 1), ("à vérifier", 1), ("non", 0), (None, 0)])
def test_liste_des_relances_selon_la_detection(regles, marque, nombre):
    assert len(a_relancer(regles, ancien(reponse_automatique=marque))) == nombre


def test_attente_comptee_depuis_mon_message_pas_la_reponse_automatique(regles):
    ligne = a_relancer(regles, ancien(reponse_automatique="oui"))[0]
    assert ligne["jours_sans_reponse"] == 60


def test_interesse_apres_reponse_automatique_pas_a_relancer(regles):
    assert a_relancer(regles, ancien(reponse_automatique="oui", interet="curieux")) == []


def test_on_arrete_apres_2_relances_meme_avec_reponse_automatique(regles):
    fiche_auto = ancien(reponse_automatique="oui")
    assert a_relancer(regles, fiche_auto, [il_y_a(55), il_y_a(45)]) == []


# --- CSV ------------------------------------------------------------------------
def ligne_csv(relances=None, **changements):
    return next(csv.DictReader(io.StringIO(
        exports.csv_anonymise([prospect(**changements)], relances or {}))))


def test_nouvelles_colonnes():
    ligne = ligne_csv({1: ["2026-10-07", "2026-10-09"]}, reponse_automatique="oui", a_deja_site=0)
    assert (ligne["nb_relances"], ligne["reponse_automatique"], ligne["a_deja_site"]) == ("2", "oui", "non")


@pytest.mark.parametrize("valeur, attendu", [(1, "oui"), (0, "non"), (None, "inconnu")])
def test_a_deja_site(valeur, attendu):
    assert ligne_csv(a_deja_site=valeur)["a_deja_site"] == attendu


@pytest.mark.parametrize("marque, attendu", [("oui", "automatique"), ("à vérifier", "à vérifier"), ("non", "réponse")])
def test_type_de_reponse_suit_la_detection(marque, attendu):
    assert ligne_csv(reponse_automatique=marque)["type_reponse"] == attendu


def test_les_dates_de_relances_ne_sortent_pas():
    texte = exports.csv_anonymise([prospect()], {1: ["2026-10-17"]})
    assert "2026-10-17" not in texte


# --- Excel : valeurs calculées en plus des formules -----------------------------
def classeur(prospects):
    contenu = exports_excel.classeur(prospects, None, None)
    return load_workbook(io.BytesIO(contenu)), load_workbook(io.BytesIO(contenu), data_only=True)


def test_formule_et_valeur_dans_la_meme_cellule():
    formules, valeurs = classeur(groupe_mixte())
    assert formules["Canaux"]["D2"].value.startswith("=IF(")
    assert valeurs["Canaux"]["D2"].value == pytest.approx(0.25)


def test_valeurs_de_wilson_calculees():
    _, valeurs = classeur(groupe_mixte())
    bas, haut = analyse.wilson(1, 4)
    assert valeurs["Canaux"]["E2"].value == pytest.approx(bas)
    assert valeurs["Canaux"]["F2"].value == pytest.approx(haut)


def test_valeurs_du_resume_calculees():
    _, valeurs = classeur(groupe_mixte())
    feuille = valeurs["Résumé"]
    assert feuille["B7"].value == pytest.approx(0.25)
    assert (feuille["B10"].value, feuille["B11"].value) == (1, 1)


def test_aucune_formule_sans_valeur():
    formules, valeurs = classeur(groupe_mixte() + [prospect(version_message="B")])
    for feuille in formules.worksheets:
        for ligne in feuille.iter_rows():
            for cellule in ligne:
                if isinstance(cellule.value, str) and cellule.value.startswith("="):
                    assert valeurs[feuille.title][cellule.coordinate].value is not None


def test_groupe_sans_contact_cellule_vide_sans_erreur():
    _, valeurs = classeur([prospect(version_message="A")])
    assert valeurs["Versions AB"]["D3"].value in (None, "")


def test_excel_a_trois_series_par_semaine():
    formules, _ = classeur(groupe_mixte())
    assert len(formules["Semaines"]._charts[0].series) == 3
