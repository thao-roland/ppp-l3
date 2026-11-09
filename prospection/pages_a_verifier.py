"""Écran « À vérifier » : seulement les cas douteux de l'analyse automatique.

Un clic corrige un champ, sans recharger la page. La requête est en JSON : un
autre site ne peut pas l'envoyer à la place de mon navigateur.
"""

from flask import Blueprint, current_app, jsonify, render_template, request

import modeles

bp = Blueprint("a_verifier", __name__)


def cas_douteux(prospects):
    """Prospects avec un champ « à vérifier » : réponses douteuses d'abord, les plus récentes en tête."""
    douteux = [p for p in prospects if modeles.A_VERIFIER in (p["reponse_automatique"], p["interet"])]
    plus_recents = sorted(douteux, key=lambda p: p["date_reponse"] or "", reverse=True)
    return sorted(plus_recents, key=lambda p: p["reponse_automatique"] != modeles.A_VERIFIER)


def _erreur(message, statut):
    return jsonify(erreur=message), statut


@bp.get("/a-verifier")
def page():
    conn = current_app.obtenir_conn()
    return render_template(
        "a_verifier.html", prospects=cas_douteux(modeles.lister(conn)),
        choix=modeles.CORRECTIONS_POSSIBLES, a_verifier=modeles.A_VERIFIER,
        nb_corrections=modeles.nombre_corrections(conn))


@bp.post("/a-verifier/<code>")
def corriger(code):
    donnees = request.get_json(silent=True) if request.is_json else None
    if not isinstance(donnees, dict):
        return _erreur("Requête non reconnue.", 400)
    conn = current_app.obtenir_conn()
    prospect = modeles.obtenir(conn, code)
    if prospect is None:
        return _erreur("Prospect introuvable.", 404)
    champ, valeur = donnees.get("champ"), donnees.get("valeur")
    if not modeles.correction_valide(champ, valeur):
        return _erreur("Champ ou valeur non reconnu.", 400)
    modeles.corriger(conn, prospect["id"], champ, valeur)
    return jsonify(champ=champ, valeur=valeur, corrections=modeles.nombre_corrections(conn))
