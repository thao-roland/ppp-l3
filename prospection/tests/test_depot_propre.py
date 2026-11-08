"""Garde-fou : rien de personnel ni de secret ne doit pouvoir partir sur GitHub.

Ce test examine tous les fichiers qui seraient commités (déjà suivis par git ou
nouveaux et non ignorés) et échoue si l'un d'eux ressemble à une donnée réelle.
"""

import re
import subprocess
from pathlib import Path

import pytest

from exports import COLONNES_CSV

RACINE = Path(__file__).resolve().parents[2]
FAUX_EXPORT = "prospection/tests/faux_export_facebook/"
DOSSIER_CSV = "prospection/donnees/"

# Noms de fichiers ou de dossiers qui n'ont rien à faire dans le dépôt.
NOMS_INTERDITS = re.compile(
    r"(\.(db|sqlite3?|pem|key|p12|pfx|zip)$)"
    r"|((^|/)\.env($|\.))"
    r"|((^|/)(exports_facebook|exports_prives|crm-donnees)/)",
    re.IGNORECASE,
)
# Un fichier de messages Facebook n'est permis que dans le FAUX export.
MESSAGE_FACEBOOK = re.compile(r"(^|/)message_\d+\.json$")

# Formes courantes de secrets (clés privées, clés d'API, mots de passe en clair).
SECRETS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b"),
    re.compile(r"(?i)\b(api[_-]?key|secret|passw(or)?d|token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
]


def fichiers_du_depot():
    """Fichiers suivis par git + nouveaux fichiers non ignorés."""
    try:
        sortie = subprocess.run(
            ["git", "-C", str(RACINE), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git n'est pas disponible")
    return [f for f in sortie.splitlines() if f and (RACINE / f).is_file()]


def test_aucun_fichier_de_donnees_dans_le_depot():
    suspects = [f for f in fichiers_du_depot()
                if NOMS_INTERDITS.search(f)
                or (MESSAGE_FACEBOOK.search(f) and not f.startswith(FAUX_EXPORT))]
    assert suspects == [], f"fichiers qui ne doivent pas être commités : {suspects}"


def test_exports_seulement_des_csv_anonymises():
    """Sous prospection/ : pas d'Excel, et un CSV seulement dans donnees/ aux bonnes colonnes."""
    suspects = []
    for nom in fichiers_du_depot():
        if not nom.startswith("prospection/"):
            continue
        if nom.endswith(".xlsx"):
            suspects.append(nom)
        elif nom.endswith(".csv"):
            entete = (RACINE / nom).read_text(encoding="utf-8").partition("\n")[0]
            if not nom.startswith(DOSSIER_CSV) or entete != ",".join(COLONNES_CSV):
                suspects.append(nom)
    assert suspects == [], f"exports qui ne doivent pas être commités : {suspects}"


def test_aucun_secret_dans_le_depot():
    trouves = []
    for nom in fichiers_du_depot():
        try:
            texte = (RACINE / nom).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # fichier binaire : ignoré
        if any(motif.search(texte) for motif in SECRETS):
            trouves.append(nom)
    assert trouves == [], f"secrets possibles dans : {trouves}"
