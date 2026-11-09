"""Tests de l'étape 7 : réponses automatiques, écran Qualifier, exports enrichis.

Tous les noms et messages sont inventés.
"""

import io
import json
from datetime import date, timedelta

import pytest
from openpyxl import load_workbook

import analyse
import db
import exports
import exports_excel
import facebook
import importation
import modeles
import pages_qualifier
import scoring
import tableau
from conftest import formulaire_valide

MOI = "Moi Fictif"
AUTRE = "Entreprise Inventée"
T0 = 1_780_000_000_000
MINUTE = 60_000
TEXTE_SECRET = "Texte de réponse totalement inventé"


def mien(minutes, texte="Bonjour"):
    return (T0 + minutes * MINUTE, MOI, texte)


def autre(minutes, texte="Oui, dites-m'en plus"):
    return (T0 + minutes * MINUTE, AUTRE, texte)


def conversation(*messages):
    return {"cle": "111", "participants": [MOI, AUTRE], "messages": list(messages)}


def detection(*messages):
    return facebook.analyser(conversation(*messages), MOI)[0]["reponse_automatique"]


# --- Détection ------------------------------------------------------------------
def test_reponse_lente_sans_formule_non():
    assert detection(mien(0), autre(60)) == "non"


def test_reponse_rapide_seule_a_verifier():
    assert detection(mien(0), autre(1)) == "à vérifier"


def test_formule_seule_a_verifier():
    assert detection(mien(0), autre(60, "Merci pour votre message !")) == "à vérifier"


def test_rapide_et_formule_oui():
    assert detection(mien(0), autre(1, "Merci pour votre message !")) == "oui"


def test_limite_de_2_minutes():
    assert detection(mien(0), (T0 + 119_999, AUTRE, "Oui")) == "à vérifier"
    assert detection(mien(0), (T0 + 120_000, AUTRE, "Oui")) == "non"


@pytest.mark.parametrize("texte", [
    "MERCI POUR VOTRE MESSAGE", "Nous vous répondrons vite", "nous vous repondrons vite",
    "Notre équipe revient vers vous", "NOTRE EQUIPE", "Ceci est une réponse automatique",
    "Consultez nos horaires",
])
def test_formules_sans_accents_ni_majuscules(texte):
    assert detection(mien(0), autre(60, texte)) == "à vérifier"


def test_delai_mesure_depuis_mon_dernier_message():
    assert detection(mien(0), mien(30), autre(31)) == "à vérifier"


def test_message_sans_texte():
    assert detection(mien(0), autre(60, None)) == "non"
    assert detection(mien(0), autre(1, None)) == "à vérifier"


def test_un_vrai_message_apres_une_reponse_automatique_donne_non():
    assert detection(mien(0), autre(1, "Merci pour votre message"), mien(10), autre(90)) == "non"


def test_deux_messages_suspects_restent_suspects():
    assert detection(mien(0), autre(1, "Notre équipe arrive"), mien(10), autre(11)) == "oui"


def test_sans_reponse_pas_de_detection():
    assert detection(mien(0)) is None


def test_message_de_l_autre_avant_le_mien_ignore():
    assert detection(autre(-500, "Merci pour votre message"), mien(0), autre(60)) == "non"


# --- Import ---------------------------------------------------------------------
def ecrire_export(racine, cle, messages):
    dossier = racine / "messages" / "inbox" / f"fictif_{cle}"
    dossier.mkdir(parents=True)
    contenu = {
        "participants": [{"name": MOI}, {"name": AUTRE + cle}],
        "messages": [{"sender_name": AUTRE + cle if qui == AUTRE else qui, "timestamp_ms": ts, "content": texte}
                     for ts, qui, texte in messages],
        "thread_path": f"inbox/fictif_{cle}",
    }
    (dossier / "message_1.json").write_text(json.dumps(contenu), encoding="utf-8")


@pytest.fixture
def export(tmp_path):
    racine = tmp_path / "export"
    ecrire_export(racine, "1", [mien(0), autre(1, TEXTE_SECRET + " merci pour votre message")])
    ecrire_export(racine, "2", [mien(0), autre(60, TEXTE_SECRET)])
    ecrire_export(racine, "3", [mien(0)])
    return racine


def fiche(conn, cle):
    return conn.execute("SELECT * FROM prospects WHERE conversation_fb = ?", (cle,)).fetchone()


def test_import_enregistre_la_detection(conn, export):
    rapport = importation.importer(conn, export, MOI)
    assert fiche(conn, "1")["reponse_automatique"] == "oui"
    assert fiche(conn, "2")["reponse_automatique"] == "non"
    assert fiche(conn, "3")["reponse_automatique"] is None
    assert (rapport["auto_oui"], rapport["auto_non"], rapport["auto_a_verifier"]) == (1, 1, 0)


def test_le_texte_de_la_reponse_n_est_jamais_enregistre(conn, export):
    importation.importer(conn, export, MOI)
    for table in ("prospects", "relances"):
        for ligne in conn.execute(f"SELECT * FROM {table}"):
            assert not any(TEXTE_SECRET in str(v) for v in tuple(ligne))


def test_reimport_complete_les_fiches_anciennes(conn, export):
    importation.importer(conn, export, MOI)
    conn.execute("UPDATE prospects SET reponse_automatique = NULL")
    conn.commit()
    rapport = importation.importer(conn, export, MOI)
    assert rapport["detections_completees"] == 2 and rapport["nouveaux"] == []
    assert fiche(conn, "1")["reponse_automatique"] == "oui"


def test_reimport_ne_remplace_jamais_une_correction(conn, export):
    importation.importer(conn, export, MOI)
    conn.execute("UPDATE prospects SET reponse_automatique = 'non' WHERE conversation_fb = '1'")
    conn.commit()
    rapport = importation.importer(conn, export, MOI)
    assert rapport["detections_completees"] == 0
    assert fiche(conn, "1")["reponse_automatique"] == "non"


def test_simulation_ne_complete_rien(conn, export):
    importation.importer(conn, export, MOI)
    conn.execute("UPDATE prospects SET reponse_automatique = NULL")
    conn.commit()
    rapport = importation.importer(conn, export, MOI, simuler=True)
    assert rapport["detections_completees"] == 2
    assert fiche(conn, "1")["reponse_automatique"] is None


def test_migration_d_une_ancienne_base(tmp_path):
    connexion = db.connecter(tmp_path / "ancienne.db")
    connexion.execute("CREATE TABLE prospects (id INTEGER PRIMARY KEY, code TEXT, conversation_fb TEXT)")
    db.initialiser(connexion)
    colonnes = {l["name"] for l in connexion.execute("PRAGMA table_info(prospects)")}
    connexion.close()
    assert "reponse_automatique" in colonnes


# --- Tableau et analyse ---------------------------------------------------------
def prospect(**changements):
    valeurs = {"id": 1, "code": "P001", "statut": "a répondu", "interet": "aucun",
               "date_reponse": "2026-10-06", "date_premier_message": "2026-10-05",
               "version_message": "A", "canal": "Messenger", "dates_estimees": 0,
               "reponse_automatique": None, "a_deja_site": None}
    valeurs.update(changements)
    return valeurs


@pytest.mark.parametrize("changements, attendu", [
    ({"reponse_automatique": "non"}, "vraie"),
    ({"reponse_automatique": None}, "vraie"),
    ({"reponse_automatique": "oui"}, "automatique"),
    ({"reponse_automatique": "à vérifier"}, "a_verifier"),
    ({"reponse_automatique": "oui", "interet": "curieux"}, "vraie"),
    ({"reponse_automatique": "à vérifier", "statut": "signé"}, "vraie"),
    ({"date_reponse": None, "statut": "contacté"}, "aucune"),
])
def test_categorie_de_reponse(changements, attendu):
    assert tableau.categorie_reponse(prospect(**changements)) == attendu


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
    modeles.mettre_a_jour_champ(conn, "P001", "reponse_automatique", "oui")
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


def test_correction_a_la_main_remet_les_points(client, conn):
    client.post("/prospects/nouveau", data=formulaire_valide(date_reponse="2026-10-03"))
    modeles.mettre_a_jour_champ(conn, "P001", "reponse_automatique", "oui")
    regles_actuelles = scoring.charger_regles()
    avant = scoring.noter(modeles.lister(conn), {}, regles_actuelles, JOUR)[0]["score"]
    client.post("/qualifier/P001", json={"champ": "reponse_automatique", "valeur": "non"})
    conn.commit()
    apres = scoring.noter(modeles.lister(conn), {}, regles_actuelles, JOUR)[0]["score"]
    assert apres - avant == 30


# --- Écran Qualifier ------------------------------------------------------------
def ajouter(client, conn, automatique=None, **changements):
    valeurs = {"date_reponse": "2026-10-03", "statut": "a répondu", **changements}
    client.post("/prospects/nouveau", data=formulaire_valide(**valeurs))
    code = max(p["code"] for p in modeles.lister(conn))
    if automatique:
        modeles.mettre_a_jour_champ(conn, code, "reponse_automatique", automatique)
    return code


def poster(client, code, champ, valeur):
    return client.post(f"/qualifier/{code}", json={"champ": champ, "valeur": valeur})


def test_liste_seulement_ceux_qui_ont_repondu(client, conn):
    code = ajouter(client, conn)
    autre_code = ajouter(client, conn, date_reponse="", statut="contacté")
    page = client.get("/qualifier").get_data(as_text=True)
    assert f"<strong>{code}</strong>" in page and f"<strong>{autre_code}</strong>" not in page


def test_les_reponses_a_verifier_arrivent_en_premier():
    groupe = [prospect(code="P1", reponse_automatique="non"), prospect(code="P2", reponse_automatique="oui"),
              prospect(code="P3", reponse_automatique="à vérifier")]
    assert [p["code"] for p in pages_qualifier.a_qualifier(groupe)] == ["P3", "P2", "P1"]


def test_lien_dans_l_entete_et_script(client):
    page = client.get("/qualifier").get_data(as_text=True)
    assert 'href="/qualifier"' in page and "qualifier.js" in page


def test_nom_echappe_dans_la_page(client, conn):
    ajouter(client, conn, nom_entreprise="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in client.get("/qualifier").get_data(as_text=True)


@pytest.mark.parametrize("champ, envoye, colonne, attendu", [
    ("interet", "curieux", "interet", "curieux"),
    ("interet", "demande de prix", "interet", "demande de prix"),
    ("version_message", "B", "version_message", "B"),
    ("version_message", "", "version_message", None),
    ("tarif_propose", "450", "tarif_propose", 450),
    ("tarif_propose", 450, "tarif_propose", 450),
    ("acompte", "150", "acompte", 150),
    ("acompte", "", "acompte", None),
    ("reponse_automatique", "à vérifier", "reponse_automatique", "à vérifier"),
    ("signe", "oui", "statut", "signé"),
    ("signe", "non", "statut", "a répondu"),
])
def test_un_champ_enregistre(client, conn, champ, envoye, colonne, attendu):
    code = ajouter(client, conn, automatique="oui")
    reponse = poster(client, code, champ, envoye)
    assert reponse.status_code == 200
    assert reponse.get_json()["valeur"] == attendu
    conn.commit()
    assert modeles.obtenir(conn, code)[colonne] == attendu


def test_un_clic_ne_change_que_son_champ(client, conn):
    code = ajouter(client, conn, automatique="oui", ville="Ville Fictive")
    avant = dict(modeles.obtenir(conn, code))
    poster(client, code, "interet", "curieux")
    conn.commit()
    apres = dict(modeles.obtenir(conn, code))
    assert {k for k in avant if avant[k] != apres[k]} == {"interet"}


@pytest.mark.parametrize("champ, valeur", [
    ("interet", "beaucoup"), ("interet", ""), ("version_message", "C"),
    ("tarif_propose", "-5"), ("tarif_propose", "abc"), ("acompte", "1.5"),
    ("reponse_automatique", "peut-être"), ("reponse_automatique", ""),
    ("signe", "peut-être"), ("nom_entreprise", "Autre nom"), ("statut", "signé"),
    ("code", "P999"), ("interet", ["curieux"]), ("interet", True), (["interet"], "curieux"),
    ("tarif_propose; DROP TABLE prospects", "1"),
])
def test_valeurs_refusees(client, conn, champ, valeur):
    code = ajouter(client, conn)
    avant = dict(modeles.obtenir(conn, code))
    reponse = poster(client, code, champ, valeur)
    assert reponse.status_code == 400
    assert "erreur" in reponse.get_json()
    conn.commit()
    assert dict(modeles.obtenir(conn, code)) == avant


def test_prospect_inconnu(client):
    reponse = poster(client, "P999", "interet", "curieux")
    assert reponse.status_code == 404


def test_formulaire_classique_refuse(client, conn):
    code = ajouter(client, conn)
    reponse = client.post(f"/qualifier/{code}", data={"champ": "interet", "valeur": "curieux"})
    assert reponse.status_code == 400
    assert modeles.obtenir(conn, code)["interet"] == "aucun"


def test_autre_site_refuse(client, conn):
    code = ajouter(client, conn)
    reponse = client.post(f"/qualifier/{code}", json={"champ": "interet", "valeur": "curieux"},
                          headers={"Origin": "https://site-piege.example"})
    assert reponse.status_code == 403


def test_message_d_erreur_sans_nom(client, conn):
    code = ajouter(client, conn, nom_entreprise="Nom Fictif Unique")
    assert "Nom Fictif Unique" not in poster(client, code, "interet", "x").get_data(as_text=True)


def test_mise_a_jour_refuse_une_colonne_libre(conn):
    with pytest.raises(ValueError):
        modeles.mettre_a_jour_champ(conn, "P001", "nom_entreprise", "x")


# --- CSV ------------------------------------------------------------------------
def ligne_csv(relances=None, **changements):
    import csv
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
