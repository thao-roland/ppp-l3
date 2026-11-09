"""Export CSV anonymisé et choix de la période.

Le CSV est construit colonne par colonne à partir d'une liste fermée : un champ
qui n'est pas dans COLONNES_CSV (nom, texte, conversation…) ne peut pas en sortir.
"""

import csv
import io
from datetime import date

import tableau

COLONNES_CSV = ("code", "date_premier_message", "date_reponse", "dates_estimees",
                "canal", "version_message", "type_reponse", "reponse_automatique",
                "nb_relances", "interet", "statut", "a_deja_site")
LIBELLES_TYPE = {"vraie": "réponse", "automatique": "automatique",
                 "a_verifier": "à vérifier", "aucune": "aucune"}
LIBELLES_SITE = {None: "inconnu", 0: "non", 1: "oui"}


# --- La période ---------------------------------------------------------------
def _date_normalisee(texte):
    """Date AAAA-MM-JJ normalisée, ou None si le champ est vide. ValueError si invalide."""
    texte = (texte or "").strip()
    return date.fromisoformat(texte).isoformat() if texte else None


def lire_periode(valeurs):
    """Renvoie (début, fin, erreur). Un champ vide = pas de limite de ce côté."""
    try:
        debut = _date_normalisee(valeurs.get("debut"))
        fin = _date_normalisee(valeurs.get("fin"))
    except ValueError:
        return None, None, "Date invalide (format AAAA-MM-JJ)."
    if debut and fin and debut > fin:
        return None, None, "La date de début est après la date de fin."
    return debut, fin, None


def filtrer(prospects, debut, fin):
    """Prospects dont le PREMIER MESSAGE est dans la période (bornes comprises).

    Avec une période, un prospect sans date est écarté : on ne sait pas s'il y est.
    """
    if not debut and not fin:
        return list(prospects)
    return [p for p in prospects if p["date_premier_message"]
            and (not debut or p["date_premier_message"] >= debut)
            and (not fin or p["date_premier_message"] <= fin)]


def nom_fichier(base, debut, fin, extension):
    """Exemple : prospection_anonymise_2026-05-01_2026-08-31.csv"""
    return f"{base}_{debut or 'debut'}_{fin or 'fin'}.{extension}"


# --- Le CSV -------------------------------------------------------------------
def type_reponse(prospect):
    """Nature de la réponse : aucune, automatique, à vérifier, réponse, intéressé ou signé."""
    if prospect["statut"] == "signé":
        return "signé"
    if tableau.est_interesse(prospect):
        return "intéressé"
    return LIBELLES_TYPE[tableau.categorie_reponse(prospect)]


def _ligne_csv(prospect, nb_relances):
    """Uniquement les colonnes autorisées."""
    calculees = {
        "type_reponse": type_reponse(prospect), "nb_relances": nb_relances,
        "dates_estimees": "oui" if prospect["dates_estimees"] else "non",
        "a_deja_site": LIBELLES_SITE[prospect["a_deja_site"]],
    }
    return {c: calculees[c] if c in calculees else prospect[c] for c in COLONNES_CSV}


def csv_anonymise(prospects, relances):
    """Texte du CSV, trié par date puis par code (UTF-8, séparateur virgule).

    `relances` = {id du prospect: [dates]} ; seul leur nombre sort du fichier.
    """
    ordre = sorted(prospects, key=lambda p: (p["date_premier_message"] or "", p["code"]))
    sortie = io.StringIO()
    ecrivain = csv.DictWriter(sortie, fieldnames=COLONNES_CSV, lineterminator="\n")
    ecrivain.writeheader()
    ecrivain.writerows(_ligne_csv(p, len(relances.get(p["id"], []))) for p in ordre)
    return sortie.getvalue()
