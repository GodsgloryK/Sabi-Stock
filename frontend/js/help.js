"use strict";

const GUIDE_SEEN_KEY = "smartStock.guideSeen";

const HELP_STEPS = [
  {
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M12 8.2v7.6M8.2 12h7.6"/></svg>',
    label: "Add products",
    hint: "Products page",
  },
  {
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 16.5 9 11l3.5 3.5L20 7"/><path d="M15 7h5v5"/></svg>',
    label: "Record sales",
    hint: "Sales page",
  },
  {
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 3 7.5l9 4.5 9-4.5L12 3Z"/><path d="m3 12 9 4.5 9-4.5M3 16.5 12 21l9-4.5"/></svg>',
    label: "Watch your stock",
    hint: "Dashboard & All stock",
  },
  {
    icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19.5c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/><path d="M16 6.2a3.2 3.2 0 0 1 0 6.2M17 14.7c2.3.4 3.5 2.2 3.5 4.8"/></svg>',
    label: "Invite your team",
    hint: "Team page",
    ownerOnly: true,
  },
];

function buildStepsMarkup() {
  return HELP_STEPS.map((step) => `
    <li class="help-step"${step.ownerOnly ? ' data-owner-only hidden data-team-step' : ""}>
      <span class="help-step__icon">${step.icon}</span>
      <span class="help-step__text">
        <span class="help-step__label">${step.label}</span>
        <span class="help-step__hint">${step.hint}</span>
      </span>
    </li>
  `).join("");
}

function injectHelpButton() {
  if (document.querySelector("[data-help-open]")) return;
  const logoutButton = document.querySelector("[data-logout]");
  if (!logoutButton || !logoutButton.parentElement) return;

  const button = document.createElement("button");
  button.className = "header-help-button";
  button.type = "button";
  button.setAttribute("data-help-open", "");
  button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-label", "How to use Smart Stock");
  button.title = "How to use Smart Stock";
  button.textContent = "?";
  logoutButton.parentElement.insertBefore(button, logoutButton);
}

function injectHelpDialog() {
  if (document.querySelector("[data-help-dialog]")) return null;

  const dialog = document.createElement("dialog");
  dialog.className = "help-dialog";
  dialog.setAttribute("data-help-dialog", "");
  dialog.setAttribute("aria-labelledby", "help-dialog-title");
  dialog.innerHTML = `
    <div class="help-dialog__head">
      <div>
        <p class="eyebrow"><span class="eyebrow__dot"></span> Quick guide</p>
        <h2 id="help-dialog-title">How to use Smart Stock</h2>
      </div>
      <button class="icon-button" type="button" data-help-close aria-label="Close guide">×</button>
    </div>
    <p class="help-dialog__intro">Four steps to run your store.</p>
    <ol class="help-steps">${buildStepsMarkup()}</ol>
  `;
  document.body.appendChild(dialog);
  return dialog;
}

function syncOwnerStep(dialog) {
  const teamStep = dialog.querySelector("[data-team-step]");
  if (!teamStep) return;
  const teamNavLink = document.querySelector(".dashboard-nav [data-owner-only]");
  if (teamNavLink && !teamNavLink.hidden) teamStep.hidden = false;
}

function openDialog(dialog) {
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}

function closeDialog(dialog) {
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

function initializeHelp() {
  injectHelpButton();
  const dialog = injectHelpDialog();
  if (!dialog) return;

  const complete = document.readyState === "complete";
  if (complete) syncOwnerStep(dialog);

  const teamNavLink = document.querySelector(".dashboard-nav [data-owner-only]");
  if (teamNavLink) {
    new MutationObserver(() => syncOwnerStep(dialog)).observe(teamNavLink, {
      attributes: true,
      attributeFilter: ["hidden"],
    });
  }
  window.setTimeout(() => syncOwnerStep(dialog), 1200);

  document.querySelector("[data-help-open]")?.addEventListener("click", () => openDialog(dialog));
  dialog.querySelector("[data-help-close]")?.addEventListener("click", () => closeDialog(dialog));
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closeDialog(dialog);
  });

  let seen = false;
  try {
    seen = localStorage.getItem(GUIDE_SEEN_KEY) === "1";
  } catch {
    seen = false;
  }
  if (!seen) {
    try {
      localStorage.setItem(GUIDE_SEEN_KEY, "1");
    } catch {
      /* storage unavailable — skip persistence */
    }
    const autoOpen = () => window.setTimeout(() => { if (!dialog.open) openDialog(dialog); }, 600);
    if (document.readyState === "complete") autoOpen();
    else window.addEventListener("load", autoOpen);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeHelp);
} else {
  initializeHelp();
}
