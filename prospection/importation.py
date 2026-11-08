"""Import d'un export Facebook dans la base (crée prospects et relances)."""

from pathlib import Path

import facebook
import modeles


class ErreurImport(Exception):
    """Problème expliqué à l'utilisateur (le message ne contient jamais de nom)."""


def lister_exports(dossier_donnees):
    """Noms des exports présents dans <données>/exports_facebook/."""
    dossier = Path(dossier_donnees) / "exports_facebook"
    if not dossier.is_dir():
        return []
    return sorted(d.name for d in dossier.iterdir() if d.is_dir() and not d.is_symlink())


def _lire_toutes(dossiers):
    """Lit les conversations. Renvoie (conversations lisibles, nombre d'illisibles)."""
    lues = [facebook.lire_conversation(d) for d in dossiers]
    return [c for c in lues if c is not None], lues.count(None)


def _choisir_mon_nom(conversations, mon_nom):
    """Utilise le nom donné, sinon le devine ; refuse si c'est impossible."""
    nom = mon_nom or facebook.detecter_mon_nom(conversations)
    if not nom:
        raise ErreurImport("Je n'arrive pas à savoir quel nom est le tien : "
                           "indique ton nom Facebook dans le champ prévu.")
    if not any(nom in c["participants"] for c in conversations):
        raise ErreurImport("Ce nom n'apparaît dans aucune conversation de l'export.")
    return nom


def _deja_importee(conn, cle):
    ligne = conn.execute("SELECT 1 FROM prospects WHERE conversation_fb = ?", (cle,))
    return ligne.fetchone() is not None


def _enregistrer(conn, prospect):
    """Ajoute le prospect et ses relances (sans valider : voir importer)."""
    valeurs = dict.fromkeys(modeles.COLONNES)
    valeurs.update(
        nom_entreprise=prospect["nom_entreprise"], canal="Messenger",
        date_premier_message=prospect["date_premier_message"],
        texte_envoye=prospect["texte_envoye"], date_reponse=prospect["date_reponse"],
        statut=prospect["statut"], interet="aucun",
        dates_estimees=0,  # dates exactes, venues de Facebook
    )
    code = modeles.creer(conn, valeurs, conversation_fb=prospect["cle"], commit=False)
    prospect_id = modeles.obtenir(conn, code)["id"]
    for relance in prospect["relances"]:
        modeles.ajouter_relance(conn, prospect_id, relance, commit=False)
    return code


def importer(conn, dossier_export, mon_nom=None):
    """Importe un export. Tout est enregistré d'un coup, ou rien en cas d'erreur.

    Renvoie un rapport (des nombres et des codes P00X, jamais de noms).
    """
    dossiers = facebook.trouver_conversations(dossier_export)
    conversations, illisibles = _lire_toutes(dossiers)
    if not conversations:
        raise ErreurImport("Aucune conversation lisible dans ce dossier "
                           "(je cherche un dossier messages/inbox).")
    nom = _choisir_mon_nom(conversations, mon_nom)

    rapport = {"conversations": len(dossiers), "nouveaux": [], "deja_importees": 0,
               "groupes": 0, "sans_message_de_moi": 0, "illisibles": illisibles}
    try:
        for conversation in conversations:
            prospect, raison = facebook.analyser(conversation, nom)
            if prospect is None:
                rapport[raison] += 1
            elif _deja_importee(conn, prospect["cle"]):
                rapport["deja_importees"] += 1
            else:
                rapport["nouveaux"].append(_enregistrer(conn, prospect))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rapport
