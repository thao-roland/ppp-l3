"""Tests de l'étape 3 : score sur 100 et relances à faire (données fictives)."""

from datetime import date, timedelta

import pytest

import modeles
import scoring
from conftest import FAUX_EXPORT, formulaire_valide
import importation

AUJOURDHUI = date(2026, 11, 8)


def il_y_a(jours):
    return (AUJOURDHUI - timedelta(days=jours)).isoformat()


def prospect(**changements):
    """Prospect fictif ancien, sans réponse, score de base 10 (site inconnu)."""
    valeurs = {"id": 1, "statut": "contacté", "interet": "aucun", "a_deja_site": None,
               "date_premier_message": il_y_a(60), "date_reponse": None}
    valeurs.update(changements)
    return valeurs


@pytest.fixture
def regles():
    return scoring.charger_regles()


def score(regles, relances=(), **changements):
    return scoring.calculer_score(prospect(**changements), list(relances), regles, AUJOURDHUI)


# --- Le barème ---------------------------------------------------------------
def test_score_de_base_site_inconnu(regles):
    assert score(regles) == 10


def test_points_reponse(regles):
    assert score(regles, date_reponse=il_y_a(50)) == 40


@pytest.mark.parametrize("interet, attendu", [("aucun", 10), ("curieux", 30), ("demande de prix", 50)])
def test_points_interet(regles, interet, attendu):
    assert score(regles, interet=interet) == attendu


@pytest.mark.parametrize("site, attendu", [(0, 20), (None, 10), (1, 0)])
def test_points_site(regles, site, attendu):
    assert score(regles, a_deja_site=site) == attendu


def test_score_maximum_vaut_100(regles):
    assert score(regles, date_reponse=il_y_a(1), interet="demande de prix", a_deja_site=0) == 100


@pytest.mark.parametrize("jours, attendu", [(13, 20), (14, 10)])
def test_echange_recent_moins_de_14_jours(regles, jours, attendu):
    assert score(regles, date_premier_message=il_y_a(jours)) == attendu


def test_une_relance_recente_compte_comme_echange(regles):
    assert score(regles, [il_y_a(2)]) == 10 + 10 - 5


def test_date_future_pas_de_bonus(regles):
    assert score(regles, date_premier_message=il_y_a(-3)) == 10


def test_malus_par_relance_sans_reponse(regles):
    assert score(regles, [il_y_a(40), il_y_a(30)], a_deja_site=0) == 10


def test_le_score_ne_descend_pas_sous_zero(regles):
    assert score(regles, [il_y_a(40), il_y_a(30), il_y_a(20)], a_deja_site=1) == 0


def test_relance_avant_la_reponse_pas_de_malus(regles):
    assert score(regles, [il_y_a(55)], date_reponse=il_y_a(50)) == 40


def test_relance_le_jour_de_la_reponse_pas_de_malus(regles):
    assert score(regles, [il_y_a(50)], date_reponse=il_y_a(50)) == 40


def test_relance_apres_la_reponse_malus(regles):
    assert score(regles, [il_y_a(45)], date_reponse=il_y_a(50)) == 35


@pytest.mark.parametrize("statut", ["signé", "perdu"])
def test_signe_ou_perdu_sans_score(regles, statut):
    assert score(regles, statut=statut) is None


def test_prospect_sans_aucune_date(regles):
    assert score(regles, date_premier_message=None) == 10


def test_tri_du_meilleur_au_moins_bon_et_sans_score_a_la_fin(regles):
    prospects = [prospect(id=1, statut="perdu"), prospect(id=2),
                 prospect(id=3, interet="demande de prix")]
    notes = scoring.noter(prospects, {}, regles, AUJOURDHUI)
    assert [p["id"] for p in notes] == [3, 2, 1]


# --- Le fichier de règles ----------------------------------------------------
REGLES_VALIDES = """
statuts_hors_score = ["perdu"]
[points]
a_repondu = 50
echange_recent = 10
par_relance_sans_reponse = -5
[points.interet]
aucun = 0
curieux = 10
"demande de prix" = 30
[points.site]
sans_site = 10
inconnu = 5
avec_site = 0
[recence]
jours = 14
[relances]
delai_jours = 3
max_sans_reponse = 1
"""


def ecrire(tmp_path, contenu):
    fichier = tmp_path / "regles.toml"
    fichier.write_text(contenu, encoding="utf-8")
    return fichier


def test_changer_le_fichier_change_le_score(tmp_path):
    regles = scoring.charger_regles(ecrire(tmp_path, REGLES_VALIDES))
    assert scoring.calculer_score(
        prospect(date_reponse=il_y_a(50)), [], regles, AUJOURDHUI) == 55


def test_changer_le_delai_change_les_relances(tmp_path):
    regles = scoring.charger_regles(ecrire(tmp_path, REGLES_VALIDES))
    liste = scoring.a_relancer([prospect(date_premier_message=il_y_a(3))], {}, regles, AUJOURDHUI)
    assert len(liste) == 1


@pytest.mark.parametrize("ancien, nouveau", [
    ("a_repondu = 50", "a_repondu = 60"),      # maximum différent de 100
    ("a_repondu = 50\n", ""),                  # réglage absent
    ("curieux = 10\n", ""),                    # niveau d'intérêt absent
    ("delai_jours = 3\n", ""),
    ("[recence]", "[recence"),                 # fichier mal écrit
])
def test_regles_invalides_refusees(tmp_path, ancien, nouveau):
    with pytest.raises(scoring.ErreurRegles):
        scoring.charger_regles(ecrire(tmp_path, REGLES_VALIDES.replace(ancien, nouveau)))


def test_fichier_absent_refuse(tmp_path):
    with pytest.raises(scoring.ErreurRegles):
        scoring.charger_regles(tmp_path / "absent.toml")


# --- Les relances à faire ----------------------------------------------------
def codes_a_relancer(regles, prospects, relances=None):
    return [p["id"] for p in scoring.a_relancer(prospects, relances or {}, regles, AUJOURDHUI)]


@pytest.mark.parametrize("jours, attendu", [(6, []), (7, [1]), (8, [1])])
def test_delai_de_7_jours(regles, jours, attendu):
    assert codes_a_relancer(regles, [prospect(date_premier_message=il_y_a(jours))]) == attendu


def test_le_delai_part_de_ma_derniere_relance(regles):
    assert codes_a_relancer(regles, [prospect()], {1: [il_y_a(3)]}) == []
    assert codes_a_relancer(regles, [prospect()], {1: [il_y_a(10)]}) == [1]


def test_jours_et_nombre_de_relances_renvoyes(regles):
    ligne = scoring.a_relancer([prospect()], {1: [il_y_a(10)]}, regles, AUJOURDHUI)[0]
    assert (ligne["jours_sans_reponse"], ligne["nb_relances"]) == (10, 1)


def test_prospect_qui_a_repondu_pas_a_relancer(regles):
    assert codes_a_relancer(regles, [prospect(date_reponse=il_y_a(50))]) == []


def test_relance_restee_sans_reponse_apres_une_reponse(regles):
    assert codes_a_relancer(regles, [prospect(date_reponse=il_y_a(50))], {1: [il_y_a(20)]}) == [1]


def test_on_arrete_apres_2_relances_sans_reponse(regles):
    assert codes_a_relancer(regles, [prospect()], {1: [il_y_a(30), il_y_a(20)]}) == []


@pytest.mark.parametrize("statut", ["signé", "perdu"])
def test_signe_ou_perdu_pas_a_relancer(regles, statut):
    assert codes_a_relancer(regles, [prospect(statut=statut)]) == []


def test_sans_date_de_premier_message_pas_a_relancer(regles):
    assert codes_a_relancer(regles, [prospect(date_premier_message=None)]) == []


def test_ordre_score_puis_attente_la_plus_longue(regles):
    prospects = [prospect(id=1, date_premier_message=il_y_a(20)),
                 prospect(id=2, date_premier_message=il_y_a(40)),
                 prospect(id=3, date_premier_message=il_y_a(20), interet="curieux")]
    assert codes_a_relancer(regles, prospects) == [3, 2, 1]


# --- Les pages ---------------------------------------------------------------
def depuis(jours):
    """Date relative au vrai jour, pour les pages (marge large : fuseaux)."""
    return (date.today() - timedelta(days=jours)).isoformat()


def test_page_vide(client):
    reponse = client.get("/relances")
    assert reponse.status_code == 200
    assert "Aucune relance à faire" in reponse.get_data(as_text=True)


def test_le_lien_est_dans_l_entete(client):
    assert 'href="/relances"' in client.get("/").get_data(as_text=True)


def test_page_liste_le_prospect_a_relancer(client):
    client.post("/prospects/nouveau", data=formulaire_valide(date_premier_message=depuis(30)))
    page = client.get("/relances").get_data(as_text=True)
    assert "P001" in page and "30 j" in page


def test_page_n_affiche_pas_un_prospect_recent(client):
    client.post("/prospects/nouveau", data=formulaire_valide(date_premier_message=depuis(2)))
    assert "<td>P001</td>" not in client.get("/relances").get_data(as_text=True)


def test_accueil_trie_par_score(client):
    client.post("/prospects/nouveau", data=formulaire_valide(
        date_premier_message=depuis(30), interet="demande de prix"))
    client.post("/prospects/nouveau", data=formulaire_valide(date_premier_message=depuis(30)))
    page = client.get("/").get_data(as_text=True)
    assert page.index("P001") < page.index("P002")


def test_accueil_tiret_pour_un_prospect_perdu(client):
    client.post("/prospects/nouveau", data=formulaire_valide(statut="perdu"))
    assert "<td>—</td>" in client.get("/").get_data(as_text=True)


def test_regles_abimees_message_clair(client, tmp_path, monkeypatch):
    monkeypatch.setattr(scoring, "FICHIER_REGLES", tmp_path / "absent.toml")
    reponse = client.get("/")
    assert reponse.status_code == 500
    assert "scoring.toml" in reponse.get_data(as_text=True)


def test_dates_relances_groupees_par_prospect(client, conn):
    client.post("/prospects/nouveau", data=formulaire_valide())
    identifiant = modeles.obtenir(conn, "P001")["id"]
    modeles.ajouter_relance(conn, identifiant, {"date": "2026-10-09", "texte": None})
    modeles.ajouter_relance(conn, identifiant, {"date": "2026-10-05", "texte": None})
    assert modeles.dates_relances(conn) == {identifiant: ["2026-10-05", "2026-10-09"]}


def test_les_pages_marchent_apres_un_faux_import(client, conn):
    importation.importer(conn, FAUX_EXPORT)
    assert client.get("/").status_code == 200
    assert client.get("/relances").status_code == 200
