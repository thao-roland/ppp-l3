"""Page « Importer un export Facebook »."""

from flask import Blueprint, current_app, render_template, request

import importation

bp = Blueprint("import_fb", __name__)


def _page(erreur=None, rapport=None, statut=200):
    exports = importation.lister_exports(current_app.config["DOSSIER_DONNEES"])
    page = render_template("import.html", exports=exports, erreur=erreur, rapport=rapport)
    return page, statut


@bp.get("/import")
def page_import():
    return _page()


@bp.post("/import")
def lancer_import():
    dossier = current_app.config["DOSSIER_DONNEES"]
    nom_export = request.form.get("export", "")
    # Seuls les dossiers présents dans exports_facebook/ sont acceptés
    # (impossible de viser un autre dossier de l'ordinateur).
    if nom_export not in importation.lister_exports(dossier):
        return _page(erreur="Choisis un export dans la liste.", statut=400)
    try:
        rapport = importation.importer(
            current_app.obtenir_conn(), dossier / "exports_facebook" / nom_export,
            request.form.get("mon_nom", "").strip() or None)
    except importation.ErreurImport as e:
        return _page(erreur=str(e), statut=400)
    return _page(rapport=rapport)
