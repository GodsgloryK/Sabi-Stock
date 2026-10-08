"use strict";

const TOKEN_STORAGE_KEY = "smartStock.accessToken";
const API_BASE_URL = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");

function setFormMessage(message, type = "error") {
  const messageElement = document.querySelector("[data-form-message]");
  if (!messageElement) return;

  messageElement.textContent = message;
  messageElement.className = `form-message form-message--${type}`;
  messageElement.hidden = false;
}

function clearFormMessage() {
  const messageElement = document.querySelector("[data-form-message]");
  if (!messageElement) return;

  messageElement.textContent = "";
  messageElement.hidden = true;
}

function formatApiError(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.at(-1) : "";
        const label = typeof field === "string" ? `${field}: ` : "";
        return typeof item.msg === "string" ? `${label}${item.msg}` : "";
      })
      .filter(Boolean);
    if (messages.length) return messages.join(" ");
  }

  if (status === 409) return "An account with this email address already exists.";
  if (status === 401) return "The email or password you entered is incorrect.";
  if (status >= 500) return "The service is temporarily unavailable. Please try again shortly.";
  return "We couldn't complete your request. Check your details and try again.";
}

async function submitAuthForm(event) {
  event.preventDefault();
  clearFormMessage();

  const form = event.currentTarget;
  form.querySelectorAll("[data-trim-required]").forEach((input) => {
    input.setCustomValidity(
      input.value.trim() ? "" : "Please enter a value without only spaces.",
    );
  });
  if (!form.reportValidity()) return;

  if (!API_BASE_URL) {
    setFormMessage("The API address is not configured. Please contact support.");
    return;
  }

  const submitButton = form.querySelector('[type="submit"]');
  const defaultLabel = submitButton.textContent;
  submitButton.disabled = true;
  submitButton.textContent = "Please wait…";

  const payload = Object.fromEntries(new FormData(form).entries());
  for (const field of ["full_name", "business_name", "email", "invitation_code"]) {
    if (typeof payload[field] === "string") payload[field] = payload[field].trim();
  }
  const endpointByForm = {
    register: "/api/auth/register/owner",
    join: "/api/auth/register/manager",
    login: "/api/auth/login",
  };
  const endpoint = endpointByForm[form.dataset.authForm] ?? "/api/auth/login";

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const result = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(formatApiError(result, response.status));
    }

    if (typeof result?.access_token !== "string" || !result.access_token) {
      throw new Error("The server response was incomplete. Please try again.");
    }

    try {
      sessionStorage.setItem(TOKEN_STORAGE_KEY, result.access_token);
    } catch {
      throw new Error("Your browser could not save this session. Enable site storage and try again.");
    }
    window.location.assign("./dashboard.html");
  } catch (error) {
    if (error instanceof TypeError) {
      setFormMessage("Unable to reach Smart-Stock. Check your connection and try again.");
    } else {
      setFormMessage(error instanceof Error ? error.message : "Something went wrong. Please try again.");
    }
    submitButton.disabled = false;
    submitButton.textContent = defaultLabel;
  }
}

document.querySelectorAll("[data-auth-form]").forEach((form) => {
  form.addEventListener("submit", submitAuthForm);
});

document.querySelectorAll("[data-clear-message]").forEach((input) => {
  input.addEventListener("input", clearFormMessage);
});
