"""Chiffres du tableau de bord : uniquement des totaux, jamais de nom ni de message.

Ce module ne lit pas la base : il reçoit la liste des prospects.
"""

from collections import Counter
from datetime import date, timedelta
from math import ceil

from modeles import A_VERIFIER, VERSIONS_DE_BASE

NON_RENSEIGNE = "Non renseigné"
LIMITE_VERSIONS = 10  # versions détaillées ; les suivantes sont regroupées
STATUTS_AVEC_REPONSE = ("a répondu", "intéressé", "signé")
STATUTS_INTERESSES = ("intéressé", "signé")
NIVEAUX_INTERESSES = ("curieux", "demande de prix")


# --- Définitions : une seule règle pour tout le tableau ----------------------
def est_interesse(prospect):
    """Intérêt curieux ou demande de prix, ou statut intéressé / signé."""
    return prospect["interet"] in NIVEAUX_INTERESSES or prospect["statut"] in STATUTS_INTERESSES


def categorie_reponse(prospect):
    """« vraie », « automatique », « a_verifier » ou « aucune ».

    Un prospect intéressé ou signé a forcément répondu pour de vrai, même si sa
    première réponse était automatique.
    """
    if est_interesse(prospect):
        return "vraie"
    if prospect["reponse_automatique"] == "oui":
        return "automatique"
    if prospect["reponse_automatique"] == "à vérifier":
        return "a_verifier"
    if prospect["date_reponse"] or prospect["statut"] in STATUTS_AVEC_REPONSE:
        return "vraie"
    return "aucune"


def a_repondu(prospect):
    """Vraie réponse : ni automatique, ni encore à vérifier."""
    return categorie_reponse(prospect) == "vraie"


def taux(nombre, total):
    """Pourcentage arrondi à 0,1 ; None s'il n'y a personne (pas « 0 % »)."""
    return round(100 * nombre / total, 1) if total else None


def format_pourcent(valeur):
    """46.9 -> « 46,9 % » ; None -> « — »."""
    return "—" if valeur is None else f"{valeur:.1f}".replace(".", ",") + " %"


def bilan(prospects):
    """Contacts, vraies réponses, automatiques, intéressés, signés et taux d'un groupe."""
    contacts = len(prospects)
    categories = Counter(categorie_reponse(p) for p in prospects)
    reponses = categories["vraie"]
    interesses = sum(est_interesse(p) for p in prospects)
    signes = sum(p["statut"] == "signé" for p in prospects)
    return {
        "contacts": contacts, "reponses": reponses, "interesses": interesses, "signes": signes,
        "automatiques": categories["automatique"], "a_verifier": categories["a_verifier"],
        "sans_reponse": categories["aucune"],
        "taux_reponse": taux(reponses, contacts), "taux_interet": taux(interesses, contacts),
        "taux_signature": taux(signes, contacts),
    }


def compter_categories(prospects):
    """Bilan de la base. Un prospect peut compter dans plusieurs catégories."""
    categories = [categorie_reponse(p) for p in prospects]
    return {
        "auto": categories.count("automatique"),
        "vraies": categories.count("vraie"),
        "interesses": sum(p["interet"] == "demande de prix" for p in prospects),
        "curieux": sum(p["interet"] == "curieux" for p in prospects),
        "pas_interesses": sum(c == "vraie" and p["interet"] == "aucun" for c, p in zip(categories, prospects)),
        "a_verifier": sum(A_VERIFIER in (p["reponse_automatique"], p["interet"]) for p in prospects),
        "sans_reponse": categories.count("aucune"),
    }


# --- Comparaisons ------------------------------------------------------------
def _grouper(prospects, champ):
    """{valeur du champ: prospects} ; une valeur vide va dans « Non renseigné »."""
    groupes = {}
    for prospect in prospects:
        groupes.setdefault(prospect[champ] or NON_RENSEIGNE, []).append(prospect)
    return groupes


def _ligne(libelle, prospects):
    return {"libelle": libelle, **bilan(prospects)}


def est_version(libelle):
    """Vrai pour une vraie version (A, B, AA…), pas pour un regroupement."""
    return libelle.isascii() and libelle.isupper() and libelle.isalpha() and len(libelle) <= 3


def comparer_versions(prospects, limite=LIMITE_VERSIONS):
    """Versions de la plus utilisée à la moins utilisée (A et B toujours présentes).

    Au-delà de `limite`, les autres sont regroupées ; les prospects sans version
    forment une dernière ligne.
    """
    groupes = _grouper(prospects, "version_message")
    sans_version = groupes.pop(NON_RENSEIGNE, None)
    lignes = sorted((_ligne(v, groupes.get(v, [])) for v in set(groupes) | set(VERSIONS_DE_BASE)),
                    key=lambda l: (-l["contacts"], len(l["libelle"]), l["libelle"]))
    gardees, reste = lignes[:limite], [l for l in lignes[limite:] if l["contacts"]]
    if reste:
        regroupes = [p for l in reste for p in groupes[l["libelle"]]]
        gardees.append(_ligne(f"Autres ({len(reste)} versions)", regroupes))
    if sans_version:
        gardees.append(_ligne(NON_RENSEIGNE, sans_version))
    return gardees


def comparer_canaux(prospects):
    """Canaux du plus utilisé au moins utilisé ; « Non renseigné » à la fin."""
    lignes = [_ligne(canal, groupe) for canal, groupe in _grouper(prospects, "canal").items()]
    return sorted(lignes, key=lambda l: (l["libelle"] == NON_RENSEIGNE, -l["contacts"], l["libelle"]))


# --- Évolution par semaine ---------------------------------------------------
def _lundi(jour_iso):
    jour = date.fromisoformat(jour_iso)
    return jour - timedelta(days=jour.weekday())


def par_semaine(prospects):
    """Une ligne par semaine (du lundi), semaines vides comprises.

    Les réponses sont rattachées à la semaine du PREMIER MESSAGE : on suit ainsi
    le taux de réponse des contacts de chaque semaine.
    """
    groupes = {}
    for prospect in prospects:
        if prospect["date_premier_message"]:
            groupes.setdefault(_lundi(prospect["date_premier_message"]), []).append(prospect)
    if not groupes:
        return []
    semaines, lundi = [], min(groupes)
    while lundi <= max(groupes):
        semaines.append({"lundi": lundi.isoformat(), "libelle": lundi.strftime("%d/%m/%Y"),
                         **bilan(groupes.get(lundi, []))})
        lundi += timedelta(days=7)
    return semaines


# --- Géométrie du graphique par semaine (dessiné en SVG, sans JavaScript) ----
LARGEUR, HAUTEUR = 900, 280
MARGE_GAUCHE, MARGE_DROITE, MARGE_HAUT, MARGE_BAS = 40, 10, 12, 28
EPAISSEUR_MAX = 24
ESPACE_SEGMENTS = 2
ARRONDI = 4
MAX_ETIQUETTES = 8


def _pas_graduation(maximum):
    """Pas « rond » (1, 2, 5, 10, 20…) donnant au plus 4 intervalles."""
    echelle = 1
    while True:
        for multiple in (1, 2, 5):
            if maximum / (multiple * echelle) <= 4:
                return multiple * echelle
        echelle *= 10


def _chemin(x, largeur, haut, bas, arrondi):
    """Barre arrondie en haut seulement ; arrondi=0 donne un rectangle."""
    r = min(arrondi, largeur / 2, bas - haut)
    return (f"M{x:.1f} {bas:.1f}V{haut + r:.1f}Q{x:.1f} {haut:.1f} {x + r:.1f} {haut:.1f}"
            f"H{x + largeur - r:.1f}Q{x + largeur:.1f} {haut:.1f} {x + largeur:.1f} {haut + r:.1f}"
            f"V{bas:.1f}Z")


def _segments(x, largeur, semaine, y_valeur):
    """Du bas vers le haut : vraies réponses, automatiques ou à vérifier, sans réponse."""
    couches = [c for c in ((semaine["reponses"], "serie-reponse"),
                           (semaine["automatiques"] + semaine["a_verifier"], "serie-auto"),
                           (semaine["sans_reponse"], "serie-sans")) if c[0]]
    segments, cumul = [], 0
    for numero, (valeur, classe) in enumerate(couches):
        bas = y_valeur(0) if numero == 0 else y_valeur(cumul) - ESPACE_SEGMENTS
        cumul += valeur
        arrondi = ARRONDI if numero == len(couches) - 1 else 0
        segments.append({"chemin": _chemin(x, largeur, min(y_valeur(cumul), bas - 1), bas, arrondi),
                         "classe": classe})
    return segments


def _compte(nombre, mot):
    """« 1 réponse », « 2 réponses » : le pluriel français commence à 2."""
    return f"{nombre} {mot}" + ("s" if nombre >= 2 else "")


def _barre(indice, semaine, creneau, largeur, y_valeur, frequence_etiquette):
    x_creneau = MARGE_GAUCHE + indice * creneau
    x = x_creneau + (creneau - largeur) / 2
    titre = (f"Semaine du {semaine['libelle']} : {_compte(semaine['contacts'], 'contact')}, "
             f"{_compte(semaine['reponses'], 'vraie réponse')} ({format_pourcent(semaine['taux_reponse'])})")
    douteuses = semaine["automatiques"] + semaine["a_verifier"]
    if douteuses:
        titre += f", automatiques ou à vérifier : {douteuses}"
    return {
        "x_creneau": round(x_creneau, 1), "creneau": round(creneau, 1), "titre": titre,
        "centre": round(x + largeur / 2, 1), "segments": _segments(x, largeur, semaine, y_valeur),
        "etiquette": semaine["libelle"][:5] if indice % frequence_etiquette == 0 else None,
    }


def graphique_semaines(semaines):
    """Tout ce qu'il faut pour dessiner le graphique, ou None sans données."""
    if not semaines:
        return None
    maximum = max(s["contacts"] for s in semaines)
    pas = _pas_graduation(maximum)
    plafond = ceil(maximum / pas) * pas
    base, trace = HAUTEUR - MARGE_BAS, HAUTEUR - MARGE_HAUT - MARGE_BAS

    def y_valeur(valeur):
        return base - valeur * trace / plafond

    creneau = (LARGEUR - MARGE_GAUCHE - MARGE_DROITE) / len(semaines)
    largeur = min(EPAISSEUR_MAX, creneau * 0.7)
    frequence = max(1, ceil(len(semaines) / MAX_ETIQUETTES))
    return {
        "largeur": LARGEUR, "hauteur": HAUTEUR, "gauche": MARGE_GAUCHE, "droite": LARGEUR - MARGE_DROITE,
        "haut": MARGE_HAUT, "base": base,
        "graduations": [{"valeur": v, "y": round(y_valeur(v), 1)} for v in range(0, plafond + 1, pas)],
        "barres": [_barre(i, s, creneau, largeur, y_valeur, frequence) for i, s in enumerate(semaines)],
    }


# --- Tout le tableau ---------------------------------------------------------
def construire(prospects):
    """Toutes les données de la page."""
    semaines = par_semaine(prospects)
    return {
        "total": bilan(prospects), "versions": comparer_versions(prospects),
        "canaux": comparer_canaux(prospects), "semaines": semaines,
        "graphique": graphique_semaines(semaines),
        "nb_version_renseignee": sum(bool(p["version_message"]) for p in prospects),
        "nb_sans_date": sum(not p["date_premier_message"] for p in prospects),
        "nb_dates_estimees": sum(bool(p["dates_estimees"]) for p in prospects),
    }
