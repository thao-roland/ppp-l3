"""Tests de l'étape 6 : CSV anonymisé et Excel (données fictives uniquement)."""

import csv
import io

import pytest
from openpyxl import load_workbook

import exports
import exports_excel
import importation
import modeles
from conftest import FAUX_EXPORT, formulaire_valide


def prospect(**changements):
    """Prospect fictif, avec tous les champs sensibles remplis."""
    valeurs = {"code": "P001", "nom_entreprise": "Nom Fictif Secret", "texte_envoye": "Texte fictif secret",
               "conversation_fb": "999888777", "ville": "Ville Fictive", "metier": "métier fictif",
               "date_premier_message": "2026-10-05", "date_reponse": None, "dates_estimees": 0,
               "canal": "Messenger", "version_message": "A", "interet": "aucun", "statut": "contacté",
               "tarif_propose": 1234, "acompte": 567}
    valeurs.update(changements)
    return valeurs


def lire_csv(texte):
    return list(csv.DictReader(io.StringIO(texte)))


# --- La période ---------------------------------------------------------------
@pytest.mark.parametrize("valeurs, attendu", [
    ({}, (None, None, None)),
    ({"debut": "2026-01-01", "fin": "2026-02-01"}, ("2026-01-01", "2026-02-01", None)),
    ({"debut": " 2026-01-01 ", "fin": ""}, ("2026-01-01", None, None)),
    ({"debut": "2026-01-01", "fin": "2026-01-01"}, ("2026-01-01", "2026-01-01", None)),
])
def test_periode_valide(valeurs, attendu):
    assert exports.lire_periode(valeurs) == attendu


@pytest.mark.parametrize("valeurs", [{"debut": "n'importe quoi"}, {"fin": "2026-13-40"},
                                     {"debut": "2026-02-01", "fin": "2026-01-01"}])
def test_periode_invalide(valeurs):
    assert exports.lire_periode(valeurs)[2] is not None


def test_filtre_bornes_comprises():
    groupe = [prospect(code=c, date_premier_message=d) for c, d in
              [("P1", "2026-09-30"), ("P2", "2026-10-01"), ("P3", "2026-10-31"), ("P4", "2026-11-01")]]
    assert [p["code"] for p in exports.filtrer(groupe, "2026-10-01", "2026-10-31")] == ["P2", "P3"]


def test_filtre_ouvert_d_un_cote():
    groupe = [prospect(code="P1", date_premier_message="2026-01-01"),
              prospect(code="P2", date_premier_message="2026-12-01")]
    assert [p["code"] for p in exports.filtrer(groupe, "2026-06-01", None)] == ["P2"]
    assert [p["code"] for p in exports.filtrer(groupe, None, "2026-06-01")] == ["P1"]


def test_sans_periode_on_garde_les_prospects_sans_date():
    assert len(exports.filtrer([prospect(date_premier_message=None)], None, None)) == 1


def test_avec_periode_un_prospect_sans_date_est_ecarte():
    assert exports.filtrer([prospect(date_premier_message=None)], "2026-01-01", None) == []


@pytest.mark.parametrize("debut, fin, attendu", [
    ("2026-05-01", "2026-08-31", "x_2026-05-01_2026-08-31.csv"),
    (None, None, "x_debut_fin.csv"),
])
def test_nom_de_fichier(debut, fin, attendu):
    assert exports.nom_fichier("x", debut, fin, "csv") == attendu


# --- Le CSV -------------------------------------------------------------------
@pytest.mark.parametrize("changements, attendu", [
    ({}, "aucune"),
    ({"statut": "perdu"}, "aucune"),
    ({"date_reponse": "2026-10-06"}, "réponse"),
    ({"date_reponse": "2026-10-06", "statut": "perdu"}, "réponse"),
    ({"interet": "curieux"}, "intéressé"),
    ({"interet": "demande de prix"}, "intéressé"),
    ({"statut": "signé"}, "signé"),
])
def test_type_de_reponse(changements, attendu):
    assert exports.type_reponse(prospect(**changements)) == attendu


def test_colonnes_exactes():
    premiere_ligne = exports.csv_anonymise([prospect()]).splitlines()[0]
    assert premiere_ligne == ("code,date_premier_message,date_reponse,dates_estimees,"
                              "canal,version_message,type_reponse,interet,statut")


def test_contenu_d_une_ligne():
    assert lire_csv(exports.csv_anonymise([prospect(date_reponse="2026-10-06", dates_estimees=1)]))[0] == {
        "code": "P001", "date_premier_message": "2026-10-05", "date_reponse": "2026-10-06",
        "dates_estimees": "oui", "canal": "Messenger", "version_message": "A",
        "type_reponse": "réponse", "interet": "aucun", "statut": "contacté"}


@pytest.mark.parametrize("secret", ["Nom Fictif Secret", "Texte fictif secret", "999888777",
                                    "Ville Fictive", "métier fictif", "1234", "567"])
def test_aucun_champ_sensible(secret):
    assert secret not in exports.csv_anonymise([prospect()])


def test_tri_par_date_puis_code():
    groupe = [prospect(code="P3", date_premier_message="2026-10-06"),
              prospect(code="P2", date_premier_message="2026-10-05"),
              prospect(code="P1", date_premier_message="2026-10-05")]
    assert [l["code"] for l in lire_csv(exports.csv_anonymise(groupe))] == ["P1", "P2", "P3"]


def test_csv_vide_garde_l_entete():
    assert exports.csv_anonymise([]).count("\n") == 1


# --- L'Excel ------------------------------------------------------------------
def ouvrir(contenu):
    return load_workbook(io.BytesIO(contenu))


def valeurs(fichier):
    for feuille in fichier.worksheets:
        for ligne in feuille.iter_rows():
            for cellule in ligne:
                if cellule.value is not None:
                    yield cellule


def exemple():
    return [prospect(version_message="A", date_reponse="2026-10-06"),
            prospect(version_message="B", date_premier_message="2026-10-20"),
            prospect(version_message=None, canal="Instagram")]


def test_quatre_feuilles():
    assert ouvrir(exports_excel.classeur(exemple(), None, None)).sheetnames == [
        "Résumé", "Semaines", "Versions AB", "Canaux"]


def test_chiffres_du_resume():
    feuille = ouvrir(exports_excel.classeur(exemple(), None, None))["Résumé"]
    assert (feuille["A5"].value, feuille["B5"].value) == ("Contacts", 3)
    assert (feuille["A6"].value, feuille["B6"].value) == ("Réponses", 1)


def test_le_taux_est_une_formule():
    feuille = ouvrir(exports_excel.classeur(exemple(), None, None))["Canaux"]
    assert feuille["D2"].value == '=IF(B2=0,"",C2/B2)'
    assert feuille["D2"].number_format == "0.0%"


def test_wilson_est_une_formule_liee_a_z():
    feuille = ouvrir(exports_excel.classeur(exemple(), None, None))["Canaux"]
    assert "SQRT" in feuille["E2"].value and "'Résumé'!$B$4" in feuille["E2"].value
    assert feuille["E2"].value.startswith('=IF(B2=0,"",MAX(0,')
    assert 'MIN(1,' in feuille["F2"].value


def test_z_a_la_bonne_place():
    feuille = ouvrir(exports_excel.classeur(exemple(), None, None))["Résumé"]
    assert feuille["A4"].value.startswith("z ") and feuille["B4"].value == pytest.approx(1.959964)


def test_periode_ecrite_dans_le_resume():
    feuille = ouvrir(exports_excel.classeur([], "2026-05-01", "2026-08-31"))["Résumé"]
    assert feuille["B3"].value == "du 2026-05-01 au 2026-08-31"


def test_police_arial_partout():
    fichier = ouvrir(exports_excel.classeur(exemple(), None, None))
    assert {c.font.name for c in valeurs(fichier)} == {"Arial"}


def test_graphiques_presents():
    fichier = ouvrir(exports_excel.classeur(exemple(), None, None))
    assert [len(f._charts) for f in fichier.worksheets] == [0, 1, 1, 1]


def test_titre_et_legende_hors_du_trace():
    graphique = ouvrir(exports_excel.classeur(exemple(), None, None))["Semaines"]._charts[0]
    assert graphique.title.overlay is False
    assert graphique.y_axis.title.overlay is False
    assert (graphique.legend.position, graphique.legend.overlay) == ("t", False)


def test_une_seule_serie_sans_legende():
    assert ouvrir(exports_excel.classeur(exemple(), None, None))["Canaux"]._charts[0].legend is None


def test_pas_de_graphique_ab_sans_version():
    groupe = [prospect(version_message=None)]
    assert len(ouvrir(exports_excel.classeur(groupe, None, None))["Versions AB"]._charts) == 0


def test_excel_sans_aucun_prospect():
    fichier = ouvrir(exports_excel.classeur([], "2026-01-01", "2026-01-31"))
    assert fichier["Résumé"]["B5"].value == 0
    assert [len(f._charts) for f in fichier.worksheets] == [0, 0, 0, 0]


def test_trop_peu_ecrit_dans_l_excel():
    feuille = ouvrir(exports_excel.classeur(exemple(), None, None))["Versions AB"]
    assert feuille["K2"].value == "Trop peu de données pour conclure"


@pytest.mark.parametrize("secret", ["Nom Fictif Secret", "Texte fictif secret", "999888777", "P001"])
def test_excel_sans_donnee_individuelle(secret):
    fichier = ouvrir(exports_excel.classeur(exemple(), None, None))
    assert not any(secret in str(c.value) for c in valeurs(fichier))


# --- Les pages ----------------------------------------------------------------
def test_page_et_lien(client):
    page = client.get("/exports").get_data(as_text=True)
    assert 'href="/exports"' in page and "CSV anonymisé" in page


def test_telechargement_csv(client):
    client.post("/prospects/nouveau", data=formulaire_valide())
    reponse = client.get("/exports/anonymise.csv?debut=2026-10-01&fin=2026-10-31")
    assert reponse.status_code == 200
    assert reponse.mimetype == "text/csv"
    assert 'filename="prospection_anonymise_2026-10-01_2026-10-31.csv"' in reponse.headers["Content-Disposition"]
    assert reponse.headers["Cache-Control"] == "no-store"
    assert [l["code"] for l in lire_csv(reponse.get_data(as_text=True))] == ["P001"]


def test_periode_appliquee_au_telechargement(client):
    client.post("/prospects/nouveau", data=formulaire_valide())
    texte = client.get("/exports/anonymise.csv?debut=2027-01-01").get_data(as_text=True)
    assert lire_csv(texte) == []


def test_telechargement_excel(client):
    client.post("/prospects/nouveau", data=formulaire_valide())
    reponse = client.get("/exports/rapport.xlsx")
    assert reponse.status_code == 200
    assert 'filename="prospection_rapport_debut_fin.xlsx"' in reponse.headers["Content-Disposition"]
    assert ouvrir(reponse.data)["Résumé"]["B5"].value == 1


@pytest.mark.parametrize("adresse", ["/exports/anonymise.csv", "/exports/rapport.xlsx"])
def test_periode_invalide_message_clair(client, adresse):
    reponse = client.get(f"{adresse}?debut=2026-02-01&fin=2026-01-01")
    assert reponse.status_code == 400
    assert "après la date de fin" in reponse.get_data(as_text=True)


def test_le_nom_de_fichier_ne_reprend_pas_la_saisie(client):
    reponse = client.get('/exports/anonymise.csv?debut=x"%0D%0AX-Pirate:1')
    assert reponse.status_code == 400
    assert "X-Pirate" not in reponse.headers


def test_vrai_faux_import_sans_nom_ni_message(client, conn):
    importation.importer(conn, FAUX_EXPORT)
    prospects = modeles.lister(conn)
    assert prospects
    texte = client.get("/exports/anonymise.csv").get_data(as_text=True)
    fichier = ouvrir(client.get("/exports/rapport.xlsx").data)
    contenu_excel = " ".join(str(c.value) for c in valeurs(fichier))
    assert len(lire_csv(texte)) == len(prospects)
    for p in prospects:
        for secret in (p["nom_entreprise"], p["texte_envoye"], p["conversation_fb"]):
            if secret:
                assert secret not in texte and secret not in contenu_excel
