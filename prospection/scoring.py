"""Score de priorité sur 100 et liste des relances à faire.

Les points et les délais sont dans scoring.toml. Ce module ne lit pas la base :
il reçoit les prospects et les dates de leurs relances.
"""

import tomllib
from datetime import date, datetime
from pathlib import Path

from facebook import FUSEAU
from modeles import INTERETS

FICHIER_REGLES = Path(__file__).resolve().parent / "scoring.toml"
SCORE_MAX = 100


class ErreurRegles(Exception):
    """Le fichier de règles est abîmé ou incomplet."""


# --- Lecture et contrôle des règles ------------------------------------------
def charger_regles(chemin=None):
    """Lit scoring.toml et vérifie qu'il est utilisable."""
    try:
        with open(chemin or FICHIER_REGLES, "rb") as fichier:
            regles = tomllib.load(fichier)
    except (OSError, tomllib.TOMLDecodeError) as erreur:
        raise ErreurRegles("Le fichier scoring.toml est illisible.") from erreur
    _verifier_regles(regles)
    return regles


def _verifier_regles(regles):
    """Refuse des règles incomplètes, ou dont le maximum n'est pas 100."""
    try:
        points = regles["points"]
        manquants = [i for i in INTERETS if i not in points["interet"]]
        site = [points["site"][c] for c in ("sans_site", "inconnu", "avec_site")]
        maximum = (points["a_repondu"] + max(points["interet"].values())
                   + max(site) + points["echange_recent"])
        _ = (points["par_relance_sans_reponse"], regles["recence"]["jours"],
             regles["relances"]["delai_jours"], regles["relances"]["max_sans_reponse"],
             regles["statuts_hors_score"])
    except (KeyError, TypeError) as erreur:
        raise ErreurRegles("Il manque un réglage dans scoring.toml.") from erreur
    if manquants:
        raise ErreurRegles("Il manque un niveau d'intérêt dans scoring.toml.")
    if maximum != SCORE_MAX:
        raise ErreurRegles(f"Le meilleur score possible vaut {maximum} au lieu de {SCORE_MAX} : "
                           "corrige les points dans scoring.toml.")


# --- Petites fonctions sur les dates -----------------------------------------
def aujourdhui():
    """La date du jour à l'heure de Paris (comme les dates importées)."""
    return datetime.now(FUSEAU).date()


def _jours_depuis(jour_iso, jour):
    """Nombre de jours entre une date AAAA-MM-JJ et `jour`."""
    return (jour - date.fromisoformat(jour_iso)).days


def relances_sans_reponse(prospect, dates_relances):
    """Relances non suivies d'une réponse : toutes, ou celles après la réponse."""
    reponse = prospect["date_reponse"]
    return [d for d in dates_relances if not reponse or d > reponse]


def _dernier_echange(prospect, dates_relances):
    """Date la plus récente connue, ou None si le prospect n'a aucune date."""
    dates = [prospect["date_premier_message"], prospect["date_reponse"], *dates_relances]
    return max((d for d in dates if d), default=None)


# --- Le score ----------------------------------------------------------------
def _points_site(a_deja_site, points_site):
    """1 = a déjà un site, 0 = pas de site, vide = inconnu."""
    if a_deja_site is None:
        return points_site["inconnu"]
    return points_site["avec_site"] if a_deja_site else points_site["sans_site"]


def _est_recent(prospect, dates_relances, regles, jour):
    dernier = _dernier_echange(prospect, dates_relances)
    return dernier is not None and 0 <= _jours_depuis(dernier, jour) < regles["recence"]["jours"]


def calculer_score(prospect, dates_relances, regles, jour):
    """Score de 0 à 100, ou None si le prospect est signé ou perdu."""
    if prospect["statut"] in regles["statuts_hors_score"]:
        return None
    points = regles["points"]
    total = points["interet"].get(prospect["interet"], 0)
    total += _points_site(prospect["a_deja_site"], points["site"])
    if prospect["date_reponse"]:
        total += points["a_repondu"]
    if _est_recent(prospect, dates_relances, regles, jour):
        total += points["echange_recent"]
    total += points["par_relance_sans_reponse"] * len(relances_sans_reponse(prospect, dates_relances))
    return max(0, min(SCORE_MAX, total))


def noter(prospects, relances, regles, jour=None):
    """Prospects avec leur score, du plus prioritaire au moins prioritaire.

    `relances` = {id du prospect: [dates]}. Les prospects sans score passent à la fin.
    """
    jour = jour or aujourdhui()
    notes = [dict(p, score=calculer_score(p, relances.get(p["id"], []), regles, jour))
             for p in prospects]
    return sorted(notes, key=lambda p: -1 if p["score"] is None else p["score"], reverse=True)


# --- Les relances à faire ----------------------------------------------------
def _jours_a_relancer(prospect, dates_relances, regles, jour):
    """Jours d'attente si le prospect est à relancer, sinon None."""
    if prospect["statut"] in regles["statuts_hors_score"] or not prospect["date_premier_message"]:
        return None
    sans_reponse = relances_sans_reponse(prospect, dates_relances)
    if prospect["date_reponse"] and not sans_reponse:
        return None  # il a répondu à mon dernier message
    if len(sans_reponse) >= regles["relances"]["max_sans_reponse"]:
        return None
    jours = _jours_depuis(max([prospect["date_premier_message"], *dates_relances]), jour)
    return jours if jours >= regles["relances"]["delai_jours"] else None


def a_relancer(prospects, relances, regles, jour=None):
    """Prospects à relancer : meilleur score d'abord, puis attente la plus longue."""
    jour = jour or aujourdhui()
    liste = []
    for prospect in noter(prospects, relances, regles, jour):
        dates = relances.get(prospect["id"], [])
        jours = _jours_a_relancer(prospect, dates, regles, jour)
        if jours is not None:
            liste.append(dict(prospect, jours_sans_reponse=jours,
                              nb_relances=len(relances_sans_reponse(prospect, dates))))
    return sorted(liste, key=lambda p: (-p["score"], -p["jours_sans_reponse"]))
