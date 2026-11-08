"""Tests de l'étape 5 : Wilson, Fisher et conclusions (données fictives uniquement)."""

import pytest

import analyse
import importation
import modeles
import tableau
from conftest import FAUX_EXPORT, formulaire_valide


def ligne(contacts, reponses):
    """Une ligne de bilan fictive."""
    return {"libelle": "X", "contacts": contacts, "reponses": reponses,
            "taux_reponse": tableau.taux(reponses, contacts)}


# --- Wilson (valeurs de référence calculées à la main) -----------------------
@pytest.mark.parametrize("succes, total, bas, haut", [
    (8, 10, 0.4902, 0.9433),
    (0, 10, 0.0, 0.2775),
    (10, 10, 0.7225, 1.0),
    (1, 2, 0.0945, 0.9055),
])
def test_wilson_valeurs_connues(succes, total, bas, haut):
    resultat = analyse.wilson(succes, total)
    assert resultat == pytest.approx((bas, haut), abs=0.0001)


def test_wilson_sans_contact():
    assert analyse.wilson(0, 0) is None


@pytest.mark.parametrize("succes, total", [(0, 1), (1, 1), (3, 7), (50, 100), (199, 200)])
def test_wilson_contient_le_taux_et_reste_entre_0_et_1(succes, total):
    bas, haut = analyse.wilson(succes, total)
    assert 0 <= bas <= succes / total <= haut <= 1


def test_wilson_plus_etroit_avec_plus_de_contacts():
    petit, grand = analyse.wilson(5, 10), analyse.wilson(500, 1000)
    assert grand[1] - grand[0] < petit[1] - petit[0]


# --- Fisher (valeurs de référence) -------------------------------------------
@pytest.mark.parametrize("tableau_2x2, attendu", [
    ((3, 1, 1, 3), 0.4857142857),
    ((1, 9, 11, 3), 0.0027594562),
    ((8, 2, 1, 5), 0.0349650350),
    ((0, 5, 5, 0), 2 / 252),
    ((5, 5, 5, 5), 1.0),
])
def test_fisher_valeurs_connues(tableau_2x2, attendu):
    assert analyse.fisher_bilateral(*tableau_2x2) == pytest.approx(attendu, abs=1e-8)


def test_fisher_symetrique():
    assert analyse.fisher_bilateral(8, 2, 1, 5) == pytest.approx(analyse.fisher_bilateral(1, 5, 8, 2))


@pytest.mark.parametrize("cases", [(0, 0, 3, 2), (3, 2, 0, 0), (0, 0, 0, 0)])
def test_fisher_groupe_vide(cases):
    assert analyse.fisher_bilateral(*cases) is None


def test_fisher_grands_nombres():
    p = analyse.fisher_bilateral(600, 400, 500, 500)
    assert 0 < p < 0.001


def test_fisher_jamais_plus_de_1():
    assert analyse.fisher_bilateral(1, 1, 1, 1) <= 1.0


# --- Conclusions -------------------------------------------------------------
def test_aucun_contact_trop_peu():
    conclusion = analyse.conclure_ab(ligne(0, 0), ligne(0, 0))
    assert conclusion["niveau"] == "trop_peu"
    assert conclusion["p"] is None
    assert analyse.TROP_PEU in conclusion["texte"]


def test_seuil_29_contacts_trop_peu_meme_avec_un_gros_ecart():
    conclusion = analyse.conclure_ab(ligne(29, 28), ligne(100, 1))
    assert conclusion["niveau"] == "trop_peu"
    assert "A : 29, B : 100" in conclusion["texte"]


def test_seuil_verifie_sur_chaque_version():
    assert analyse.conclure_ab(ligne(100, 1), ligne(29, 28))["niveau"] == "trop_peu"


def test_30_contacts_suffisent():
    assert analyse.conclure_ab(ligne(30, 25), ligne(30, 5))["niveau"] == "significatif"


@pytest.mark.parametrize("a, b, gagnante", [
    (ligne(50, 40), ligne(50, 10), "A"),
    (ligne(50, 10), ligne(50, 40), "B"),
])
def test_ecart_significatif_nomme_la_bonne_version(a, b, gagnante):
    assert f"La version {gagnante}" in analyse.conclure_ab(a, b)["texte"]


def test_pas_de_difference_ne_dit_pas_qu_elles_se_valent():
    conclusion = analyse.conclure_ab(ligne(50, 20), ligne(50, 21))
    assert conclusion["niveau"] == "non_significatif"
    assert "ne prouve pas" in conclusion["texte"]


@pytest.mark.parametrize("valeur, attendu", [(0.0123, "0,012"), (0.0004, "moins de 0,001"), (1.0, "1,000")])
def test_format_p(valeur, attendu):
    assert analyse.format_p(valeur) == attendu


def test_avec_intervalle_en_pourcent():
    resultat = analyse.avec_intervalle(ligne(10, 8))
    assert (resultat["bas"], resultat["haut"]) == (49.0, 94.3)
    assert resultat["assez"] is False


def test_avec_intervalle_sans_contact():
    resultat = analyse.avec_intervalle(ligne(0, 0))
    assert resultat["bas"] is None and resultat["haut"] is None


def test_avec_intervalle_30_contacts_assez():
    assert analyse.avec_intervalle(ligne(30, 3))["assez"] is True


# --- La page -----------------------------------------------------------------
def test_page_vide(client):
    reponse = client.get("/analyse")
    assert reponse.status_code == 200
    assert "Aucun prospect pour l'instant" in reponse.get_data(as_text=True)


def test_lien_dans_l_entete(client):
    assert 'href="/analyse"' in client.get("/").get_data(as_text=True)


def test_trop_peu_affiche_clairement(client):
    client.post("/prospects/nouveau", data=formulaire_valide())
    page = client.get("/analyse").get_data(as_text=True)
    assert analyse.TROP_PEU in page
    assert "verdict-trop_peu" in page


def test_conclusion_significative_affichee(client):
    for numero in range(60):
        version = "A" if numero % 2 == 0 else "B"
        reponse = "2026-10-03" if version == "A" else ""
        client.post("/prospects/nouveau", data=formulaire_valide(version_message=version, date_reponse=reponse))
    page = client.get("/analyse").get_data(as_text=True)
    assert "La version A obtient plus de réponses" in page
    assert "moins de 0,001" in page


def test_lien_analyse_depuis_le_tableau(client):
    client.post("/prospects/nouveau", data=formulaire_valide())
    assert 'href="/analyse">Analyse</a>.' in client.get("/tableau").get_data(as_text=True)


def test_la_page_ne_montre_aucun_nom_ni_message(client, conn):
    importation.importer(conn, FAUX_EXPORT)
    page = client.get("/analyse").get_data(as_text=True)
    prospects = modeles.lister(conn)
    assert prospects
    for p in prospects:
        assert p["nom_entreprise"] not in page
        assert not p["texte_envoye"] or p["texte_envoye"] not in page
