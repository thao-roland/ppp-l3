"""Relance l'analyse automatique sur la base existante. N'affiche QUE des nombres.

Exemples :
    python analyser_cli.py --simuler        # compte, sans rien enregistrer
    python analyser_cli.py                  # applique les règles

Analyse 100 % locale. Les corrections faites à la main ne sont jamais remplacées.
Le texte des réponses n'étant pas conservé en base, il est relu dans l'export.
"""

import sys

import db
import importation
import importer_cli


def afficher(rapport):
    """Affiche le rapport : des nombres, jamais de noms ni de messages."""
    if rapport["simulation"]:
        print("SIMULATION : rien n'a été enregistré.")
    print(f"Conversations lues          : {rapport['conversations']}")
    print(f"  illisibles                : {rapport['illisibles']}")
    print(f"Fiches analysées            : {rapport['deja_importees']}")
    print(f"  dont modifiées            : {rapport['fiches_mises_a_jour']}")
    print(f"Sans fiche (non importées)  : {rapport['sans_fiche']}")
    importer_cli.afficher_categories(rapport)


def main(argv=None):
    args = importer_cli.lire_arguments(argv)
    dossier = db.preparer_dossier(db.dossier_donnees())
    conn = db.connecter(db.chemin_base(dossier))
    try:
        db.initialiser(conn)
        export = importer_cli.choisir_export(importation.lister_exports(dossier), args.export)
        rapport = importation.analyser_base(
            conn, dossier / "exports_facebook" / export, args.mon_nom, args.simuler)
    except importation.ErreurImport as erreur:
        print(f"Erreur : {erreur}")  # ce message ne contient jamais de nom
        return 1
    finally:
        conn.close()
    afficher(rapport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
