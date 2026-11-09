// Écran Qualifier : un clic enregistre un champ, sans recharger la page.
"use strict";

const ERREUR_RESEAU = "Enregistrement impossible : l'outil est-il lancé ?";

// Envoie un champ au serveur ; lève une erreur avec un message lisible.
async function envoyer(fiche, champ, valeur) {
  let reponse;
  try {
    reponse = await fetch(fiche.dataset.url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ champ, valeur }),
    });
  } catch {
    throw new Error(ERREUR_RESEAU);
  }
  const donnees = await reponse.json().catch(() => ({}));
  if (!reponse.ok) throw new Error(donnees.erreur || ERREUR_RESEAU);
  return donnees;
}

function afficherEtat(fiche, texte, echec = false) {
  const etat = fiche.querySelector(".qualif-etat");
  etat.textContent = texte;
  etat.classList.toggle("echec", echec);
}

function compterAVerifier() {
  const actifs = document.querySelectorAll(
    '[data-champ="reponse_automatique"][data-valeur="à vérifier"][aria-pressed="true"]');
  document.getElementById("nb-a-verifier").textContent = actifs.length;
}

// La valeur à envoyer : un second clic sur « Signé » ou sur une version annule.
function valeurDuClic(bouton) {
  const actif = bouton.getAttribute("aria-pressed") === "true";
  if (bouton.dataset.champ === "signe") return actif ? "non" : "oui";
  if (bouton.dataset.effacable && actif) return "";
  return bouton.dataset.valeur;
}

function marquerGroupe(groupe, champ, valeurEnvoyee) {
  groupe.querySelectorAll("button").forEach((b) => {
    const presse = champ === "signe" ? valeurEnvoyee === "oui" : b.dataset.valeur === valeurEnvoyee;
    b.setAttribute("aria-pressed", String(presse));
  });
}

async function surClic(evenement) {
  const bouton = evenement.target.closest("button[data-champ]");
  if (!bouton) return;
  const fiche = bouton.closest(".qualif");
  const groupe = bouton.closest(".choix");
  const { champ } = bouton.dataset;
  const valeur = valeurDuClic(bouton);
  const boutons = [...groupe.querySelectorAll("button")];
  boutons.forEach((b) => { b.disabled = true; });
  try {
    await envoyer(fiche, champ, valeur);
    marquerGroupe(groupe, champ, valeur);
    compterAVerifier();
    afficherEtat(fiche, "Enregistré");
  } catch (erreur) {
    afficherEtat(fiche, erreur.message, true);
  } finally {
    boutons.forEach((b) => { b.disabled = false; });
  }
}

async function surMontant(evenement) {
  const champ = evenement.target;
  if (!champ.matches("input[data-champ]")) return;
  const fiche = champ.closest(".qualif");
  try {
    await envoyer(fiche, champ.dataset.champ, champ.value);
    champ.dataset.initial = champ.value;
    afficherEtat(fiche, "Enregistré");
  } catch (erreur) {
    champ.value = champ.dataset.initial;
    afficherEtat(fiche, erreur.message, true);
  }
}

document.addEventListener("click", surClic);
document.addEventListener("change", surMontant);
