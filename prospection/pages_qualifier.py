"""Écran « Qualifier » : compléter vite les prospects qui ont répondu.

Chaque clic enregistre un seul champ, sans recharger la page. La requête est en
JSON : un autre site ne peut pas l'envoyer à la place de mon navigateur.
"""

from flask import Blueprint, current_app, jsonify, render_template, request

import modeles
import tableau

bp = Blueprint("qualifier", __name__)

# Ce qui demande le plus d'attention arrive en premier.
ORDRE_CATEGORIES = {"a_verifier": 0, "automatique": 1, "vraie": 2}


def a_qualifier(prospects):
    """Prospects qui ont répondu : à vérifier, puis automatiques, puis vraies réponses."""
    avec_reponse = [p for p in prospects if tableau.categorie_reponse(p) != "aucune"]
    plus_recents = sorted(avec_reponse, key=lambda p: p["date_reponse"] or "", reverse=True)
    return sorted(plus_recents, key=lambda p: ORDRE_CATEGORIES[tableau.categorie_reponse(p)])


def _erreur(message, statut):
    return jsonify(erreur=message), statut


@bp.get("/qualifier")
def page_qualifier():
    prospects = a_qualifier(modeles.lister(current_app.obtenir_conn()))
    return render_template(
        "qualifier.html", prospects=prospects, interets=modeles.INTERETS, versions=modeles.VERSIONS,
        reponses_automatiques=modeles.REPONSES_AUTOMATIQUES,
        nb_a_verifier=sum(p["reponse_automatique"] == "à vérifier" for p in prospects))


@bp.post("/qualifier/<code>")
def enregistrer(code):
    donnees = request.get_json(silent=True) if request.is_json else None
    if not isinstance(donnees, dict):
        return _erreur("Requête non reconnue.", 400)
    conn = current_app.obtenir_conn()
    if modeles.obtenir(conn, code) is None:
        return _erreur("Prospect introuvable.", 404)
    resultat, erreur = modeles.valider_champ(donnees.get("champ"), donnees.get("valeur"))
    if erreur:
        return _erreur(erreur, 400)
    colonne, valeur = resultat
    modeles.mettre_a_jour_champ(conn, code, colonne, valeur)
    return jsonify(champ=donnees["champ"], colonne=colonne, valeur=valeur)
