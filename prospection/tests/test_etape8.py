"""Tests de l'analyse automatique des messages et de l'écran « À vérifier ».

Toutes les conversations sont INVENTÉES.
"""

import json
import re
from pathlib import Path

import pytest

import analyse
import analyse_messages
import analyser_cli
import db
import importation
import modeles
import pages_a_verifier
import tableau
from conftest import formulaire_valide

MOI = "Moi Fictif"
AUTRE = "Entreprise Inventée"
T0 = 1_780_000_000_000
MINUTE = 60_000
TEXTE_SECRET = "Phrase totalement inventée pour le test"
REGLES = {**analyse_messages.charger_regles(), "auto_actif": True}
CHARGER_VRAI = analyse_messages.charger_regles


@pytest.fixture(autouse=True)
def detection_active(monkeypatch):
    """Ces tests vérifient la détection : on l'active, quel que soit le réglage du fichier."""
    monkeypatch.setattr(analyse_messages, "charger_regles", lambda chemin=None: {**CHARGER_VRAI(chemin), "auto_actif": True})


def mien(minutes, texte="Bonjour, je crée des sites"):
    return (T0 + minutes * MINUTE, MOI, texte)


def autre(minutes, texte="Bonjour"):
    return (T0 + minutes * MINUTE, AUTRE, texte)


def resultat(*messages):
    conversation = {"cle": "111", "participants": [MOI, AUTRE], "messages": list(messages)}
    return analyse_messages.analyser(conversation, MOI, REGLES)


# --- Réponse automatique --------------------------------------------------------
@pytest.mark.parametrize("messages, attendu", [
    ([mien(0), autre(60, "Bonjour à vous")], "non"),
    ([mien(0), autre(1, "Bonjour à vous")], "oui"),
    ([mien(0), autre(60, "Merci pour votre message")], "oui"),
    ([mien(0), autre(60, "Nous reviendrons vers vous")], "oui"),
    ([mien(0), autre(60, "NOUS VOUS RÉPONDRONS vite")], "oui"),
    ([mien(0), autre(60, "nous vous repondrons vite")], "oui"),
    ([mien(0), autre(60, "Notre équipe arrive")], "oui"),
    ([mien(0), autre(60, "Ceci est une réponse automatique")], "oui"),
    ([mien(0), autre(60, "Voici nos horaires")], "oui"),
    ([mien(0), autre(1, None)], "oui"),
    ([mien(0), autre(60, None)], "non"),
])
def test_reponse_automatique(messages, attendu):
    assert resultat(*messages)["reponse_automatique"] == attendu


def test_limite_de_2_minutes():
    assert resultat(mien(0), (T0 + 119_999, AUTRE, "Salut"))["reponse_automatique"] == "oui"
    assert resultat(mien(0), (T0 + 120_000, AUTRE, "Salut"))["reponse_automatique"] == "non"


def test_delai_mesure_depuis_mon_dernier_message():
    assert resultat(mien(0), mien(30), autre(31, "Salut"))["reponse_automatique"] == "oui"


@pytest.mark.parametrize("texte", ["Combien ça coûte", "Non merci", "Pourquoi pas"])
def test_rapide_avec_des_mots_humains_a_verifier(texte):
    assert resultat(mien(0), autre(1, texte))["reponse_automatique"] == "à vérifier"


def test_formule_dans_une_question_lente_a_verifier():
    assert resultat(mien(0), autre(60, "Quels sont vos horaires ?"))["reponse_automatique"] == "à vérifier"


def test_un_message_ecrit_a_la_main_apres_une_reponse_automatique():
    sortie = resultat(mien(0), autre(1, "Merci pour votre message"), mien(10), autre(90, "Combien ?"))
    assert (sortie["reponse_automatique"], sortie["interet"]) == ("non", "demande de prix")


def test_deux_messages_suspects_restent_automatiques():
    assert resultat(mien(0), autre(1, "Salut"), mien(10), autre(11, "Salut"))["reponse_automatique"] == "oui"


def test_sans_reponse():
    assert resultat(mien(0)) == {"reponse_automatique": None, "interet": "aucun",
                                 "tarif_propose": None, "a_deja_site": None}


def test_message_de_l_autre_avant_le_mien_ignore():
    assert resultat(autre(-500, "Combien"), mien(0))["reponse_automatique"] is None


# --- Détection désactivée dans regles_messages.toml -----------------------------
def resultat_sans_detection(*messages):
    conversation = {"cle": "111", "participants": [MOI, AUTRE], "messages": list(messages)}
    return analyse_messages.analyser(conversation, MOI, {**REGLES, "auto_actif": False})


def test_le_fichier_livre_desactive_la_detection():
    assert CHARGER_VRAI()["auto_actif"] is False


@pytest.mark.parametrize("texte", ["Salut", "Merci pour votre message", "Combien"])
def test_sans_detection_toute_reponse_est_vraie(texte):
    assert resultat_sans_detection(mien(0), autre(1, texte))["reponse_automatique"] == "non"


def test_sans_detection_une_formule_compte_pour_l_interet():
    assert resultat_sans_detection(mien(0), autre(1, "Notre équipe veut un devis"))["interet"] == "demande de prix"


def test_sans_detection_une_reponse_rapide_compte_pour_l_interet():
    assert resultat_sans_detection(mien(0), autre(1, "Pourquoi pas"))["interet"] == "curieux"


def test_sans_reponse_reste_sans_detection():
    assert resultat_sans_detection(mien(0))["reponse_automatique"] is None


def test_actif_doit_etre_vrai_ou_faux(tmp_path):
    contenu = REGLES_MINIMALES.replace("delai_secondes = 10", 'actif = "non"\ndelai_secondes = 10')
    with pytest.raises(analyse_messages.ErreurRegles):
        regles_depuis(tmp_path, contenu)


def test_actif_absent_vaut_actif(tmp_path):
    assert CHARGER_VRAI(regles_fichier(tmp_path, REGLES_MINIMALES))["auto_actif"] is True


# --- Intérêt --------------------------------------------------------------------
@pytest.mark.parametrize("texte, attendu", [
    ("Quel est votre prix", "demande de prix"),
    ("Vos tarifs svp", "demande de prix"),
    ("Je veux un devis", "demande de prix"),
    ("Quel délai", "demande de prix"),
    ("delai", "demande de prix"),
    ("Combien ça fait", "demande de prix"),
    ("Pourquoi pas", "curieux"),
    ("Ça m'intéresse", "curieux"),
    ("ca m’interesse", "curieux"),
    ("Dites-moi en plus", "curieux"),
    ("Vous êtes qui ?", "curieux"),
    ("Non merci", "aucun"),
    ("Pas besoin", "aucun"),
    ("Pas intéressé", "aucun"),
    ("Nous avons déjà un site", "aucun"),
    ("Ok", "à vérifier"),
    ("Mépris total", "à vérifier"),
    (None, "à vérifier"),
    ("Non merci, mais combien", "à vérifier"),
    ("Non merci, pourquoi pas plus tard", "à vérifier"),
])
def test_interet(texte, attendu):
    assert resultat(mien(0), autre(60, texte))["interet"] == attendu


def test_seulement_automatique_interet_aucun():
    assert resultat(mien(0), autre(1, "Salut"))["interet"] == "aucun"


def test_les_mots_d_une_formule_automatique_ne_comptent_pas():
    assert resultat(mien(0), autre(60, "Notre équipe prépare un devis"))["interet"] == "à vérifier"


# --- Tarif ----------------------------------------------------------------------
def tarif(*suite, demande="Quel est votre tarif"):
    return resultat(mien(0), autre(60, demande), *suite)["tarif_propose"]


@pytest.mark.parametrize("texte, attendu", [
    ("Je propose 450 €", 450), ("450€", 450), ("500 euros", 500), ("1 200€", 1200),
    ("1.200 euros", 1200), ("49,90 €", 49), ("à partir de 300 eur", 300), ("3 pages", None),
    ("0 €", None), ("Pour 2026 je peux", None),
])
def test_montants(texte, attendu):
    assert tarif(mien(70, texte)) == attendu


def test_premier_montant_garde():
    assert tarif(mien(70, "300 €"), mien(80, "Ou 500 €")) == 300


def test_montant_avant_la_demande_ignore():
    assert resultat(mien(0, "Dès 300 €"), autre(60, "Combien"))["tarif_propose"] is None


def test_montant_de_l_autre_ignore():
    assert tarif(autre(70, "Mon budget est 900 €")) is None


def test_pas_de_tarif_sans_demande_de_prix():
    assert resultat(mien(0), autre(60, "Pourquoi pas"), mien(70, "450 €"))["tarif_propose"] is None


# --- Site -----------------------------------------------------------------------
@pytest.mark.parametrize("texte, attendu", [
    ("J'ai déjà un site", 1), ("Nous avons déjà un site", 1), ("Je n'ai pas de site", None), ("Bonjour", None),
])
def test_a_deja_site(texte, attendu):
    assert resultat(mien(0), autre(60, texte))["a_deja_site"] == attendu


# --- Versions -------------------------------------------------------------------
@pytest.mark.parametrize("rang, attendu", [(0, "A"), (1, "B"), (25, "Z"), (26, "AA"), (27, "AB"), (701, "ZZ"), (702, "AAA")])
def test_code_version(rang, attendu):
    assert analyse_messages.code_version(rang) == attendu


def test_le_resultat_ne_contient_jamais_de_texte():
    sortie = resultat(mien(0, TEXTE_SECRET), autre(60, TEXTE_SECRET + " combien"), mien(70, TEXTE_SECRET + " 450 €"))
    assert TEXTE_SECRET not in str(sortie)


# --- Fichier de règles ----------------------------------------------------------
REGLES_MINIMALES = """
[reponses_automatiques]
delai_secondes = 10
formules = ["message robot"]
[interet]
prix = ["sous"]
curieux = ["super"]
refus = ["jamais"]
[site]
deja_un_site = ["mon site"]
"""


def regles_fichier(tmp_path, contenu):
    fichier = tmp_path / "regles.toml"
    fichier.write_text(contenu, encoding="utf-8")
    return fichier


def regles_depuis(tmp_path, contenu):
    return CHARGER_VRAI(regles_fichier(tmp_path, contenu))


def test_changer_le_fichier_change_le_resultat(tmp_path):
    regles = regles_depuis(tmp_path, REGLES_MINIMALES)
    conversation = {"cle": "1", "participants": [MOI, AUTRE], "messages": [mien(0), autre(60, "Combien de sous")]}
    assert analyse_messages.analyser(conversation, MOI, regles)["interet"] == "demande de prix"
    conversation["messages"] = [mien(0), autre(60, "Combien")]
    assert analyse_messages.analyser(conversation, MOI, regles)["interet"] == "à vérifier"


@pytest.mark.parametrize("ancien, nouveau", [
    ('delai_secondes = 10\n', ''), ('prix = ["sous"]\n', ''), ('[site]', '[site'), ('delai_secondes = 10', 'delai_secondes = "x"'),
])
def test_regles_abimees_refusees(tmp_path, ancien, nouveau):
    with pytest.raises(analyse_messages.ErreurRegles):
        regles_depuis(tmp_path, REGLES_MINIMALES.replace(ancien, nouveau))


def test_les_listes_ne_sont_pas_dans_le_code():
    code = Path(analyse_messages.__file__).read_text(encoding="utf-8")
    assert "non merci" not in code and "demande de prix\", \"curieux" not in code


@pytest.mark.parametrize("fichier", ["analyse_messages.py", "importation.py", "analyser_cli.py", "facebook.py"])
def test_aucun_acces_reseau_ni_ia(fichier):
    code = (Path(analyse_messages.__file__).parent / fichier).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(socket|http|urllib|requests|httpx|anthropic|openai)\b", code, re.M)


# --- Import et analyse sur la base ----------------------------------------------
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
    ecrire_export(racine, "1", [mien(1000, "Texte deux"), autre(1060, TEXTE_SECRET + " combien"), mien(1070, "450 €")])
    ecrire_export(racine, "2", [mien(0, "Texte un"), autre(1, "Merci pour votre message")])
    ecrire_export(racine, "3", [mien(2000, "Texte un")])
    return racine


def fiche(conn, cle):
    return conn.execute("SELECT * FROM prospects WHERE conversation_fb = ?", (cle,)).fetchone()


def test_import_remplit_les_champs(conn, export):
    importation.importer(conn, export, MOI)
    p = fiche(conn, "1")
    assert (p["reponse_automatique"], p["interet"], p["tarif_propose"]) == ("non", "demande de prix", 450)
    assert fiche(conn, "2")["reponse_automatique"] == "oui"
    assert fiche(conn, "3")["reponse_automatique"] is None


def test_versions_dans_l_ordre_chronologique(conn, export):
    importation.importer(conn, export, MOI)
    assert (fiche(conn, "2")["version_message"], fiche(conn, "1")["version_message"],
            fiche(conn, "3")["version_message"]) == ("A", "B", "A")


def test_une_lettre_ne_change_pas_si_un_texte_plus_ancien_arrive(conn, export, tmp_path):
    importation.importer(conn, export, MOI)
    ecrire_export(export, "4", [mien(-5000, "Texte zéro"), autre(-4000, "Oui")])
    importation.importer(conn, export, MOI)
    assert (fiche(conn, "2")["version_message"], fiche(conn, "4")["version_message"]) == ("A", "C")


def test_le_texte_de_la_reponse_n_est_jamais_enregistre(conn, export):
    importation.importer(conn, export, MOI)
    for table in ("prospects", "relances", "versions_message", "corrections"):
        for ligne in conn.execute(f"SELECT * FROM {table}"):
            assert not any(TEXTE_SECRET in str(v) for v in tuple(ligne))


def test_analyser_base_met_a_jour_sans_creer(conn, export):
    importation.importer(conn, export, MOI)
    conn.execute("UPDATE prospects SET interet = 'aucun', tarif_propose = NULL WHERE conversation_fb = '1'")
    conn.commit()
    ecrire_export(export, "9", [mien(3000), autre(3060, "Oui")])
    rapport = importation.analyser_base(conn, export, MOI)
    assert rapport["nouveaux"] == [] and rapport["sans_fiche"] == 1
    assert rapport["fiches_mises_a_jour"] == 1
    assert fiche(conn, "1")["tarif_propose"] == 450
    assert fiche(conn, "9") is None


def test_simulation_n_enregistre_rien(conn, export):
    importation.importer(conn, export, MOI)
    conn.execute("UPDATE prospects SET interet = 'aucun' WHERE conversation_fb = '1'")
    conn.execute("DELETE FROM versions_message")
    conn.commit()
    rapport = importation.analyser_base(conn, export, MOI, simuler=True)
    assert rapport["categories"]["interesses"] == 1
    assert fiche(conn, "1")["interet"] == "aucun"
    assert conn.execute("SELECT COUNT(*) FROM versions_message").fetchone()[0] == 0


def test_analyse_ne_remplace_jamais_une_correction(conn, export):
    importation.importer(conn, export, MOI)
    modeles.corriger(conn, fiche(conn, "1")["id"], "interet", "curieux")
    importation.analyser_base(conn, export, MOI)
    assert fiche(conn, "1")["interet"] == "curieux"
    assert fiche(conn, "1")["tarif_propose"] == 450


def test_modifier_la_fiche_compte_comme_correction(client, conn, export):
    importation.importer(conn, export, MOI)
    code = fiche(conn, "1")["code"]
    client.post(f"/prospects/{code}/modifier", data=formulaire_valide(
        date_premier_message="2026-06-01", interet="curieux", version_message="B",
        date_reponse="2026-06-02", reponse_automatique="non", tarif_propose="450"))
    importation.analyser_base(conn, export, MOI)
    assert fiche(conn, "1")["interet"] == "curieux"
    assert "interet" in modeles.champs_corriges(conn, fiche(conn, "1")["id"])


def test_prospect_ajoute_a_la_main_jamais_touche(client, conn, export):
    client.post("/prospects/nouveau", data=formulaire_valide(interet="curieux"))
    importation.importer(conn, export, MOI)
    importation.analyser_base(conn, export, MOI)
    assert modeles.obtenir(conn, "P001")["interet"] == "curieux"


def test_signe_reste_manuel(conn, export):
    importation.importer(conn, export, MOI)
    conn.execute("UPDATE prospects SET statut = 'signé' WHERE conversation_fb = '1'")
    conn.commit()
    importation.analyser_base(conn, export, MOI)
    assert fiche(conn, "1")["statut"] == "signé"
    assert all(p["statut"] != "signé" for p in modeles.lister(conn) if p["conversation_fb"] != "1")


def test_migration_d_une_ancienne_base(tmp_path):
    connexion = db.connecter(tmp_path / "ancienne.db")
    connexion.execute("CREATE TABLE prospects (id INTEGER PRIMARY KEY, code TEXT, conversation_fb TEXT)")
    db.initialiser(connexion)
    colonnes = {l["name"] for l in connexion.execute("PRAGMA table_info(prospects)")}
    tables = {l["name"] for l in connexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    connexion.close()
    assert "reponse_automatique" in colonnes and {"versions_message", "corrections"} <= tables


def test_commande_n_affiche_que_des_nombres(conn, export, dossier_donnees, monkeypatch, capsys):
    importation.importer(conn, export, MOI)
    (dossier_donnees / "exports_facebook" / "export_test").parent.mkdir(exist_ok=True)
    export.rename(dossier_donnees / "exports_facebook" / "export_test")
    monkeypatch.setenv("CRM_DONNEES", str(dossier_donnees))
    assert analyser_cli.main(["--mon-nom", MOI]) == 0
    sortie = capsys.readouterr().out
    assert "Fiches analysées            : 3" in sortie and "à vérifier" in sortie
    assert AUTRE not in sortie and MOI not in sortie and TEXTE_SECRET not in sortie


# --- Catégories et versions dans les pages --------------------------------------
def prospect(**changements):
    valeurs = {"statut": "a répondu", "interet": "aucun", "date_reponse": "2026-10-06",
               "date_premier_message": "2026-10-05", "version_message": "A", "canal": "Messenger",
               "dates_estimees": 0, "reponse_automatique": "non"}
    valeurs.update(changements)
    return valeurs


def test_compter_categories():
    groupe = [prospect(reponse_automatique="oui"), prospect(interet="demande de prix"), prospect(interet="curieux"),
              prospect(), prospect(reponse_automatique="à vérifier"), prospect(interet="à vérifier"),
              prospect(date_reponse=None, statut="contacté", reponse_automatique=None)]
    assert tableau.compter_categories(groupe) == {
        "auto": 1, "vraies": 4, "interesses": 1, "curieux": 1, "pas_interesses": 1, "a_verifier": 2, "sans_reponse": 1}


def groupe_versions():
    return ([prospect(version_message="C") for _ in range(5)] + [prospect(version_message="B") for _ in range(3)]
            + [prospect(version_message="A")])


def test_versions_triees_par_contacts():
    assert [l["libelle"] for l in tableau.comparer_versions(groupe_versions())] == ["C", "B", "A"]


def test_fisher_compare_les_deux_versions_les_plus_utilisees():
    conclusion = analyse.construire(groupe_versions())["conclusion_ab"]
    assert (conclusion["a"], conclusion["b"]) == ("C", "B")
    assert "C : 5, B : 3" in conclusion["texte"]


def test_versions_au_dela_de_la_limite_regroupees():
    groupe = [prospect(version_message=analyse_messages.code_version(i)) for i in range(14)]
    lignes = tableau.comparer_versions(groupe)
    assert len(lignes) == tableau.LIMITE_VERSIONS + 1
    assert lignes[-1]["libelle"] == "Autres (4 versions)" and lignes[-1]["contacts"] == 4


@pytest.mark.parametrize("libelle, attendu", [("A", True), ("AB", True), ("Non renseigné", False), ("Autres (4 versions)", False)])
def test_est_version(libelle, attendu):
    assert tableau.est_version(libelle) is attendu


@pytest.mark.parametrize("version, valide", [("C", True), ("aa", True), ("ABC", True), ("ABCD", False), ("A1", False)])
def test_version_saisie_sur_la_fiche(version, valide):
    _, erreurs = modeles.valider(formulaire_valide(version_message=version))
    assert ("version_message" not in erreurs) is valide


# --- Écran « À vérifier » -------------------------------------------------------
def ajouter(client, conn, reponse_automatique=None, interet=None, **changements):
    valeurs = {"date_reponse": "2026-10-03", "statut": "a répondu", **changements}
    client.post("/prospects/nouveau", data=formulaire_valide(**valeurs))
    code = max(p["code"] for p in modeles.lister(conn))
    identifiant = modeles.obtenir(conn, code)["id"]
    if reponse_automatique:
        modeles.ecrire_champ_analyse(conn, identifiant, "reponse_automatique", reponse_automatique)
    if interet:
        modeles.ecrire_champ_analyse(conn, identifiant, "interet", interet)
    conn.commit()
    return code


def poster(client, code, champ, valeur):
    return client.post(f"/a-verifier/{code}", json={"champ": champ, "valeur": valeur})


def test_seulement_les_cas_douteux(client, conn):
    douteux = ajouter(client, conn, reponse_automatique="à vérifier")
    douteux_interet = ajouter(client, conn, interet="à vérifier")
    clair = ajouter(client, conn, reponse_automatique="non")
    page = client.get("/a-verifier").get_data(as_text=True)
    assert f"<strong>{douteux}</strong>" in page and f"<strong>{douteux_interet}</strong>" in page
    assert f"<strong>{clair}</strong>" not in page


def test_seuls_les_champs_douteux_sont_proposes(client, conn):
    ajouter(client, conn, interet="à vérifier")
    page = client.get("/a-verifier").get_data(as_text=True)
    assert 'data-champ="interet"' in page and 'data-champ="reponse_automatique"' not in page


def test_reponses_douteuses_d_abord():
    groupe = [dict(prospect(interet="à vérifier"), code="P1"), dict(prospect(reponse_automatique="à vérifier"), code="P2")]
    assert [p["code"] for p in pages_a_verifier.cas_douteux(groupe)] == ["P2", "P1"]


def test_page_vide(client):
    page = client.get("/a-verifier").get_data(as_text=True)
    assert 'id="rien-a-verifier" class="message"' in page and 'href="/a-verifier"' in page
    assert 'class="message" hidden' not in page


def test_ancienne_adresse_retiree(client):
    assert client.get("/qualifier").status_code == 404


@pytest.mark.parametrize("champ, valeur", [
    ("interet", "aucun"), ("interet", "curieux"), ("interet", "demande de prix"),
    ("reponse_automatique", "non"), ("reponse_automatique", "oui"),
])
def test_correction_enregistree(client, conn, champ, valeur):
    code = ajouter(client, conn, reponse_automatique="à vérifier", interet="à vérifier")
    reponse = poster(client, code, champ, valeur)
    assert reponse.status_code == 200
    conn.commit()
    p = modeles.obtenir(conn, code)
    assert p[champ] == valeur
    assert modeles.champs_corriges(conn, p["id"]) == {champ}


def test_compteur_de_corrections(client, conn):
    code = ajouter(client, conn, reponse_automatique="à vérifier", interet="à vérifier")
    assert poster(client, code, "interet", "curieux").get_json()["corrections"] == 1
    assert poster(client, code, "reponse_automatique", "non").get_json()["corrections"] == 2
    assert poster(client, code, "interet", "aucun").get_json()["corrections"] == 2
    assert '<strong id="nb-corrections">2</strong>' in client.get("/a-verifier").get_data(as_text=True)


def test_le_cas_corrige_quitte_la_liste(client, conn):
    code = ajouter(client, conn, reponse_automatique="à vérifier")
    poster(client, code, "reponse_automatique", "non")
    conn.commit()
    assert f"<strong>{code}</strong>" not in client.get("/a-verifier").get_data(as_text=True)


@pytest.mark.parametrize("champ, valeur", [
    ("interet", "à vérifier"), ("interet", "beaucoup"), ("interet", ""), ("reponse_automatique", "à vérifier"),
    ("nom_entreprise", "Autre"), ("statut", "signé"), ("tarif_propose", "100"), ("acompte", "50"),
    ("interet", ["curieux"]), ("interet", True), (["interet"], "curieux"), ("interet; DROP TABLE prospects", "aucun"),
])
def test_valeurs_refusees(client, conn, champ, valeur):
    code = ajouter(client, conn, interet="à vérifier")
    avant = dict(modeles.obtenir(conn, code))
    reponse = poster(client, code, champ, valeur)
    assert reponse.status_code == 400
    conn.commit()
    assert dict(modeles.obtenir(conn, code)) == avant and modeles.nombre_corrections(conn) == 0


def test_prospect_inconnu(client):
    assert poster(client, "P999", "interet", "curieux").status_code == 404


def test_formulaire_classique_refuse(client, conn):
    code = ajouter(client, conn, interet="à vérifier")
    assert client.post(f"/a-verifier/{code}", data={"champ": "interet", "valeur": "curieux"}).status_code == 400


def test_autre_site_refuse(client, conn):
    code = ajouter(client, conn, interet="à vérifier")
    reponse = client.post(f"/a-verifier/{code}", json={"champ": "interet", "valeur": "curieux"},
                          headers={"Origin": "https://site-piege.example"})
    assert reponse.status_code == 403


def test_nom_echappe(client, conn):
    ajouter(client, conn, interet="à vérifier", nom_entreprise="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in client.get("/a-verifier").get_data(as_text=True)


def test_ecriture_refuse_une_colonne_libre(conn):
    with pytest.raises(ValueError):
        modeles.ecrire_champ_analyse(conn, 1, "nom_entreprise", "x")
