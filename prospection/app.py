"""Application Flask : liste, ajout et modification des prospects.

Lancer en local :  python app.py   puis ouvrir http://127.0.0.1:5000
"""

import secrets
from urllib.parse import urlparse

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

import db
import modeles
import analyse_messages
import pages_a_verifier
import pages_exports
import pages_import
import pages_tableau
import scoring


def create_app(donnees=None):
    """Fabrique l'application.

    `donnees` = dossier des données réelles (hors dépôt). Par défaut il est lu
    dans CRM_DONNEES ; les tests passent un dossier temporaire.
    """
    app = Flask(__name__)
    # Clé aléatoire à chaque démarrage : sert seulement aux messages « enregistré ».
    app.secret_key = secrets.token_hex(16)

    dossier = db.preparer_dossier(db.dossier_donnees(donnees))
    app.config["DOSSIER_DONNEES"] = dossier
    app.config["CHEMIN_BASE"] = db.chemin_base(dossier)

    conn = db.connecter(app.config["CHEMIN_BASE"])
    db.initialiser(conn)
    conn.close()
    scoring.charger_regles()  # des règles abîmées se voient dès le démarrage
    analyse_messages.charger_regles()

    _brancher_base(app)
    _brancher_securite(app)
    _brancher_routes(app)
    app.register_blueprint(pages_import.bp)
    app.register_blueprint(pages_tableau.bp)
    app.register_blueprint(pages_exports.bp)
    app.register_blueprint(pages_a_verifier.bp)
    return app


def _brancher_base(app):
    """Une connexion par requête, fermée à la fin."""

    def obtenir_conn():
        if "conn" not in g:
            g.conn = db.connecter(app.config["CHEMIN_BASE"])
        return g.conn

    @app.teardown_appcontext
    def fermer_conn(_erreur):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    app.obtenir_conn = obtenir_conn


def _brancher_securite(app):
    """Refuse les envois de formulaires qui viennent d'un autre site (CSRF)."""

    @app.before_request
    def verifier_origine():
        if request.method != "POST":
            return
        origine = request.headers.get("Origin")
        if origine and urlparse(origine).netloc != request.host:
            abort(403)


def _valeurs_vides():
    """Valeurs de départ du formulaire d'ajout."""
    return {"interet": "aucun", "statut": "contacté", "dates_estimees": 0}


def _listes_formulaire():
    """Listes de choix affichées dans le formulaire."""
    return {
        "statuts": modeles.STATUTS, "interets": modeles.INTERETS,
        "canaux": modeles.CANAUX,
        "reponses_automatiques": modeles.REPONSES_AUTOMATIQUES,
    }


def _brancher_routes(app):
    def _donnees_scoring():
        """Prospects, dates des relances et règles (relues à chaque page)."""
        conn = app.obtenir_conn()
        return modeles.lister(conn), modeles.dates_relances(conn), scoring.charger_regles()

    @app.errorhandler(scoring.ErreurRegles)
    def regles_invalides(erreur):
        return render_template("erreur_regles.html", message=str(erreur)), 500

    @app.get("/")
    def accueil():
        return render_template("liste.html", prospects=scoring.noter(*_donnees_scoring()))

    @app.get("/relances")
    def relances_a_faire():
        prospects, relances, regles = _donnees_scoring()
        return render_template("relances.html", prospects=scoring.a_relancer(prospects, relances, regles),
                               delai=regles["relances"]["delai_jours"])

    @app.route("/prospects/nouveau", methods=["GET", "POST"])
    def nouveau():
        if request.method == "GET":
            return render_template("formulaire.html", valeurs=_valeurs_vides(),
                                   erreurs={}, prospect=None, **_listes_formulaire())
        valeurs, erreurs = modeles.valider(request.form)
        if erreurs:
            return _formulaire_avec_erreurs(valeurs, erreurs, None)
        code = modeles.creer(app.obtenir_conn(), valeurs)
        flash(f"Prospect {code} ajouté.")
        return redirect(url_for("accueil"))

    @app.route("/prospects/<code>/modifier", methods=["GET", "POST"])
    def modifier(code):
        conn = app.obtenir_conn()
        prospect = modeles.obtenir(conn, code) or abort(404)
        if request.method == "GET":
            return _formulaire(prospect, dict(prospect), {})
        valeurs, erreurs = modeles.valider(request.form)
        if erreurs:
            return _formulaire(prospect, valeurs, erreurs, 400)
        modeles.modifier(conn, code, valeurs)
        flash(f"Prospect {code} modifié.")
        return redirect(url_for("modifier", code=code))

    @app.post("/prospects/<code>/relances")
    def nouvelle_relance(code):
        conn = app.obtenir_conn()
        prospect = modeles.obtenir(conn, code) or abort(404)
        valeurs, erreurs = modeles.valider_relance(request.form)
        if erreurs:
            return _formulaire(prospect, dict(prospect), {}, 400, erreurs_relance=erreurs)
        modeles.ajouter_relance(conn, prospect["id"], valeurs)
        flash("Relance ajoutée.")
        return redirect(url_for("modifier", code=code))

    def _formulaire(prospect, valeurs, erreurs, statut=200, erreurs_relance=None):
        """Page du formulaire de modification (avec la liste des relances)."""
        relances = modeles.lister_relances(app.obtenir_conn(), prospect["id"])
        page = render_template(
            "formulaire.html", valeurs=valeurs, erreurs=erreurs, prospect=prospect,
            relances=relances, erreurs_relance=erreurs_relance or {},
            **_listes_formulaire())
        return page, statut

    def _formulaire_avec_erreurs(valeurs, erreurs, prospect):
        page = render_template("formulaire.html", valeurs=valeurs, erreurs=erreurs,
                               prospect=prospect, **_listes_formulaire())
        return page, 400


def lancer():
    """Démarrage réel : récupère l'ancienne base de l'étape 1, puis lance le serveur."""
    dossier = db.preparer_dossier(db.dossier_donnees())
    if db.migrer_ancienne_base(db.ANCIENNE_BASE, dossier):
        print("Ancienne base déplacée vers le dossier de données (hors dépôt).")
    # 127.0.0.1 = accessible seulement depuis cet ordinateur. Pas de mode debug.
    create_app(dossier).run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    lancer()
