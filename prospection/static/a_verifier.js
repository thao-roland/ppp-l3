// Écran À vérifier : un clic corrige un champ, sans recharger la page.
"use strict";

const ERREUR_RESEAU = "Enregistrement impossible : l'outil est-il lancé ?";

// Envoie la correction ; lève une erreur avec un message lisible.
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

// Retire le champ corrigé ; une fiche sans champ douteux disparaît.
function retirerGroupe(fiche, groupe) {
  groupe.remove();
  if (!fiche.querySelector("[data-groupe]")) fiche.remove();
  const restants = document.querySelectorAll(".qualif").length;
  document.getElementById("nb-restants").textContent = restants;
  document.getElementById("rien-a-verifier").hidden = restants > 0;
}

async function surClic(evenement) {
  const bouton = evenement.target.closest("button[data-champ]");
  if (!bouton) return;
  const fiche = bouton.closest(".qualif");
  const groupe = bouton.closest("[data-groupe]");
  const boutons = [...groupe.querySelectorAll("button")];
  boutons.forEach((b) => { b.disabled = true; });
  try {
    const { corrections } = await envoyer(fiche, bouton.dataset.champ, bouton.dataset.valeur);
    document.getElementById("nb-corrections").textContent = corrections;
    afficherEtat(fiche, "Corrigé");
    retirerGroupe(fiche, groupe);
  } catch (erreur) {
    afficherEtat(fiche, erreur.message, true);
    boutons.forEach((b) => { b.disabled = false; });
  }
}

document.addEventListener("click", surClic);
