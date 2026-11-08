"""Analyse statistique : intervalle de Wilson et test exact de Fisher.

Uniquement des totaux. Les formules sont écrites ici, avec la bibliothèque
standard, pour pouvoir être relues (voir le README).
"""

from math import comb, sqrt

import tableau

Z_95 = 1.959964             # valeur de z pour un intervalle de confiance à 95 %
SEUIL_P = 0.05              # en dessous, l'écart est dit « significatif »
MIN_CONTACTS_PAR_GROUPE = 30  # en dessous, on ne conclut pas
TROP_PEU = "Trop peu de données pour conclure"


# --- Les deux calculs --------------------------------------------------------
def wilson(succes, total, z=Z_95):
    """Intervalle de Wilson (bas, haut) entre 0 et 1, ou None si total = 0."""
    if not total:
        return None
    p = succes / total
    z2 = z * z
    denominateur = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denominateur
    marge = z * sqrt(p * (1 - p) / total + z2 / (4 * total * total)) / denominateur
    return max(0.0, centre - marge), min(1.0, centre + marge)


def fisher_bilateral(a, b, c, d):
    """Valeur p du test exact de Fisher sur le tableau [[a, b], [c, d]].

    a, b = réponses et non-réponses du groupe 1 ; c, d = celles du groupe 2.
    Calcul en nombres entiers : on additionne tous les tableaux possibles
    (mêmes totaux) qui ne sont pas plus probables que celui observé.
    Renvoie None si un des deux groupes est vide.
    """
    groupe1, groupe2 = a + b, c + d
    if not groupe1 or not groupe2:
        return None
    succes = a + c

    def poids(x):
        return comb(groupe1, x) * comb(groupe2, succes - x)

    observe = poids(a)
    extremes = sum(p for p in map(poids, range(max(0, succes - groupe2), min(groupe1, succes) + 1))
                   if p <= observe)
    return min(1.0, extremes / comb(groupe1 + groupe2, succes))


# --- Présentation des résultats ----------------------------------------------
def format_p(valeur):
    """0.0123 -> « 0,012 » ; très petit -> « moins de 0,001 »."""
    if valeur < 0.001:
        return "moins de 0,001"
    return f"{valeur:.3f}".replace(".", ",")


def avec_intervalle(ligne):
    """Ajoute à une ligne du bilan son intervalle (en %) et si elle est assez fournie."""
    intervalle = wilson(ligne["reponses"], ligne["contacts"])
    bas, haut = (round(v * 100, 1) for v in intervalle) if intervalle else (None, None)
    return {**ligne, "bas": bas, "haut": haut,
            "assez": ligne["contacts"] >= MIN_CONTACTS_PAR_GROUPE}


def conclure_ab(version_a, version_b):
    """Conclusion de la comparaison A/B : niveau, phrase et valeur p."""
    n_a, n_b = version_a["contacts"], version_b["contacts"]
    p = fisher_bilateral(version_a["reponses"], n_a - version_a["reponses"],
                         version_b["reponses"], n_b - version_b["reponses"])
    if n_a < MIN_CONTACTS_PAR_GROUPE or n_b < MIN_CONTACTS_PAR_GROUPE:
        return {"niveau": "trop_peu", "p": p,
                "texte": f"{TROP_PEU} : il faut au moins {MIN_CONTACTS_PAR_GROUPE} contacts "
                         f"par version (A : {n_a}, B : {n_b})."}
    if p < SEUIL_P:
        gagnante = "A" if version_a["taux_reponse"] > version_b["taux_reponse"] else "B"
        return {"niveau": "significatif", "p": p,
                "texte": f"La version {gagnante} obtient plus de réponses, et l'écart est "
                         f"statistiquement significatif (p = {format_p(p)})."}
    return {"niveau": "non_significatif", "p": p,
            "texte": f"Pas de différence démontrée entre A et B (p = {format_p(p)}). "
                     "Cela ne prouve pas qu'elles se valent."}


def construire(prospects):
    """Toutes les données de la page Analyse."""
    versions = [avec_intervalle(l) for l in tableau.comparer_versions(prospects)]
    return {
        "total": avec_intervalle(tableau.bilan(prospects)),
        "versions": versions,
        "canaux": [avec_intervalle(l) for l in tableau.comparer_canaux(prospects)],
        "conclusion_ab": conclure_ab(versions[0], versions[1]),
        "minimum": MIN_CONTACTS_PAR_GROUPE,
        "trop_peu": TROP_PEU,
    }
