"""Import d'un export Facebook en ligne de commande. N'affiche QUE des nombres.

Exemples :
    python importer_cli.py --simuler        # compte, sans rien enregistrer
    python importer_cli.py                  # importe pour de bon
    python importer_cli.py --export messages --mon-nom "Prénom Nom"

Les données sont lues dans le dossier désigné par CRM_DONNEES (hors dépôt).
"""

import argparse
import sys

import db
import importation


def lire_arguments(argv=None):
    parseur = argparse.ArgumentParser(description="Importer un export Facebook (nombres seulement).")
    parseur.add_argument("--export", help="nom du dossier dans exports_facebook/ (inutile s'il n'y en a qu'un)")
    parseur.add_argument("--mon-nom", help="mon nom Facebook (sinon : deviné)")
    parseur.add_argument("--simuler", action="store_true", help="ne rien enregistrer, juste compter")
    return parseur.parse_args(argv)


def choisir_export(exports, demande):
    """L'export demandé, ou l'unique export présent."""
    if demande:
        if demande not in exports:
            raise importation.ErreurImport("Export introuvable dans exports_facebook/.")
        return demande
    if len(exports) != 1:
        raise importation.ErreurImport(
            f"{len(exports)} exports trouvés dans exports_facebook/ : précise --export.")
    return exports[0]


def afficher_categories(rapport):
    """Bilan de toute la base : des nombres uniquement."""
    categories = rapport["categories"]
    print("Bilan de la base (un prospect peut compter dans plusieurs lignes) :")
    print(f"  réponses automatiques     : {categories['auto']}")
    print(f"  vraies réponses           : {categories['vraies']}")
    print(f"  intéressés (demande prix) : {categories['interesses']}")
    print(f"  curieux                   : {categories['curieux']}")
    print(f"  pas intéressés            : {categories['pas_interesses']}")
    print(f"  à vérifier                : {categories['a_verifier']}")
    print(f"  sans réponse              : {categories['sans_reponse']}")
    print(f"Versions de message         : {rapport['versions']}")


def afficher(rapport):
    """Affiche le rapport : des nombres, jamais de noms ni de messages."""
    if rapport["simulation"]:
        print("SIMULATION : rien n'a été enregistré.")
    print(f"Conversations trouvées      : {rapport['conversations']}")
    print(f"  illisibles                : {rapport['illisibles']}")
    print(f"Prospects créés             : {len(rapport['nouveaux'])}")
    print(f"  dont avec une réponse     : {rapport['reponses']}")
    print(f"Relances créées             : {rapport['relances']}")
    print(f"Fiches mises à jour         : {rapport['fiches_mises_a_jour']}")
    afficher_categories(rapport)
    print("Conversations ignorées :")
    print(f"  déjà importées            : {rapport['deja_importees']}")
    print(f"  groupes                   : {rapport['groupes']}")
    print(f"  sans message de moi       : {rapport['sans_message_de_moi']}")


def main(argv=None):
    args = lire_arguments(argv)
    dossier = db.preparer_dossier(db.dossier_donnees())
    db.migrer_ancienne_base(db.ANCIENNE_BASE, dossier)
    conn = db.connecter(db.chemin_base(dossier))
    try:
        db.initialiser(conn)
        export = choisir_export(importation.lister_exports(dossier), args.export)
        rapport = importation.importer(
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
