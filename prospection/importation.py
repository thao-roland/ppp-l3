"""Import d'un export Facebook dans la base (crée prospects et relances)."""

from pathlib import Path

import facebook
import modeles


CLES_DETECTION = {"non": "auto_non", "oui": "auto_oui", "à vérifier": "auto_a_verifier"}


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
        reponse_automatique=prospect["reponse_automatique"],
    )
    code = modeles.creer(conn, valeurs, conversation_fb=prospect["cle"], commit=False)
    prospect_id = modeles.obtenir(conn, code)["id"]
    for relance in prospect["relances"]:
        modeles.ajouter_relance(conn, prospect_id, relance, commit=False)
    return code


def _completer_detection(conn, prospect):
    """Remplit la détection d'un prospect déjà importé, si elle est encore vide.

    Une valeur déjà présente (donc une correction à la main) n'est jamais remplacée.
    Renvoie 1 si la fiche a été complétée, sinon 0.
    """
    if prospect["reponse_automatique"] is None:
        return 0
    return conn.execute(
        "UPDATE prospects SET reponse_automatique = ? "
        "WHERE conversation_fb = ? AND reponse_automatique IS NULL AND date_reponse IS NOT NULL",
        (prospect["reponse_automatique"], prospect["cle"])).rowcount


def _compter_detection(rapport, prospect):
    """Ajoute au rapport le résultat de la détection, sans aucun texte."""
    cle = CLES_DETECTION.get(prospect["reponse_automatique"])
    if cle:
        rapport[cle] += 1


def importer(conn, dossier_export, mon_nom=None, simuler=False):
    """Importe un export. Tout est enregistré d'un coup, ou rien en cas d'erreur.

    simuler=True : fait tous les calculs mais n'enregistre rien (pour voir les nombres).
    Renvoie un rapport (des nombres et des codes P00X, jamais de noms).
    """
    dossiers = facebook.trouver_conversations(dossier_export)
    conversations, illisibles = _lire_toutes(dossiers)
    if not conversations:
        raise ErreurImport("Aucune conversation lisible dans ce dossier "
                           "(je cherche un dossier messages/inbox).")
    nom = _choisir_mon_nom(conversations, mon_nom)

    rapport = {"conversations": len(dossiers), "nouveaux": [], "deja_importees": 0,
               "groupes": 0, "sans_message_de_moi": 0, "illisibles": illisibles,
               "relances": 0, "reponses": 0, "simulation": simuler,
               "auto_non": 0, "auto_oui": 0, "auto_a_verifier": 0, "detections_completees": 0}
    try:
        for conversation in conversations:
            prospect, raison = facebook.analyser(conversation, nom)
            if prospect is None:
                rapport[raison] += 1
                continue
            _compter_detection(rapport, prospect)
            if _deja_importee(conn, prospect["cle"]):
                rapport["deja_importees"] += 1
                rapport["detections_completees"] += _completer_detection(conn, prospect)
            else:
                rapport["nouveaux"].append(_enregistrer(conn, prospect))
                rapport["relances"] += len(prospect["relances"])
                rapport["reponses"] += 1 if prospect["date_reponse"] else 0
        conn.rollback() if simuler else conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rapport
