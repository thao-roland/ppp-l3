"""Tests de l'étape 2 : import de l'export Facebook.

Le faux export (tests/faux_export_facebook/) ne contient que des noms et des
messages inventés. Il imite le format Facebook, y compris l'encodage cassé.
"""

import json
import shutil

import pytest

import db
import facebook
import importation
from conftest import FAUX_EXPORT

MOI = "Utilisateur Test"


@pytest.fixture
def conversations():
    """Toutes les conversations du faux export, déjà lues."""
    dossiers = facebook.trouver_conversations(FAUX_EXPORT)
    return [facebook.lire_conversation(d) for d in dossiers]


def prospect(conn, nom):
    return conn.execute("SELECT * FROM prospects WHERE nom_entreprise = ?", (nom,)).fetchone()


def relances(conn, nom):
    return conn.execute(
        "SELECT date, texte FROM relances WHERE prospect_id = ? ORDER BY date",
        (prospect(conn, nom)["id"],)).fetchall()


@pytest.fixture
def export_installe(dossier_donnees, client):
    """Copie le faux export dans <données>/exports_facebook/export_test."""
    destination = dossier_donnees / "exports_facebook" / "export_test"
    shutil.copytree(FAUX_EXPORT, destination)
    return destination


# --- Encodage et lecture -----------------------------------------------------
def test_reparation_des_accents_casses():
    assert facebook.reparer_texte("Je crÃ©e des sites") == "Je crée des sites"
    assert facebook.reparer_texte("Boulangerie Ã\u0089toile") == "Boulangerie Étoile"


def test_un_texte_deja_correct_n_est_pas_modifie():
    assert facebook.reparer_texte("Je crée des sites") == "Je crée des sites"
    assert facebook.reparer_texte("Bonjour 😀 œuvre") == "Bonjour 😀 œuvre"
    assert facebook.reparer_texte("Simple ASCII") == "Simple ASCII"


def test_toutes_les_conversations_sont_trouvees():
    # 7 conversations : 6 dans inbox + 1 dans message_requests
    assert len(facebook.trouver_conversations(FAUX_EXPORT)) == 7


def test_nouvelle_presentation_de_l_export_aussi(tmp_path):
    """Les exports récents mettent tout sous your_facebook_activity/."""
    cible = tmp_path / "your_facebook_activity"
    shutil.copytree(FAUX_EXPORT / "messages", cible / "messages")
    assert len(facebook.trouver_conversations(tmp_path)) == 7


def test_conversation_repartie_sur_plusieurs_fichiers_fusionnee(conversations):
    boulangerie = next(c for c in conversations if "Boulangerie Fictive Étoile" in c["participants"])
    assert len(boulangerie["messages"]) == 3  # 1 dans message_2.json + 2 dans message_1.json
    horodatages = [m[0] for m in boulangerie["messages"]]
    assert horodatages == sorted(horodatages)


def test_les_noms_sont_repares_a_la_lecture(conversations):
    noms = {n for c in conversations for n in c["participants"]}
    assert "Garage Imaginaire Léo" in noms and "Coiffure Inventée Chloé" in noms
    assert not any("Ã" in n for n in noms)


def test_mon_nom_est_devine(conversations):
    assert facebook.detecter_mon_nom(conversations) == MOI


def test_mon_nom_non_devinable_avec_une_seule_conversation(conversations):
    assert facebook.detecter_mon_nom(conversations[:1]) is None


# --- Règles de transformation ------------------------------------------------
def analyser(conversations, nom_autre):
    conv = next(c for c in conversations if nom_autre in c["participants"])
    return facebook.analyser(conv, MOI)


def test_conversation_avec_reponse(conversations):
    p, _ = analyser(conversations, "Boulangerie Fictive Étoile")
    assert p["date_premier_message"] == "2026-10-01"
    assert p["texte_envoye"].startswith("Bonjour, je crée des sites web")
    assert p["date_reponse"] == "2026-10-02"
    assert p["relances"] == []  # mon message du 2 octobre suit une réponse : pas une relance
    assert p["statut"] == "a répondu"


def test_relances_sans_reponse(conversations):
    p, _ = analyser(conversations, "Garage Imaginaire Léo")
    assert [r["date"] for r in p["relances"]] == ["2026-10-12", "2026-10-20"]
    assert p["relances"][1]["texte"] is None  # message sans texte (photo)
    assert p["date_reponse"] is None and p["statut"] == "relancé"


def test_sans_relance_ni_reponse_statut_contacte(conversations):
    p, _ = analyser(conversations, "Pizzeria Fictive Mélanie")
    assert p["statut"] == "contacté" and p["relances"] == []


def test_la_date_suit_l_heure_de_paris(conversations):
    # 22h30 UTC le 7 octobre = 00h30 le 8 octobre à Paris
    p, _ = analyser(conversations, "Coiffure Inventée Chloé")
    assert p["date_premier_message"] == "2026-10-08"


def test_la_reponse_compte_apres_mon_premier_message(conversations):
    # L'autre avait écrit le 28 septembre, avant moi : la réponse est celle du 3 octobre.
    p, _ = analyser(conversations, "Atelier Fictif Noël")
    assert p["date_premier_message"] == "2026-10-02"
    assert p["date_reponse"] == "2026-10-03"


def test_groupe_et_conversation_sans_message_de_moi_ignores(conversations):
    assert analyser(conversations, "Fictif Alpha") == (None, "groupes")
    assert analyser(conversations, "Cabinet Fictif Zoé") == (None, "sans_message_de_moi")


def test_delai_minimum_entre_relances(conversations, monkeypatch):
    conv = {"cle": "x", "participants": ["Autre", MOI], "messages": [
        (1_000_000_000_000, MOI, "1er"), (1_000_000_060_000, MOI, "juste après"),
        (1_000_100_000_000, MOI, "3 jours après")]}
    assert len(facebook.analyser(conv, MOI)[0]["relances"]) == 2
    monkeypatch.setattr(facebook, "DELAI_MIN_RELANCE_HEURES", 12)
    assert len(facebook.analyser(conv, MOI)[0]["relances"]) == 1


# --- Import en base ----------------------------------------------------------
def test_import_cree_les_prospects(client, conn):
    rapport = importation.importer(conn, FAUX_EXPORT)
    assert len(rapport["nouveaux"]) == 5
    assert rapport["groupes"] == 1 and rapport["sans_message_de_moi"] == 1
    assert rapport["conversations"] == 7 and rapport["illisibles"] == 0
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 5


def test_import_remplit_les_champs(client, conn):
    importation.importer(conn, FAUX_EXPORT)
    p = prospect(conn, "Boulangerie Fictive Étoile")
    assert p["code"].startswith("P") and p["canal"] == "Messenger"
    assert p["date_premier_message"] == "2026-10-01" and p["date_reponse"] == "2026-10-02"
    assert p["statut"] == "a répondu" and p["interet"] == "aucun"
    assert p["dates_estimees"] == 0  # dates exactes : pas « estimées »
    assert p["version_message"] is None and p["conversation_fb"] == "1000000001"
    assert [(r["date"], r["texte"]) for r in relances(conn, "Garage Imaginaire Léo")][0][0] == "2026-10-12"


def test_les_codes_sont_automatiques_et_a_la_suite(client, conn):
    client.post("/prospects/nouveau", data={"nom_entreprise": "Saisi à la main"})
    importation.importer(conn, FAUX_EXPORT)
    codes = [l["code"] for l in conn.execute("SELECT code FROM prospects ORDER BY id")]
    assert codes == ["P001", "P002", "P003", "P004", "P005", "P006"]


def test_jamais_deux_fois_la_meme_conversation(client, conn):
    importation.importer(conn, FAUX_EXPORT)
    rapport = importation.importer(conn, FAUX_EXPORT)
    assert rapport["nouveaux"] == [] and rapport["deja_importees"] == 5
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 5
    assert conn.execute("SELECT COUNT(*) FROM relances").fetchone()[0] == 2


def test_la_base_refuse_un_doublon_meme_en_contournant_le_code(client, conn):
    importation.importer(conn, FAUX_EXPORT)
    with pytest.raises(Exception):
        conn.execute("INSERT INTO prospects (code, nom_entreprise, conversation_fb) "
                     "VALUES ('P900', 'X', '1000000001')")


def test_un_second_export_ajoute_seulement_les_nouvelles_conversations(client, conn, tmp_path):
    partiel = tmp_path / "partiel"
    shutil.copytree(FAUX_EXPORT, partiel)
    shutil.rmtree(partiel / "messages" / "message_requests")
    assert len(importation.importer(conn, partiel)["nouveaux"]) == 4
    rapport = importation.importer(conn, FAUX_EXPORT)
    assert len(rapport["nouveaux"]) == 1 and rapport["deja_importees"] == 4


def test_fichier_abime_ignore_sans_bloquer_le_reste(client, conn, tmp_path):
    copie = tmp_path / "abime"
    shutil.copytree(FAUX_EXPORT, copie)
    (copie / "messages/inbox/garageimaginaireleo_1000000002/message_1.json").write_text("{pas du json")
    rapport = importation.importer(conn, copie)
    assert rapport["illisibles"] == 1 and len(rapport["nouveaux"]) == 4


def test_erreur_en_cours_d_import_n_enregistre_rien(client, conn, monkeypatch):
    appels = {"n": 0}
    vrai = importation._enregistrer

    def en_panne(connexion, prospect_):
        appels["n"] += 1
        if appels["n"] == 3:
            raise RuntimeError("panne")
        return vrai(connexion, prospect_)

    monkeypatch.setattr(importation, "_enregistrer", en_panne)
    with pytest.raises(RuntimeError):
        importation.importer(conn, FAUX_EXPORT)
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 0


def test_dossier_sans_conversation_refuse(client, conn, tmp_path):
    with pytest.raises(importation.ErreurImport):
        importation.importer(conn, tmp_path)


def test_mon_nom_a_donner_si_impossible_a_deviner(client, conn, tmp_path):
    une_seule = tmp_path / "seule"
    (une_seule / "messages" / "inbox").mkdir(parents=True)
    shutil.copytree(FAUX_EXPORT / "messages/inbox/garageimaginaireleo_1000000002",
                    une_seule / "messages/inbox/garageimaginaireleo_1000000002")
    with pytest.raises(importation.ErreurImport):
        importation.importer(conn, une_seule)
    assert len(importation.importer(conn, une_seule, mon_nom=MOI)["nouveaux"]) == 1


def test_nom_inconnu_refuse(client, conn):
    with pytest.raises(importation.ErreurImport):
        importation.importer(conn, FAUX_EXPORT, mon_nom="Quelqu'un D'autre")


# --- Interface ---------------------------------------------------------------
def test_bouton_importer_present_dans_l_interface(client):
    page = client.get("/").get_data(as_text=True)
    assert "Importer un export Facebook" in page and 'href="/import"' in page


def test_page_import_sans_export(client):
    assert "Aucun export trouvé" in client.get("/import").get_data(as_text=True)


def test_page_import_liste_les_exports(client, export_installe):
    assert "export_test" in client.get("/import").get_data(as_text=True)


def test_import_par_l_interface(client, conn, export_installe):
    reponse = client.post("/import", data={"export": "export_test"})
    assert reponse.status_code == 200
    page = reponse.get_data(as_text=True)
    assert "5</strong> nouveau(x) prospect(s)" in page
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 5
    assert "Garage Imaginaire Léo" not in page  # le rapport ne montre jamais de noms
    # second clic : rien de nouveau
    page = client.post("/import", data={"export": "export_test"}).get_data(as_text=True)
    assert "0</strong> nouveau(x)" in page and "Déjà importées avant : 5" in page
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 5


def test_import_refuse_un_dossier_hors_de_la_liste(client, export_installe):
    for mauvais in ("../exports_prives", "../../..", "/etc", "", "export_inconnu"):
        assert client.post("/import", data={"export": mauvais}).status_code == 400


def test_import_depuis_un_autre_site_refuse(client, export_installe):
    reponse = client.post("/import", data={"export": "export_test"},
                          headers={"Origin": "http://site-malveillant.example"})
    assert reponse.status_code == 403


def test_message_d_erreur_clair_sans_nom(client, dossier_donnees):
    (dossier_donnees / "exports_facebook" / "vide").mkdir()
    reponse = client.post("/import", data={"export": "vide"})
    assert reponse.status_code == 400
    assert "Aucune conversation lisible" in reponse.get_data(as_text=True)


# --- Le faux export ne contient que des données inventées --------------------
def test_le_faux_export_ne_contient_que_des_noms_inventes():
    autorises = {MOI, "Boulangerie Fictive Étoile", "Garage Imaginaire Léo",
                 "Coiffure Inventée Chloé", "Cabinet Fictif Zoé", "Atelier Fictif Noël",
                 "Pizzeria Fictive Mélanie", "Fictif Alpha", "Fictif Bêta"}
    for fichier in FAUX_EXPORT.rglob("*.json"):
        donnees = facebook.reparer(json.loads(fichier.read_text(encoding="utf-8")))
        noms = {p["name"] for p in donnees["participants"]}
        noms |= {m["sender_name"] for m in donnees["messages"]}
        assert noms <= autorises, f"nom non prévu dans {fichier.name}"
