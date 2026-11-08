"""Page « Exports » : CSV anonymisé et Excel pour une période choisie.

Les fichiers sont téléchargés : l'outil n'écrit rien dans le dépôt.
"""

from flask import Blueprint, Response, current_app, render_template, request

import exports
import exports_excel
import modeles

bp = Blueprint("exports", __name__)

TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _page(erreur=None, statut=200):
    page = render_template("exports.html", erreur=erreur, colonnes=exports.COLONNES_CSV,
                           debut=request.args.get("debut", ""), fin=request.args.get("fin", ""))
    return page, statut


def _telechargement(contenu, type_fichier, nom):
    return Response(contenu, mimetype=type_fichier, headers={
        "Content-Disposition": f'attachment; filename="{nom}"',
        "Cache-Control": "no-store",
    })


def _prospects_de_la_periode():
    """Renvoie (prospects, début, fin, erreur)."""
    debut, fin, erreur = exports.lire_periode(request.args)
    if erreur:
        return None, None, None, erreur
    tous = modeles.lister(current_app.obtenir_conn())
    return exports.filtrer(tous, debut, fin), debut, fin, None


@bp.get("/exports")
def page_exports():
    return _page()


@bp.get("/exports/anonymise.csv")
def export_csv():
    prospects, debut, fin, erreur = _prospects_de_la_periode()
    if erreur:
        return _page(erreur, 400)
    return _telechargement(exports.csv_anonymise(prospects), "text/csv; charset=utf-8",
                           exports.nom_fichier("prospection_anonymise", debut, fin, "csv"))


@bp.get("/exports/rapport.xlsx")
def export_excel():
    prospects, debut, fin, erreur = _prospects_de_la_periode()
    if erreur:
        return _page(erreur, 400)
    return _telechargement(exports_excel.classeur(prospects, debut, fin), TYPE_XLSX,
                           exports.nom_fichier("prospection_rapport", debut, fin, "xlsx"))
