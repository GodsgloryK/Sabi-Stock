"use strict";

const TOKEN_STORAGE_KEY = "smartStock.accessToken";
const LOW_STOCK_THRESHOLD = 5;
const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
const apiBaseUrl = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");
const groupsContainer = document.querySelector("[data-category-groups]");
const pageMessage = document.querySelector("[data-page-message]");
const searchInput = document.querySelector("[data-search]");
const stockCount = document.querySelector("[data-stock-count]");

let products = [];

function returnToLogin() {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
}

function showMessage(message, type = "error") {
  pageMessage.textContent = message;
  pageMessage.className = `form-message form-message--${type} product-page-message`;
  pageMessage.hidden = false;
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
    returnToLogin();
    throw new Error("Your session has expired. Please login again.");
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : "The request could not be completed. Please try again.",
    );
  }

  if (response.status === 204) return null;
  return response.json();
}

function formatPrice(value) {
  const price = Number(value);
  return Number.isFinite(price)
    ? `₦${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : "—";
}

function formatCount(value) {
  return Number(value).toLocaleString();
}

function stockBadge(quantity) {
  if (quantity === 0) {
    return `<span class="stock-value">${formatCount(quantity)}</span><span class="stock-badge stock-badge--out">Out</span>`;
  }
  if (quantity < LOW_STOCK_THRESHOLD) {
    return `<span class="stock-value">${formatCount(quantity)}</span><span class="stock-badge stock-badge--low">Low</span>`;
  }
  return `<span class="stock-value">${formatCount(quantity)}</span>`;
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

function buildGroups(list) {
  const map = new Map();
  list.forEach((product) => {
    const category = product.category || "Uncategorised";
    if (!map.has(category)) map.set(category, []);
    map.get(category).push(product);
  });
  return [...map.entries()].sort((first, second) => first[0].localeCompare(second[0]));
}

function renderSummary() {
  const categoryCount = new Set(products.map((product) => product.category || "Uncategorised")).size;
  const totalUnits = products.reduce((sum, product) => sum + Number(product.stock_quantity || 0), 0);
  document.querySelector("[data-total-categories]").textContent = formatCount(categoryCount);
  document.querySelector("[data-total-products]").textContent = formatCount(products.length);
  document.querySelector("[data-total-units]").textContent = formatCount(totalUnits);
}

function categoryChips(items) {
  const units = items.reduce((sum, product) => sum + Number(product.stock_quantity || 0), 0);
  const parsedOut = items.filter((product) => Number(product.stock_quantity) === 0).length;
  const parsedLow = items.filter((product) => {
    const quantity = Number(product.stock_quantity);
    return quantity > 0 && quantity < LOW_STOCK_THRESHOLD;
  }).length;
  const chips = [
    `<span class="category-chip">${items.length} ${items.length === 1 ? "product" : "products"}</span>`,
    `<span class="category-chip">${formatCount(units)} units</span>`,
  ];
  if (parsedOut > 0) chips.push(`<span class="category-chip category-chip--out">${parsedOut} out</span>`);
  if (parsedLow > 0) chips.push(`<span class="category-chip category-chip--low">${parsedLow} low</span>`);
  return chips.join("");
}

function renderGroup([category, items]) {
  const rows = items.map((product) => `
    <tr>
      <td data-label="Product ID"><span class="sku-code">${escapeHtml(product.sku)}</span></td>
      <td data-label="Product"><span class="product-name">${escapeHtml(product.name)}</span></td>
      <td data-label="Buying price">${formatPrice(product.buying_price)}</td>
      <td data-label="Selling price">${formatPrice(product.selling_price)}</td>
      <td data-label="Stock">${stockBadge(Number(product.stock_quantity))}</td>
      <td data-label="" class="products-table__actions">
        <a class="table-action" href="./products.html">Edit</a>
      </td>
    </tr>
  `).join("");

  return `
    <details class="category-group" open>
      <summary class="category-group__header">
        <span class="category-group__title">
          <span class="category-group__name">${escapeHtml(category)}</span>
          <span class="category-group__meta">${categoryChips(items)}</span>
        </span>
        <span class="category-group__chevron" aria-hidden="true"></span>
      </summary>
      <div class="products-table-wrap">
        <table class="products-table">
          <thead>
            <tr>
              <th scope="col">Product ID</th>
              <th scope="col">Product</th>
              <th scope="col">Buying price</th>
              <th scope="col">Selling price</th>
              <th scope="col">Stock</th>
              <th scope="col"><span class="visually-hidden">Edit</span></th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </details>
  `;
}

function render() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  const filtered = products.filter((product) => {
    if (!query) return true;
    return product.name.toLocaleLowerCase().includes(query)
      || (product.category || "").toLocaleLowerCase().includes(query)
      || String(product.sku || "").toLocaleLowerCase().includes(query);
  });
  const groups = buildGroups(filtered);

  if (products.length === 0) {
    stockCount.textContent = "No products";
    groupsContainer.innerHTML = '<p class="products-table__status">No products yet. Add products to see them grouped here.</p>';
    return;
  }

  stockCount.textContent = `${filtered.length} of ${products.length} ${products.length === 1 ? "product" : "products"} · ${groups.length} ${groups.length === 1 ? "category" : "categories"}`;

  if (filtered.length === 0) {
    groupsContainer.innerHTML = '<p class="products-table__status">No products match your search.</p>';
    return;
  }

  groupsContainer.innerHTML = groups.map(renderGroup).join("");
}

async function loadStock() {
  groupsContainer.innerHTML = '<p class="products-table__status">Loading your stock…</p>';
  products = await apiRequest("/products");
  renderSummary();
  render();
}

searchInput.addEventListener("input", render);
document.querySelector("[data-logout]").addEventListener("click", () => {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
});

async function initializeAllStockPage() {
  if (!token || !apiBaseUrl) {
    returnToLogin();
    return;
  }

  try {
    const user = await apiRequest("/auth/me");
    document.querySelector("[data-business-identity]").textContent = `${user.full_name} · ${user.business_name}`;
    if (user.role === "owner") {
      document.querySelectorAll("[data-owner-only]").forEach((element) => { element.hidden = false; });
    }
    await loadStock();
  } catch (error) {
    showMessage(error.message);
    groupsContainer.innerHTML = '<p class="products-table__status">Stock could not be loaded.</p>';
    stockCount.textContent = "—";
  }
}

initializeAllStockPage();
