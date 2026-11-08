"""Page « Tableau de bord » : des totaux seulement."""

from flask import Blueprint, current_app, render_template

import modeles
import tableau

bp = Blueprint("tableau_bord", __name__)


@bp.app_template_filter("pourcent")
def filtre_pourcent(valeur):
    """Pourcentage à la française dans les pages : 46,9 %."""
    return tableau.format_pourcent(valeur)


@bp.get("/tableau")
def page_tableau():
    prospects = modeles.lister(current_app.obtenir_conn())
    return render_template("tableau.html", **tableau.construire(prospects))
