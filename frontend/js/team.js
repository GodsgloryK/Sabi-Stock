"use strict";

const TOKEN_STORAGE_KEY = "smartStock.accessToken";
const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
const apiBaseUrl = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");
const teamMessage = document.querySelector("[data-team-message]");
const membersBody = document.querySelector("[data-members-body]");
const membersCount = document.querySelector("[data-members-count]");
const invitationsBody = document.querySelector("[data-invitations-body]");
const invitationsCount = document.querySelector("[data-invitations-count]");
const inviteCard = document.querySelector("[data-invite-card]");
const inviteCodeElement = document.querySelector("[data-invitation-code]");
const inviteExpiryElement = document.querySelector("[data-invitation-expiry]");
const inviteButton = document.querySelector("[data-invite-button]");
const copyCodeButton = document.querySelector("[data-copy-code]");

let currentUser = null;

function redirectToLogin() {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
}

function showMessage(message, type = "error") {
  teamMessage.textContent = message;
  teamMessage.className = `form-message form-message--${type} product-page-message`;
  teamMessage.hidden = false;
}

function clearMessage() {
  teamMessage.textContent = "";
  teamMessage.hidden = true;
}

async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(`${apiBaseUrl}/api${path}`, {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new Error("Unable to reach Smart-Stock. Check your connection and try again.");
  }

  if (response.status === 401) {
    redirectToLogin();
    throw new Error("Your session has expired. Please login again.");
  }
  if (response.status === 403) {
    throw new Error("Only business owners can manage the team.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : response.status >= 500
          ? "The service is temporarily unavailable. Please try again shortly."
          : "The request could not be completed. Check your details and try again.",
    );
  }

  if (response.status === 204) return null;
  return response.json();
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function roleBadge(role) {
  const label = role === "owner" ? "Owner" : "Stock manager";
  const modifier = role === "owner" ? "role-badge--owner" : "role-badge--manager";
  return `<span class="role-badge ${modifier}">${label}</span>`;
}

function renderMembers(members) {
  membersCount.textContent = `${members.length} ${members.length === 1 ? "member" : "members"}`;
  if (members.length === 0) {
    membersBody.innerHTML = '<tr><td class="products-table__status" colspan="5">No team members found.</td></tr>';
    return;
  }

  membersBody.innerHTML = members.map((member) => {
    const isSelf = currentUser && member.id === currentUser.id;
    const removeCell = member.role === "owner"
      ? ""
      : `<button class="table-action table-action--delete" type="button" data-remove-member="${escapeHtml(member.id)}"${isSelf ? " disabled title=\"You cannot remove your own owner account\"" : ""}>Remove</button>`;
    return `
      <tr>
        <td data-label="Name"><span class="product-name">${escapeHtml(member.full_name)}${isSelf ? " (you)" : ""}</span></td>
        <td data-label="Email">${escapeHtml(member.email)}</td>
        <td data-label="Role">${roleBadge(member.role)}</td>
        <td data-label="Joined">${escapeHtml(formatDateTime(member.joined_at))}</td>
        <td data-label="Actions" class="products-table__actions">${removeCell}</td>
      </tr>
    `;
  }).join("");
}

function invitationBadge(status) {
  const labels = { pending: "Pending", used: "Used", expired: "Expired" };
  const modifiers = {
    pending: "role-badge--manager",
    used: "role-badge--owner",
    expired: "role-badge--manager",
  };
  return `<span class="role-badge ${modifiers[status] ?? ""}">${labels[status] ?? escapeHtml(status)}</span>`;
}

function renderInvitations(invitations) {
  const pendingCount = invitations.filter((item) => item.status === "pending").length;
  invitationsCount.textContent = `${pendingCount} pending of ${invitations.length} total`;
  if (invitations.length === 0) {
    invitationsBody.innerHTML = '<tr><td class="products-table__status" colspan="4">No invitations yet. Create one with the button above.</td></tr>';
    return;
  }

  invitationsBody.innerHTML = invitations.map((invitation) => {
    const revokeCell = invitation.status === "pending"
      ? `<button class="table-action table-action--delete" type="button" data-revoke-invitation="${escapeHtml(invitation.id)}">Revoke</button>`
      : "";
    return `
      <tr>
        <td data-label="Status">${invitationBadge(invitation.status)}</td>
        <td data-label="Created">${escapeHtml(formatDateTime(invitation.created_at))}</td>
        <td data-label="Expires">${escapeHtml(formatDateTime(invitation.expires_at))}</td>
        <td data-label="Actions" class="products-table__actions">${revokeCell}</td>
      </tr>
    `;
  }).join("");
}

async function loadTeamData() {
  try {
    const [memberList, invitationList] = await Promise.all([
      apiRequest("/auth/members"),
      apiRequest("/auth/invitations/list"),
    ]);
    renderMembers(memberList);
    renderInvitations(invitationList);
  } catch (error) {
    showMessage(error.message);
    membersCount.textContent = "—";
    membersBody.innerHTML = '<tr><td class="products-table__status" colspan="5">Team members could not be loaded.</td></tr>';
    invitationsCount.textContent = "—";
    invitationsBody.innerHTML = '<tr><td class="products-table__status" colspan="4">Invitations could not be loaded.</td></tr>';
  }
}

function closeInviteCard() {
  inviteCard.hidden = true;
  inviteCodeElement.textContent = "—";
  inviteExpiryElement.textContent = "";
}

inviteButton.addEventListener("click", async () => {
  clearMessage();
  inviteButton.disabled = true;
  const originalLabel = inviteButton.innerHTML;
  inviteButton.textContent = "Creating…";
  try {
    const invitation = await apiRequest("/auth/invitations", { method: "POST" });
    inviteCodeElement.textContent = invitation.invitation_code;
    inviteExpiryElement.textContent = `Expires ${formatDateTime(invitation.expires_at)}`;
    inviteCard.hidden = false;
    inviteCard.scrollIntoView({ behavior: "smooth", block: "start" });
    await loadTeamData();
  } catch (error) {
    showMessage(error.message);
  } finally {
    inviteButton.disabled = false;
    inviteButton.innerHTML = originalLabel;
  }
});

copyCodeButton.addEventListener("click", async () => {
  const code = inviteCodeElement.textContent.trim();
  if (!code || code === "—") return;
  try {
    await navigator.clipboard.writeText(code);
    copyCodeButton.textContent = "Copied!";
    window.setTimeout(() => { copyCodeButton.textContent = "Copy code"; }, 2000);
  } catch {
    showMessage("Copy failed. Select the code and copy it manually.");
  }
});

document.querySelector("[data-close-invite]").addEventListener("click", closeInviteCard);

membersBody.addEventListener("click", async (event) => {
  const removeButton = event.target.closest("[data-remove-member]");
  if (!removeButton) return;

  const row = removeButton.closest("tr");
  const memberName = row?.querySelector(".product-name")?.textContent?.replace(" (you)", "") ?? "this member";
  if (!window.confirm(`Remove ${memberName} from this business? They will lose access immediately.`)) {
    return;
  }

  clearMessage();
  removeButton.disabled = true;
  try {
    await apiRequest(`/auth/members/${encodeURIComponent(removeButton.dataset.removeMember)}`, { method: "DELETE" });
    await loadTeamData();
    showMessage(`${memberName} was removed from the team.`, "success");
  } catch (error) {
    showMessage(error.message);
    removeButton.disabled = false;
  }
});

invitationsBody.addEventListener("click", async (event) => {
  const revokeButton = event.target.closest("[data-revoke-invitation]");
  if (!revokeButton) return;

  if (!window.confirm("Revoke this invitation? The code will no longer work.")) {
    return;
  }

  clearMessage();
  revokeButton.disabled = true;
  try {
    await apiRequest(`/auth/invitations/${encodeURIComponent(revokeButton.dataset.revokeInvitation)}`, { method: "DELETE" });
    await loadTeamData();
    showMessage("Invitation revoked.", "success");
  } catch (error) {
    showMessage(error.message);
    revokeButton.disabled = false;
  }
});

document.querySelector("[data-logout]").addEventListener("click", () => {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
});

async function initializeTeamPage() {
  if (!token || !apiBaseUrl) {
    redirectToLogin();
    return;
  }

  try {
    currentUser = await apiRequest("/auth/me");
    document.querySelector("[data-business-identity]").textContent = `${currentUser.full_name} · ${currentUser.business_name}`;
    if (currentUser.role !== "owner") {
      document.querySelectorAll("[data-owner-only]").forEach((element) => { element.hidden = true; });
      inviteButton.disabled = true;
      inviteButton.hidden = true;
      membersCount.textContent = "—";
      membersBody.innerHTML = '<tr><td class="products-table__status" colspan="5">Only the business owner can view the team.</td></tr>';
      invitationsCount.textContent = "—";
      invitationsBody.innerHTML = '<tr><td class="products-table__status" colspan="4">Only the business owner can view invitations.</td></tr>';
      showMessage("You do not have permission to manage the team. Contact the business owner.");
      return;
    }
    document.querySelectorAll("[data-owner-only]").forEach((element) => { element.hidden = false; });
    await loadTeamData();
  } catch (error) {
    showMessage(error.message);
  }
}

initializeTeamPage();
