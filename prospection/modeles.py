"""Règles sur les prospects : valeurs autorisées, validation, lecture/écriture."""

from datetime import date

# --- Valeurs autorisées (à modifier ici si besoin) ---------------------------
STATUTS = ["contacté", "relancé", "a répondu", "intéressé", "signé", "perdu"]
INTERETS = ["aucun", "curieux", "demande de prix"]
VERSIONS = ["A", "B"]
CANAUX = ["Messenger", "Facebook (commentaire)", "Instagram", "E-mail",
          "Téléphone", "Sur place", "Autre"]
REPONSES_AUTOMATIQUES = ["non", "oui", "à vérifier"]

# Champs enregistrés tels quels dans la table prospects (hors code et id).
COLONNES = [
    "nom_entreprise", "metier", "ville", "canal", "date_premier_message",
    "version_message", "texte_envoye", "date_reponse", "interet",
    "tarif_propose", "acompte", "statut", "a_deja_site", "dates_estimees",
    "reponse_automatique",
]


# --- Petites fonctions de nettoyage ------------------------------------------
def _texte(formulaire, champ):
    """Texte sans espaces autour ; chaîne vide -> None."""
    valeur = (formulaire.get(champ) or "").strip()
    return valeur or None


def _choix(formulaire, champ, autorises, erreurs):
    """Valeur qui doit être dans la liste (ou vide)."""
    valeur = _texte(formulaire, champ)
    if valeur is not None and valeur not in autorises:
        erreurs[champ] = "Valeur non reconnue."
        return None
    return valeur


def _date(formulaire, champ, erreurs):
    """Date au format AAAA-MM-JJ (ou vide)."""
    valeur = _texte(formulaire, champ)
    if valeur is None:
        return None
    try:
        return date.fromisoformat(valeur).isoformat()
    except ValueError:
        erreurs[champ] = "Date invalide (format AAAA-MM-JJ)."
        return None


def _euros(formulaire, champ, erreurs):
    """Montant entier en euros, positif ou nul (ou vide)."""
    valeur = _texte(formulaire, champ)
    if valeur is None:
        return None
    if not (valeur.isascii() and valeur.isdigit()):
        erreurs[champ] = "Entre un nombre entier d'euros (0 ou plus)."
        return None
    return int(valeur)


def _oui_non(formulaire, champ, erreurs):
    """'oui' -> 1, 'non' -> 0, vide -> None (inconnu)."""
    valeur = _texte(formulaire, champ)
    if valeur is None:
        return None
    if valeur not in ("oui", "non"):
        erreurs[champ] = "Valeur non reconnue."
        return None
    return 1 if valeur == "oui" else 0


# --- Validation d'un formulaire de prospect ----------------------------------
def valider(formulaire):
    """Vérifie un formulaire. Renvoie (valeurs, erreurs)."""
    erreurs = {}
    v = {
        "nom_entreprise": _texte(formulaire, "nom_entreprise"),
        "metier": _texte(formulaire, "metier"),
        "ville": _texte(formulaire, "ville"),
        "canal": _choix(formulaire, "canal", CANAUX, erreurs),
        "date_premier_message": _date(formulaire, "date_premier_message", erreurs),
        "version_message": _choix(formulaire, "version_message", VERSIONS, erreurs),
        "texte_envoye": _texte(formulaire, "texte_envoye"),
        "date_reponse": _date(formulaire, "date_reponse", erreurs),
        "interet": _choix(formulaire, "interet", INTERETS, erreurs) or "aucun",
        "tarif_propose": _euros(formulaire, "tarif_propose", erreurs),
        "acompte": _euros(formulaire, "acompte", erreurs),
        "statut": _choix(formulaire, "statut", STATUTS, erreurs) or "contacté",
        "a_deja_site": _oui_non(formulaire, "a_deja_site", erreurs),
        "dates_estimees": 1 if formulaire.get("dates_estimees") else 0,
        "reponse_automatique": _choix(formulaire, "reponse_automatique", REPONSES_AUTOMATIQUES, erreurs),
    }
    if not v["nom_entreprise"]:
        erreurs["nom_entreprise"] = "Le nom de l'entreprise est obligatoire."
    _verifier_coherence_dates(v, erreurs)
    return v, erreurs


def _verifier_coherence_dates(v, erreurs):
    """La réponse ne peut pas arriver avant le premier message."""
    debut, reponse = v["date_premier_message"], v["date_reponse"]
    if debut and reponse and reponse < debut:
        erreurs["date_reponse"] = "La réponse est avant le premier message."


# --- Lecture / écriture en base ----------------------------------------------
def prochain_code(conn):
    """Prochain code libre : P001, P002, P003..."""
    ligne = conn.execute(
        "SELECT MAX(CAST(SUBSTR(code, 2) AS INTEGER)) AS dernier FROM prospects"
    ).fetchone()
    return f"P{(ligne['dernier'] or 0) + 1:03d}"


def creer(conn, valeurs, conversation_fb=None, commit=True):
    """Ajoute un prospect et renvoie son code.

    commit=False sert à l'import : tout est validé (ou annulé) d'un seul coup.
    """
    code = prochain_code(conn)
    colonnes = ["code", "conversation_fb"] + COLONNES
    marques = ", ".join("?" for _ in colonnes)
    conn.execute(
        f"INSERT INTO prospects ({', '.join(colonnes)}) VALUES ({marques})",
        [code, conversation_fb] + [valeurs[c] for c in COLONNES],
    )
    if commit:
        conn.commit()
    return code


def modifier(conn, code, valeurs):
    """Met à jour un prospect existant."""
    affectations = ", ".join(f"{c} = ?" for c in COLONNES)
    conn.execute(
        f"UPDATE prospects SET {affectations} WHERE code = ?",
        [valeurs[c] for c in COLONNES] + [code],
    )
    conn.commit()


# --- Qualification rapide : un seul champ à la fois ---------------------------
# Liste fermée : le nom de colonne envoyé en SQL ne vient jamais du navigateur.
CHAMPS_RAPIDES = {
    "interet": lambda f, e: _choix(f, "interet", INTERETS, e),
    "version_message": lambda f, e: _choix(f, "version_message", VERSIONS, e),
    "reponse_automatique": lambda f, e: _choix(f, "reponse_automatique", REPONSES_AUTOMATIQUES, e),
    "tarif_propose": lambda f, e: _euros(f, "tarif_propose", e),
    "acompte": lambda f, e: _euros(f, "acompte", e),
}
CHAMPS_OBLIGATOIRES = ("interet", "reponse_automatique")
STATUT_SI_NON_SIGNE = "a répondu"
ERREUR_CHAMP = "Champ ou valeur non reconnu."


def _champ_signe(valeur):
    """Le bouton « Signé » écrit dans le statut."""
    if valeur not in ("oui", "non"):
        return None, ERREUR_CHAMP
    return ("statut", "signé" if valeur == "oui" else STATUT_SI_NON_SIGNE), None


def valider_champ(champ, valeur):
    """Renvoie ((colonne, valeur propre), None) ou (None, erreur)."""
    if not isinstance(champ, str) or isinstance(valeur, bool) or not isinstance(valeur, (str, int)):
        return None, ERREUR_CHAMP
    if champ == "signe":
        return _champ_signe(valeur)
    if champ not in CHAMPS_RAPIDES:
        return None, ERREUR_CHAMP
    erreurs = {}
    propre = CHAMPS_RAPIDES[champ]({champ: str(valeur)}, erreurs)
    if erreurs or (propre is None and champ in CHAMPS_OBLIGATOIRES):
        return None, erreurs.get(champ, ERREUR_CHAMP)
    return (champ, propre), None


def mettre_a_jour_champ(conn, code, colonne, valeur):
    """Enregistre un seul champ déjà validé par valider_champ."""
    if colonne != "statut" and colonne not in CHAMPS_RAPIDES:
        raise ValueError("Colonne non autorisée.")
    conn.execute(f"UPDATE prospects SET {colonne} = ? WHERE code = ?", (valeur, code))
    conn.commit()


def obtenir(conn, code):
    """Un prospect par son code (ou None)."""
    return conn.execute("SELECT * FROM prospects WHERE code = ?", (code,)).fetchone()


def lister(conn):
    """Tous les prospects, du plus récent au plus ancien."""
    return conn.execute("SELECT * FROM prospects ORDER BY id DESC").fetchall()


# --- Relances ----------------------------------------------------------------
def valider_relance(formulaire):
    """Vérifie une relance. Renvoie (valeurs, erreurs)."""
    erreurs = {}
    jour = _date(formulaire, "date", erreurs)
    if jour is None and "date" not in erreurs:
        erreurs["date"] = "La date de la relance est obligatoire."
    return {"date": jour, "texte": _texte(formulaire, "texte")}, erreurs


def ajouter_relance(conn, prospect_id, valeurs, commit=True):
    """Ajoute une relance à un prospect."""
    conn.execute(
        "INSERT INTO relances (prospect_id, date, texte) VALUES (?, ?, ?)",
        (prospect_id, valeurs["date"], valeurs["texte"]),
    )
    if commit:
        conn.commit()


def lister_relances(conn, prospect_id):
    """Relances d'un prospect, de la plus ancienne à la plus récente."""
    return conn.execute(
        "SELECT * FROM relances WHERE prospect_id = ? ORDER BY date, id",
        (prospect_id,),
    ).fetchall()


def dates_relances(conn):
    """Dates des relances de tous les prospects : {id du prospect: [dates]}."""
    par_prospect = {}
    for ligne in conn.execute("SELECT prospect_id, date FROM relances ORDER BY date, id"):
        par_prospect.setdefault(ligne["prospect_id"], []).append(ligne["date"])
    return par_prospect
