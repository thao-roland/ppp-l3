"""Import d'un export Facebook et analyse automatique des conversations."""

from pathlib import Path

import analyse_messages
import facebook
import modeles
import tableau


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


def _enregistrer(conn, prospect, resultat):
    """Ajoute le prospect et ses relances (sans valider : voir _traiter)."""
    valeurs = dict.fromkeys(modeles.COLONNES)
    valeurs.update(
        nom_entreprise=prospect["nom_entreprise"], canal="Messenger",
        date_premier_message=prospect["date_premier_message"],
        texte_envoye=prospect["texte_envoye"], date_reponse=prospect["date_reponse"],
        statut=prospect["statut"],
        dates_estimees=0,  # dates exactes, venues de Facebook
        **resultat,
    )
    code = modeles.creer(conn, valeurs, conversation_fb=prospect["cle"], commit=False)
    prospect_id = modeles.obtenir(conn, code)["id"]
    for relance in prospect["relances"]:
        modeles.ajouter_relance(conn, prospect_id, relance, commit=False)
    return code


def _appliquer(conn, cle, resultat):
    """Met à jour une fiche déjà importée, sans toucher aux champs corrigés à la main.

    Renvoie 1 si la fiche a changé, sinon 0.
    """
    ligne = conn.execute("SELECT * FROM prospects WHERE conversation_fb = ?", (cle,)).fetchone()
    corriges = modeles.champs_corriges(conn, ligne["id"])
    changements = {c: v for c, v in resultat.items() if c not in corriges and ligne[c] != v}
    for colonne, valeur in changements.items():
        modeles.ecrire_champ_analyse(conn, ligne["id"], colonne, valeur)
    return int(bool(changements))


def _versions(conn, prospects):
    """{clé de conversation: version}, selon le texte exact de mon premier message.

    Un texte nouveau reçoit la lettre suivante, dans l'ordre chronologique.
    La correspondance est conservée : une lettre ne change pas d'une analyse à l'autre.
    """
    connues = {l["texte"]: l["code"] for l in conn.execute("SELECT texte, code FROM versions_message")}
    versions = {}
    for prospect in sorted(prospects, key=lambda p: p["horodatage_premier"]):
        texte = prospect["texte_envoye"]
        if texte is None:
            continue
        if texte not in connues:
            connues[texte] = analyse_messages.code_version(len(connues))
            conn.execute("INSERT INTO versions_message (texte, code) VALUES (?, ?)", (texte, connues[texte]))
        versions[prospect["cle"]] = connues[texte]
    return versions


def _preparer(dossier_export, mon_nom):
    """Lit l'export. Renvoie (dossiers, conversations, illisibles, mon nom, règles)."""
    dossiers = facebook.trouver_conversations(dossier_export)
    conversations, illisibles = _lire_toutes(dossiers)
    if not conversations:
        raise ErreurImport("Aucune conversation lisible dans ce dossier "
                           "(je cherche un dossier messages/inbox).")
    try:
        regles = analyse_messages.charger_regles()
    except analyse_messages.ErreurRegles as erreur:
        raise ErreurImport(str(erreur)) from erreur
    return dossiers, conversations, illisibles, _choisir_mon_nom(conversations, mon_nom), regles


def _trier(conn, conversations, nom, creer, rapport):
    """Garde les conversations à traiter : [(conversation, prospect)]."""
    a_traiter = []
    for conversation in conversations:
        prospect, raison = facebook.analyser(conversation, nom)
        if prospect is None:
            rapport[raison] += 1
        elif creer or _deja_importee(conn, prospect["cle"]):
            a_traiter.append((conversation, prospect))
        else:
            rapport["sans_fiche"] += 1
    return a_traiter


def _traiter(conn, conversations, nom, regles, rapport, creer):
    """Analyse et enregistre. Tout est validé d'un coup, ou rien en cas d'erreur."""
    try:
        a_traiter = _trier(conn, conversations, nom, creer, rapport)
        versions = _versions(conn, [p for _, p in a_traiter])
        for conversation, prospect in a_traiter:
            resultat = {**analyse_messages.analyser(conversation, nom, regles),
                        "version_message": versions.get(prospect["cle"])}
            if _deja_importee(conn, prospect["cle"]):
                rapport["deja_importees"] += 1
                rapport["fiches_mises_a_jour"] += _appliquer(conn, prospect["cle"], resultat)
            else:
                rapport["nouveaux"].append(_enregistrer(conn, prospect, resultat))
                rapport["relances"] += len(prospect["relances"])
                rapport["reponses"] += 1 if prospect["date_reponse"] else 0
        rapport["categories"] = tableau.compter_categories(modeles.lister(conn))
        rapport["versions"] = conn.execute("SELECT COUNT(*) FROM versions_message").fetchone()[0]
        conn.rollback() if rapport["simulation"] else conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rapport


def _rapport_vide(dossiers, illisibles, simuler):
    return {"conversations": len(dossiers), "nouveaux": [], "deja_importees": 0,
            "groupes": 0, "sans_message_de_moi": 0, "illisibles": illisibles,
            "relances": 0, "reponses": 0, "simulation": simuler,
            "fiches_mises_a_jour": 0, "sans_fiche": 0}


def importer(conn, dossier_export, mon_nom=None, simuler=False):
    """Importe un export et analyse ses conversations.

    simuler=True : fait tous les calculs mais n'enregistre rien.
    Renvoie un rapport (des nombres et des codes P00X, jamais de noms).
    """
    dossiers, conversations, illisibles, nom, regles = _preparer(dossier_export, mon_nom)
    rapport = _rapport_vide(dossiers, illisibles, simuler)
    return _traiter(conn, conversations, nom, regles, rapport, creer=True)


def analyser_base(conn, dossier_export, mon_nom=None, simuler=False):
    """Relance l'analyse sur les fiches existantes, sans créer de prospect.

    Le texte des réponses n'étant jamais stocké, il est relu dans l'export.
    """
    dossiers, conversations, illisibles, nom, regles = _preparer(dossier_export, mon_nom)
    rapport = _rapport_vide(dossiers, illisibles, simuler)
    return _traiter(conn, conversations, nom, regles, rapport, creer=False)
