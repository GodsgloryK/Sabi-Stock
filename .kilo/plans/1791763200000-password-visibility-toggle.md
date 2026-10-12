# Password visibility toggle — implementation plan

## Goal
Let users reveal/hide their password while typing on the auth pages, instead of typing blind. Toggle applies to **every** password field: `login.html`, `register.html`, and `join.html`.

## Findings (cross-checked against code)
- Only 3 password inputs exist — all `<input type="password" name="password">` on the auth pages (verified via grep). No other pages collect passwords.
- All three auth pages load **the same** script: `<script src="./js/config.js">` + `<script src="./js/auth.js" defer>`. So one hook in `auth.js` covers all three pages.
- The auth forms are **already JS-dependent** for submission (`auth.js` → `submitAuthForm` calls `preventDefault` + `fetch`). A JS-injected toggle is therefore consistent with the existing baseline — if JS is off, nothing works anyway, and the default stays *hidden* (secure default).
- Icon convention: inline SVG with `fill="none"` + `stroke="currentColor"` (see `frontend/css/styles.css:205` `.button svg`).
- `.icon-button` class already exists (`styles.css:1480`) and is used in `team.html` / `products.html` for close `×` buttons. The eye button will reuse it for a consistent look.
- `.form-field` is `display:grid` with `gap`; inputs use `padding: 0.8rem 1rem; width:100%`.

## Design decisions
1. **JS-injected button** (not hand-coded in each HTML). Rationale: DRY across 3 pages, zero HTML edits, auto-covers future pages that load `auth.js`. Secure-by-default (hidden when JS unavailable).
2. **Reuse `.icon-button`** for the button shell; add a small `.password-toggle` class only for absolute positioning + icon sizing.
3. **Toggle via `input.type`** swap (`password` ↔ `text`). Prices/focus retained by the browser in modern browsers; no value reset.
4. **Accessibility**: `<button type="button">`, `aria-label="Show password"` / `"Hide password"`, `aria-pressed` tracking state, and a visible eye / eye-off SVG icon that swaps with the state. `<button type="button">` so it never submits the form.
5. **Scope**: no backend changes; no schema changes; no new dependencies. Pure frontend.

## Affected files
- `frontend/js/auth.js` — add init function (called at module load, like the rest of the file).
- `frontend/css/styles.css` — add `.password-field` wrapper + `.password-toggle` positioning rules.
- No HTML edits required (`frontend/login.html`, `register.html`, `join.html` unchanged).

## Implementation steps

### Step 1 — CSS (`frontend/css/styles.css`)
Add near the `.form-field` rules (after `styles.css:1258` / `.form-hint`):
```css
.password-field {
  position: relative;
  width: 100%;
}

.password-field input {
  padding-inline-end: 2.6rem;
}

.password-toggle {
  position: absolute;
  right: 0.5rem;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  border: 1px solid var(--color-border);
  border-radius: 0.7rem;
  background: var(--color-surface);
  color: var(--color-muted);
  cursor: pointer;
  padding: 0;
  font-size: 1rem;
  place-items: center;
}

.password-toggle svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}
```
(Reuses `.icon-button` hover aesthetic; add an explicit `:hover` mirroring `.icon-button:hover` colors if not inheriting.)

### Step 2 — JS (`frontend/js/auth.js`)
Add two SVG icon constants and an initializer; run once at the bottom (script is `defer`, DOM ready).
```js
const EYE_SVG = '<svg viewBox="0 0 24 24"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11z"/><circle cx="12" cy="12" r="3.2"/></svg>';
const EYE_OFF_SVG = '<svg viewBox="0 0 24 24"><path d="M1 1 23 23"/><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11z"/><circle cx="12" cy="12" r="3.2"/></svg>';

function createPasswordToggle(input) {
  const wrapper = document.createElement("span");
  wrapper.className = "password-field";
  input.parentNode.insertBefore(wrapper, input);
  wrapper.appendChild(input);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "icon-button password-toggle";
  button.setAttribute("aria-label", "Show password");
  button.setAttribute("aria-pressed", "false");
  button.innerHTML = EYE_OFF_SVG;

  let revealed = false;
  button.addEventListener("click", () => {
    revealed = !revealed;
    input.type = revealed ? "text" : "password";
    button.innerHTML = revealed ? EYE_SVG : EYE_OFF_SVG;
    button.setAttribute("aria-label", revealed ? "Hide password" : "Show password");
    button.setAttribute("aria-pressed", String(revealed));
    input.focus(); // keep keyboard user on the field
  });

  wrapper.appendChild(button);
}

document.querySelectorAll('input[type="password"]').forEach(createPasswordToggle);
```
- Matches the existing style of `auth.js` (top-level `document.querySelectorAll(...).forEach(...)` for wiring, e.g. lines 110-112).
- `input.focus()` preserves usability; safe because the click came from the button.

### Step 3 — Verify
- Open `login.html`, `register.html`, `join.html` locally (e.g. `npx serve frontend`); each password field shows an eye button at its right edge.
- Click toggles reveal; button label/icon flips between eye-off (hidden) and eye (visible).
- Submit still works: `submitAuthForm` reads the password value via `FormData` regardless of `type`, so no regression.
- Tab order is correct: eye button sits after the input inside the wrapper; it is `type="button"` so Enter/Space doesn't submit the form.
- Native browser password-reveal icons (if any) coexist harmlessly.

## Rollout / migration
None: purely additive frontend assets. No DB/data/user migration. Deploy by rebuilding/redeploying the static frontend (Vercel) — the `build_frontend_config.js` step doesn't touch these files.

## Risks & notes
- **Browser-native reveal overlap**: some browsers render their own eye icon. Both can coexist; no conflict.
- **Focus retention on older browsers**: toggling `type` may blur the input on very old browsers; `input.focus()` call mitigates.
- **Scope creep avoided**: deliberately *not* adding a global "remember my preference" (`localStorage`) — that is out of scope for this request. Could be a follow-up.
- If the team later prefers progressive enhancement with the button in static HTML, the alternative is: add the `<button>` markup inside each `.form-field` and skip JS wrapper injection — but that is more repetitive and inconsistent with the JS-driven auth flow.
