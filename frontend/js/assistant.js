"use strict";

(function () {
  const TOKEN_STORAGE_KEY = "smartStock.accessToken";
  const apiBaseUrl = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");
  const MAX_HISTORY_TURNS = 10;

  const CHIPS = [
    "What should I restock?",
    "What sold best?",
    "How much did I make today?",
    "Am I low on anything?",
  ];

  let history = [];
  let sending = false;

  function token() {
    return sessionStorage.getItem(TOKEN_STORAGE_KEY);
  }

  function buildWidget() {
    const button = document.createElement("button");
    button.className = "assistant-fab";
    button.type = "button";
    button.setAttribute("data-assistant-fab", "");
    button.setAttribute("aria-label", "Open the Smart Stock assistant");
    button.title = "Ask the Smart Stock assistant";
    button.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5 13.9 9l5.6 1.9-5.6 1.9L12 18.4l-1.9-5.6L4.5 10.9 10.1 9 12 3.5Z"/><path d="M18.5 16.2l.8 2.3 2.3.8-2.3.8-.8 2.3-.8-2.3-2.3-.8 2.3-.8.8-2.3Z"/></svg>';

    const panel = document.createElement("section");
    panel.className = "assistant-panel";
    panel.hidden = true;
    panel.setAttribute("data-assistant-panel", "");
    panel.setAttribute("aria-label", "Smart Stock assistant");
    panel.innerHTML = `
      <header class="assistant-panel__head">
        <div>
          <p class="assistant-panel__title">Smart assistant</p>
          <p class="assistant-panel__sub">Answers from your live shop data</p>
        </div>
        <button class="icon-button" type="button" data-assistant-close aria-label="Close assistant">×</button>
      </header>
      <div class="assistant-messages" data-assistant-messages>
        <div class="assistant-bubble assistant-bubble--bot">Hi! Ask me what to restock, what sold best, or how today is going.</div>
      </div>
      <div class="assistant-chips" data-assistant-chips></div>
      <form class="assistant-form" data-assistant-form>
        <input class="assistant-input" data-assistant-input type="text" maxlength="1000"
          placeholder="Ask about your stock or sales…" autocomplete="off" required />
        <button class="button button--small" type="submit" data-assistant-send>Send</button>
      </form>
    `;

    document.body.appendChild(button);
    document.body.appendChild(panel);
    return { button, panel };
  }

  function addBubble(messages, role, text, source) {
    const bubble = document.createElement("div");
    bubble.className = `assistant-bubble assistant-bubble--${role === "user" ? "user" : "bot"}`;
    const body = document.createElement("span");
    body.className = "assistant-bubble__text";
    body.textContent = text;
    bubble.appendChild(body);
    if (role === "assistant" && source) {
      const tag = document.createElement("span");
      tag.className = "assistant-bubble__source";
      tag.textContent = source === "gemini" ? "Gemini" : "shop data";
      tag.title = source === "gemini"
        ? "Answered by the Gemini model using your computed figures"
        : "Answered locally from your computed shop snapshot";
      bubble.appendChild(tag);
    }
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
  }

  function initializeAssistant() {
    if (!token() || !apiBaseUrl) return;
    if (document.querySelector("[data-assistant-fab]")) return;

    const { button, panel } = buildWidget();
    const messages = panel.querySelector("[data-assistant-messages]");
    const chipsRow = panel.querySelector("[data-assistant-chips]");
    const form = panel.querySelector("[data-assistant-form]");
    const input = panel.querySelector("[data-assistant-input]");
    const sendButton = panel.querySelector("[data-assistant-send]");

    CHIPS.forEach((label) => {
      const chip = document.createElement("button");
      chip.className = "assistant-chip";
      chip.type = "button";
      chip.textContent = label;
      chip.addEventListener("click", () => {
        input.value = label;
        form.requestSubmit();
      });
      chipsRow.appendChild(chip);
    });

    function setOpen(open) {
      panel.hidden = !open;
      if (open) input.focus();
    }

    button.addEventListener("click", () => setOpen(panel.hidden));
    panel.querySelector("[data-assistant-close]").addEventListener("click", () => setOpen(false));

    async function send(message) {
      if (sending) return;
      sending = true;
      sendButton.disabled = true;
      input.disabled = true;
      addBubble(messages, "user", message);
      const typing = document.createElement("div");
      typing.className = "assistant-bubble assistant-bubble--bot assistant-bubble--typing";
      typing.innerHTML = "<span></span><span></span><span></span>";
      messages.appendChild(typing);
      messages.scrollTop = messages.scrollHeight;

      try {
        const response = await fetch(`${apiBaseUrl}/api/ai/assistant`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token()}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            message,
            history: history.slice(-MAX_HISTORY_TURNS),
          }),
        });
        typing.remove();
        if (response.status === 401) {
          sessionStorage.removeItem(TOKEN_STORAGE_KEY);
          window.location.replace("./login.html");
          return;
        }
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
          const detail = typeof payload?.detail === "string"
            ? payload.detail
            : "I could not reach the assistant. Please try again.";
          addBubble(messages, "assistant", detail, null);
          return;
        }
        history.push({ role: "user", text: message });
        history.push({ role: "assistant", text: payload.reply });
        history = history.slice(-MAX_HISTORY_TURNS * 2);
        addBubble(messages, "assistant", payload.reply, payload.source);
      } catch {
        typing.remove();
        addBubble(
          messages,
          "assistant",
          "I could not reach Smart Stock. Check your connection and try again.",
          null,
        );
      } finally {
        sending = false;
        sendButton.disabled = false;
        input.disabled = false;
        input.focus();
      }
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const message = input.value.trim();
      if (!message) return;
      input.value = "";
      send(message);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeAssistant);
  } else {
    initializeAssistant();
  }
})();
