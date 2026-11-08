"""Pages « Tableau de bord » et « Analyse » : des totaux seulement."""

from flask import Blueprint, current_app, render_template

import analyse
import modeles
import tableau

bp = Blueprint("tableau_bord", __name__)


@bp.app_template_filter("pourcent")
def filtre_pourcent(valeur):
    """Pourcentage à la française dans les pages : 46,9 %."""
    return tableau.format_pourcent(valeur)


@bp.app_template_filter("valeur_p")
def filtre_valeur_p(valeur):
    """Valeur p à la française dans les pages : 0,012."""
    return "—" if valeur is None else analyse.format_p(valeur)


@bp.get("/tableau")
def page_tableau():
    prospects = modeles.lister(current_app.obtenir_conn())
    return render_template("tableau.html", **tableau.construire(prospects))


@bp.get("/analyse")
def page_analyse():
    prospects = modeles.lister(current_app.obtenir_conn())
    return render_template("analyse.html", **analyse.construire(prospects))
