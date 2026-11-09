"""Tests de l'étape 1 : base SQLite + ajout / modification d'un prospect.

Toutes les données ici sont fictives.
"""

from conftest import formulaire_valide


def ajouter(client, **changements):
    return client.post("/prospects/nouveau", data=formulaire_valide(**changements))


# --- Base de données ---------------------------------------------------------
def test_les_tables_sont_creees(conn):
    tables = {l["name"] for l in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"prospects", "relances"} <= tables


def test_page_vide_au_depart(client):
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert "Aucun prospect" in reponse.get_data(as_text=True)


# --- Ajout -------------------------------------------------------------------
def test_ajout_cree_le_code_p001_puis_p002(client, conn):
    assert ajouter(client).status_code == 302
    ajouter(client, nom_entreprise="Garage Exemple")
    codes = [l["code"] for l in conn.execute("SELECT code FROM prospects ORDER BY id")]
    assert codes == ["P001", "P002"]


def test_ajout_enregistre_tous_les_champs(client, conn):
    ajouter(client, tarif_propose="450", acompte="150", a_deja_site="non",
            date_reponse="2026-10-03", interet="curieux", statut="a répondu",
            dates_estimees="1")
    p = conn.execute("SELECT * FROM prospects WHERE code = 'P001'").fetchone()
    assert p["nom_entreprise"] == "Boulangerie Test"
    assert (p["metier"], p["ville"], p["canal"]) == ("boulanger", "Valenciennes", "Messenger")
    assert p["date_premier_message"] == "2026-10-01"
    assert p["version_message"] == "A"
    assert p["texte_envoye"].startswith("Bonjour")
    assert (p["tarif_propose"], p["acompte"]) == (450, 150)
    assert p["a_deja_site"] == 0
    assert p["interet"] == "curieux" and p["statut"] == "a répondu"
    assert p["dates_estimees"] == 1


def test_champs_vides_deviennent_null_avec_valeurs_par_defaut(client, conn):
    client.post("/prospects/nouveau", data={"nom_entreprise": "Juste un nom"})
    p = conn.execute("SELECT * FROM prospects").fetchone()
    assert p["metier"] is None and p["tarif_propose"] is None and p["a_deja_site"] is None
    assert p["interet"] == "aucun" and p["statut"] == "contacté"


def test_ajout_apparait_dans_la_liste(client):
    ajouter(client)
    page = client.get("/").get_data(as_text=True)
    assert "P001" in page and "Boulangerie Test" in page


# --- Refus des données incorrectes -------------------------------------------
def test_nom_obligatoire(client, conn):
    reponse = ajouter(client, nom_entreprise="   ")
    assert reponse.status_code == 400
    assert "obligatoire" in reponse.get_data(as_text=True)
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 0


def test_valeurs_non_autorisees_refusees(client, conn):
    for champ, mauvaise in [("statut", "inconnu"), ("interet", "beaucoup"),
                            ("version_message", "A1"), ("canal", "Pigeon")]:
        assert ajouter(client, **{champ: mauvaise}).status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 0


def test_date_invalide_refusee(client):
    assert ajouter(client, date_premier_message="31/02/2026").status_code == 400


def test_reponse_avant_premier_message_refusee(client):
    reponse = ajouter(client, date_premier_message="2026-10-10", date_reponse="2026-10-05")
    assert reponse.status_code == 400


def test_montants_negatifs_ou_texte_refuses(client):
    assert ajouter(client, tarif_propose="-5").status_code == 400
    assert ajouter(client, acompte="abc").status_code == 400
    assert ajouter(client, acompte="12.5").status_code == 400


def test_erreur_garde_ce_qui_a_ete_saisi(client):
    page = ajouter(client, nom_entreprise="", ville="Denain").get_data(as_text=True)
    assert "Denain" in page


# --- Modification ------------------------------------------------------------
def test_modification_change_les_champs(client, conn):
    ajouter(client)
    reponse = client.post("/prospects/P001/modifier", data=formulaire_valide(
        statut="signé", interet="demande de prix", tarif_propose="500"))
    assert reponse.status_code == 302
    p = conn.execute("SELECT * FROM prospects WHERE code = 'P001'").fetchone()
    assert (p["statut"], p["interet"], p["tarif_propose"]) == ("signé", "demande de prix", 500)


def test_modification_ne_change_pas_le_code(client, conn):
    ajouter(client)
    client.post("/prospects/P001/modifier", data=formulaire_valide(nom_entreprise="Autre nom"))
    assert conn.execute("SELECT code FROM prospects").fetchone()["code"] == "P001"


def test_page_modification_affiche_les_valeurs(client):
    ajouter(client, ville="Denain")
    page = client.get("/prospects/P001/modifier").get_data(as_text=True)
    assert "Denain" in page and "Modifier P001" in page


def test_modification_invalide_refusee_et_rien_change(client, conn):
    ajouter(client)
    reponse = client.post("/prospects/P001/modifier", data=formulaire_valide(statut="nimporte"))
    assert reponse.status_code == 400
    assert conn.execute("SELECT statut FROM prospects").fetchone()["statut"] == "contacté"


def test_prospect_inexistant_donne_404(client):
    assert client.get("/prospects/P999/modifier").status_code == 404
    assert client.post("/prospects/P999/modifier", data=formulaire_valide()).status_code == 404


# --- Relances ----------------------------------------------------------------
def test_ajout_d_une_relance(client, conn):
    ajouter(client)
    client.post("/prospects/P001/relances", data={"date": "2026-10-08", "texte": "Petit rappel"})
    r = conn.execute("SELECT * FROM relances").fetchone()
    assert (r["date"], r["texte"]) == ("2026-10-08", "Petit rappel")
    assert "Petit rappel" in client.get("/prospects/P001/modifier").get_data(as_text=True)


def test_relance_sans_date_ou_date_invalide_refusee(client, conn):
    ajouter(client)
    assert client.post("/prospects/P001/relances", data={"texte": "x"}).status_code == 400
    assert client.post("/prospects/P001/relances", data={"date": "hier"}).status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM relances").fetchone()[0] == 0


# --- Sécurité ----------------------------------------------------------------
def test_les_caracteres_speciaux_sont_neutralises(client, conn):
    nom = "<script>alert(1)</script>'); DROP TABLE prospects;--"
    ajouter(client, nom_entreprise=nom)
    page = client.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page  # affiché échappé, pas exécuté
    assert conn.execute("SELECT nom_entreprise FROM prospects").fetchone()[0] == nom


def test_envoi_depuis_un_autre_site_refuse(client, conn):
    reponse = client.post("/prospects/nouveau", data=formulaire_valide(),
                          headers={"Origin": "http://site-malveillant.example"})
    assert reponse.status_code == 403
    assert conn.execute("SELECT COUNT(*) FROM prospects").fetchone()[0] == 0
