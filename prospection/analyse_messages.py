"""Analyse automatique des messages d'une conversation, par des règles de mots.

100 % locale : aucun appel à une IA ni à Internet. Le texte des messages est lu
ici puis oublié : seuls les résultats (oui, curieux, 500…) sont renvoyés.
Les listes de mots sont dans regles_messages.toml.
"""

import re
import string
import tomllib
import unicodedata
from pathlib import Path

FICHIER_REGLES = Path(__file__).resolve().parent / "regles_messages.toml"

A_VERIFIER = "à vérifier"

# Un montant en euros : 500 €, 1 200€, 1.200 euros, 49,90 €.
MONTANT = re.compile(r"(?<![\d.,])(\d{1,3}(?:[ .]\d{3})+|\d+)(?:[.,]\d{1,2})?\s*(?:€|euros?\b|eur\b)")


class ErreurRegles(Exception):
    """Le fichier de règles est abîmé ou incomplet."""


# --- Lecture des règles --------------------------------------------------------
def normaliser(texte):
    """Sans majuscules, accents ni tirets ; apostrophes et espaces uniformisés."""
    decompose = unicodedata.normalize("NFD", texte.casefold().replace("’", "'").replace("-", " "))
    return " ".join("".join(c for c in decompose if not unicodedata.combining(c)).split())


def _motifs(expressions):
    """Motifs qui ne trouvent que des mots entiers."""
    return [re.compile(rf"(?<!\w){re.escape(normaliser(e))}(?!\w)") for e in expressions]


def charger_regles(chemin=None):
    """Lit regles_messages.toml et prépare les motifs de recherche."""
    try:
        with open(chemin or FICHIER_REGLES, "rb") as fichier:
            brut = tomllib.load(fichier)
    except (OSError, tomllib.TOMLDecodeError) as erreur:
        raise ErreurRegles("Le fichier regles_messages.toml est illisible.") from erreur
    try:
        actif = brut["reponses_automatiques"].get("actif", True)
        if not isinstance(actif, bool):
            raise TypeError("actif doit valoir true ou false")
        return {
            "auto_actif": actif,
            "delai_ms": int(brut["reponses_automatiques"]["delai_secondes"]) * 1000,
            "formules": _motifs(brut["reponses_automatiques"]["formules"]),
            "prix": _motifs(brut["interet"]["prix"]),
            "curieux": _motifs(brut["interet"]["curieux"]),
            "refus": _motifs(brut["interet"]["refus"]),
            "site": _motifs(brut["site"]["deja_un_site"]),
        }
    except (KeyError, TypeError, ValueError, AttributeError) as erreur:
        raise ErreurRegles("Il manque un réglage dans regles_messages.toml.") from erreur


def _trouve(motifs, texte):
    return any(m.search(texte) for m in motifs)


# --- Lecture des réponses de l'autre personne ----------------------------------
def _lire_reponse(message, messages, mon_nom, regles):
    """Ce qu'on retient d'une réponse : des indices, pas de texte à conserver."""
    horodatage, _, texte = message
    mon_precedent = max(m[0] for m in messages if m[1] == mon_nom and m[0] < horodatage)
    contenu = normaliser(texte or "")
    return {
        "horodatage": horodatage,
        "rapide": regles["auto_actif"] and horodatage - mon_precedent < regles["delai_ms"],
        "formule": regles["auto_actif"] and _trouve(regles["formules"], contenu),
        "question": "?" in contenu,
        "prix": _trouve(regles["prix"], contenu),
        "curieux": _trouve(regles["curieux"], contenu),
        "refus": _trouve(regles["refus"], contenu),
        "site": _trouve(regles["site"], contenu),
    }


def _suspecte(reponse):
    return reponse["rapide"] or reponse["formule"]


def _reponse_automatique(reponses):
    """« oui », « non » ou « à vérifier » quand les indices se contredisent."""
    premiere = reponses[0]
    if not _suspecte(premiere) or not all(_suspecte(r) for r in reponses[1:]):
        return "non"  # écrite sans signal, ou un message suivant écrit à la main
    mots_humains = premiere["prix"] or premiere["curieux"] or premiere["refus"]
    if mots_humains or (premiere["formule"] and not premiere["rapide"] and premiere["question"]):
        return A_VERIFIER
    return "oui"


def _interet(automatique, humaines):
    """Intérêt d'après les réponses sans formule automatique."""
    if automatique == "oui":
        return "aucun"
    prix = any(r["prix"] for r in humaines)
    curieux = any(r["curieux"] or r["question"] for r in humaines)
    refus = any(r["refus"] for r in humaines)
    if refus and (prix or curieux):
        return A_VERIFIER
    if prix:
        return "demande de prix"
    if curieux:
        return "curieux"
    return "aucun" if refus else A_VERIFIER


def _montant(texte):
    """Premier montant en euros d'un texte (entier), ou None."""
    for trouve in MONTANT.finditer(normaliser(texte)):
        montant = int(re.sub(r"[ .]", "", trouve.group(1)))
        if montant > 0:
            return montant
    return None


def _tarif(interet, humaines, messages, mon_nom):
    """Premier montant dans MES messages après sa demande de prix, sinon None."""
    if interet != "demande de prix":
        return None
    demande = next(r["horodatage"] for r in humaines if r["prix"])
    for horodatage, expediteur, texte in messages:
        if expediteur == mon_nom and horodatage > demande and texte and _montant(texte):
            return _montant(texte)
    return None


# --- Analyse d'une conversation ------------------------------------------------
def analyser(conversation, mon_nom, regles):
    """Résultats pour une conversation à deux. Ne renvoie jamais de texte."""
    messages = conversation["messages"]
    premier = next(m for m in messages if m[1] == mon_nom)
    brutes = [m for m in messages if m[1] != mon_nom and m[0] > premier[0]]
    if not brutes:
        return {"reponse_automatique": None, "interet": "aucun", "tarif_propose": None, "a_deja_site": None}
    reponses = [_lire_reponse(m, messages, mon_nom, regles) for m in brutes]
    automatique = _reponse_automatique(reponses)
    humaines = [r for r in reponses if not r["formule"]]
    interet = _interet(automatique, humaines)
    return {
        "reponse_automatique": automatique, "interet": interet,
        "tarif_propose": _tarif(interet, humaines, messages, mon_nom),
        "a_deja_site": 1 if any(r["site"] for r in humaines) else None,
    }


def code_version(rang):
    """0 -> A, 25 -> Z, 26 -> AA… (comme les colonnes d'Excel)."""
    lettres = ""
    rang += 1
    while rang:
        rang, reste = divmod(rang - 1, 26)
        lettres = string.ascii_uppercase[reste] + lettres
    return lettres
