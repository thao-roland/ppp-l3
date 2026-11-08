"""Lecture de l'export officiel Facebook (« Télécharger vos informations », JSON).

On lit seulement les fichiers de l'export, sur mon ordinateur : pas de scraping,
aucune connexion à Facebook. Ce module ne touche pas à la base de données.
"""

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Fuseau utilisé pour transformer les horodatages Facebook en dates.
FUSEAU = ZoneInfo("Europe/Paris")

# Dossiers de conversations à parcourir (…/messages/<type>/<conversation>/).
# Une conversation où je n'ai écrit aucun message est de toute façon ignorée.
TYPES_DOSSIERS = ("inbox", "archived_threads", "message_requests", "filtered_threads")

# Un message à moi n'est une « relance » que s'il arrive au moins N heures après
# mon message précédent. 0 = tous mes messages sans réponse comptent comme relances.
# Mettre par ex. 12 pour ignorer les messages envoyés d'affilée le même jour.
DELAI_MIN_RELANCE_HEURES = 0


# --- Encodage cassé de Facebook ----------------------------------------------
def reparer_texte(texte):
    """Répare « Ã©» -> « é » : Facebook écrit de l'UTF-8 lu comme du latin-1."""
    try:
        return texte.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texte  # déjà correct (ou pas réparable) : on ne touche à rien


def reparer(valeur):
    """Répare tous les textes d'une structure JSON (listes et dictionnaires)."""
    if isinstance(valeur, str):
        return reparer_texte(valeur)
    if isinstance(valeur, list):
        return [reparer(v) for v in valeur]
    if isinstance(valeur, dict):
        return {cle: reparer(v) for cle, v in valeur.items()}
    return valeur


# --- Trouver et lire les conversations ---------------------------------------
def _dossiers_de_type(racine, type_dossier):
    """Dossiers « inbox » (ou autre type) d'un export.

    Trouve …/messages/inbox à n'importe quelle profondeur (ancienne ou nouvelle
    présentation), mais aussi inbox/ directement dans le dossier donné quand on
    a copié seulement le dossier « messages » de l'export.
    """
    racine = Path(racine)
    candidats = [racine / type_dossier] + sorted(racine.glob(f"**/messages/{type_dossier}"))
    return [c for c in candidats if c.is_dir() and not c.is_symlink()]


def trouver_conversations(racine):
    """Liste les dossiers de conversations d'un export."""
    trouves, deja_vus = [], set()
    for type_dossier in TYPES_DOSSIERS:
        for parent in _dossiers_de_type(racine, type_dossier):
            for d in sorted(parent.iterdir()):
                if d.is_dir() and not d.is_symlink() and d.resolve() not in deja_vus:
                    deja_vus.add(d.resolve())
                    trouves.append(d)
    return trouves


def _fichiers_messages(dossier):
    """message_1.json, message_2.json… dans l'ordre des numéros (pas du texte)."""
    fichiers = []
    for f in dossier.iterdir():
        correspond = re.fullmatch(r"message_(\d+)\.json", f.name)
        if correspond and f.is_file() and not f.is_symlink():
            fichiers.append((int(correspond.group(1)), f))
    return [f for _, f in sorted(fichiers)]


def _message(brut):
    """Message simplifié (horodatage ms, expéditeur, texte ou None), ou None si inutilisable."""
    try:
        contenu = brut.get("content")
        return (int(brut["timestamp_ms"]), str(brut["sender_name"]),
                contenu if isinstance(contenu, str) else None)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _noms(participants):
    return [p["name"] for p in participants if isinstance(p, dict) and "name" in p]


def cle_conversation(thread_path, dossier):
    """Identifiant stable d'une conversation : la partie numérique de son dossier."""
    base = Path(thread_path).name if thread_path else dossier.name
    return base.rsplit("_", 1)[-1]


def lire_conversation(dossier):
    """Lit tous les fichiers d'une conversation (même répartie sur plusieurs).

    Renvoie {"cle", "participants", "messages"} ou None si illisible.
    """
    dossier = Path(dossier)
    fichiers = _fichiers_messages(dossier)
    if not fichiers:
        return None
    participants, messages, thread_path = [], [], None
    for fichier in fichiers:
        try:
            donnees = reparer(json.loads(fichier.read_text(encoding="utf-8")))
            participants = participants or _noms(donnees["participants"])
            messages += [_message(m) for m in donnees["messages"]]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None  # fichier abîmé : on laisse cette conversation de côté
        thread_path = thread_path or donnees.get("thread_path")
    return {
        "cle": cle_conversation(thread_path, dossier),
        "participants": participants,
        "messages": sorted((m for m in messages if m is not None), key=lambda m: m[0]),
    }


# --- Savoir qui je suis ------------------------------------------------------
def detecter_mon_nom(conversations):
    """Mon nom = celui qui revient dans (presque) toutes les conversations."""
    compte = Counter(n for c in conversations for n in set(c["participants"]))
    plus_frequents = compte.most_common(2)
    if not plus_frequents or plus_frequents[0][1] < 2:
        return None
    if len(plus_frequents) == 2 and plus_frequents[0][1] == plus_frequents[1][1]:
        return None  # égalité : impossible de savoir qui je suis
    return plus_frequents[0][0]


# --- Transformer une conversation en prospect --------------------------------
def _date(ts_ms):
    """Horodatage Facebook (millisecondes) -> date AAAA-MM-JJ (heure de Paris)."""
    return datetime.fromtimestamp(ts_ms / 1000, FUSEAU).date().isoformat()


def _relances(messages_apres_le_premier, premier):
    """Mes messages suivants, en écartant ceux envoyés trop peu de temps après le précédent."""
    delai_ms = DELAI_MIN_RELANCE_HEURES * 3600 * 1000
    relances, precedent = [], premier[0]
    for ts, _, texte in messages_apres_le_premier:
        if ts - precedent >= delai_ms:
            relances.append({"date": _date(ts), "texte": texte})
        precedent = ts
    return relances


def analyser(conversation, mon_nom):
    """Renvoie (prospect, None) ou (None, raison) si la conversation est ignorée.

    Règles : une conversation entre deux personnes = un prospect.
    - date du 1er message = mon premier message ;
    - date de réponse = premier message de l'autre APRÈS le mien ;
    - relances = mes messages suivants restés sans réponse.
    """
    noms = conversation["participants"]
    autre = next((n for n in noms if n != mon_nom), None)
    if len(noms) != 2 or mon_nom not in noms or autre is None:
        return None, "groupes"
    miens = [m for m in conversation["messages"] if m[1] == mon_nom]
    if not miens:
        return None, "sans_message_de_moi"
    premier = miens[0]
    reponse = next((m for m in conversation["messages"]
                    if m[1] != mon_nom and m[0] > premier[0]), None)
    fin = reponse[0] if reponse else float("inf")
    relances = _relances([m for m in miens[1:] if m[0] < fin], premier)
    return {
        "cle": conversation["cle"],
        "nom_entreprise": autre,
        "date_premier_message": _date(premier[0]),
        "texte_envoye": premier[2],
        "date_reponse": _date(reponse[0]) if reponse else None,
        "relances": relances,
        "statut": "a répondu" if reponse else ("relancé" if relances else "contacté"),
    }, None
