"use strict";

const TOKEN_STORAGE_KEY = "smartStock.accessToken";
const PAGE_SIZE = 100;
const MAX_BATCH_ITEMS = 50;
const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
const apiBaseUrl = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");
const saleForm = document.querySelector("[data-sale-form]");
const saleItems = document.querySelector("[data-sale-items]");
const addItemButton = document.querySelector("[data-add-item]");
const salesBody = document.querySelector("[data-sales-body]");
const salesCount = document.querySelector("[data-sales-count]");
const salesMessage = document.querySelector("[data-sales-message]");
const submitSaleButton = document.querySelector("[data-submit-sale]");
const filterFrom = document.querySelector("[data-filter-from]");
const filterTo = document.querySelector("[data-filter-to]");
const filterProduct = document.querySelector("[data-filter-product]");
const loadMoreWrap = document.querySelector("[data-load-more-wrap]");
const loadMoreButton = document.querySelector("[data-load-more]");
const exportButton = document.querySelector("[data-export-csv]");

let products = [];
let sales = [];
let totalSalesCount = 0;
let currentOffset = 0;

function redirectToLogin() {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
}

function showMessage(message, type = "error") {
  salesMessage.textContent = message;
  salesMessage.className = `form-message form-message--${type} product-page-message`;
  salesMessage.hidden = false;
}

function clearMessage() {
  salesMessage.textContent = "";
  salesMessage.hidden = true;
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
    throw new Error("Unable to reach Smart Stock. Check your connection and try again.");
  }

  if (response.status === 401) {
    redirectToLogin();
    throw new Error("Your session has expired. Please login again.");
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

  if (response.status === 204) return { data: null, response };
  const data = await response.json();
  return { data, response };
}

function formatMoney(value) {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? `₦${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : "—";
}

function formatDate(value) {
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

function activeFilterParams() {
  const params = new URLSearchParams();
  if (filterFrom.value) params.set("date_from", filterFrom.value);
  if (filterTo.value) params.set("date_to", filterTo.value);
  if (filterProduct.value) params.set("product_id", filterProduct.value);
  return params;
}

function productById(productId) {
  return products.find((product) => product.id === productId);
}

function fillProductSelect(select, preferredValue) {
  if (products.length === 0) {
    select.replaceChildren(new Option("No products found", ""));
    return;
  }
  select.replaceChildren(new Option("Select a product", ""));
  products.forEach((product) => {
    const option = new Option(
      `${product.name} (${product.sku}) · ${product.stock_quantity} available`,
      product.id,
    );
    option.disabled = product.stock_quantity < 1;
    select.add(option);
  });
  if (preferredValue && productById(preferredValue)) {
    select.value = preferredValue;
  }
}

function updateRowStock(row) {
  const select = row.querySelector("[data-item-product]");
  const quantityInput = row.querySelector("[data-item-quantity]");
  const stockElement = row.querySelector("[data-item-stock]");
  const product = select ? productById(select.value) : null;

  if (!product) {
    stockElement.textContent = "—";
    quantityInput.removeAttribute("max");
    return;
  }
  stockElement.textContent = String(product.stock_quantity);
  quantityInput.max = String(product.stock_quantity);
}

function createItemRow() {
  const row = document.createElement("div");
  row.className = "sale-item";
  row.innerHTML = `
    <label class="form-field">
      <span class="form-field__label">Product</span>
      <select data-item-product></select>
    </label>
    <label class="form-field">
      <span class="form-field__label">Quantity sold</span>
      <input type="number" min="1" step="1" inputmode="numeric" placeholder="Qty" data-item-quantity />
    </label>
    <div class="sale-stock-panel" aria-live="polite">
      <span class="sale-stock-panel__label">Available</span>
      <strong data-item-stock>—</strong>
    </div>
    <button class="table-action table-action--delete sale-item__remove" type="button" data-remove-item>Remove</button>
  `;
  return row;
}

function refreshRows() {
  saleItems.querySelectorAll(".sale-item").forEach((row) => {
    const select = row.querySelector("[data-item-product]");
    fillProductSelect(select, select.value);
    updateRowStock(row);
  });
  addItemButton.disabled = products.length === 0 || saleItems.children.length >= MAX_BATCH_ITEMS;
  submitSaleButton.disabled = products.length === 0;
}

function addItemRow() {
  if (saleItems.children.length >= MAX_BATCH_ITEMS) return;
  saleItems.appendChild(createItemRow());
  refreshRows();
}

function resetBatchForm() {
  saleItems.replaceChildren();
  addItemRow();
}

function renderProductOptions() {
  refreshRows();

  const filterSelection = filterProduct.value;
  filterProduct.replaceChildren(new Option("All products", ""));
  products.forEach((product) => {
    filterProduct.add(new Option(`${product.name} (${product.sku})`, product.id));
  });
  if (products.some((product) => product.id === filterSelection)) {
    filterProduct.value = filterSelection;
  }
}

function renderSales() {
  const shown = sales.length;
  salesCount.textContent = totalSalesCount > shown
    ? `Showing ${shown} of ${totalSalesCount} sales`
    : `${sales.length} ${sales.length === 1 ? "sale" : "sales"}`;
  loadMoreWrap.hidden = shown >= totalSalesCount;

  if (sales.length === 0) {
    salesBody.innerHTML = '<tr><td class="products-table__status" colspan="7">No sales recorded yet. Record your first sale above.</td></tr>';
    return;
  }

  salesBody.innerHTML = sales.map((sale) => `
    <tr>
      <td data-label="Product">
        <span class="product-name">${escapeHtml(sale.product_name)}</span>
        ${sale.product_sku ? `<span class="sku-code sku-code--sub">${escapeHtml(sale.product_sku)}</span>` : ""}
      </td>
      <td data-label="Quantity sold"><span class="stock-value">${sale.quantity}</span></td>
      <td data-label="Total amount">${formatMoney(sale.total_amount)}</td>
      <td data-label="Profit"><span class="${Number(sale.profit) < 0 ? "profit-value profit-value--negative" : "profit-value"}">${formatMoney(sale.profit)}</span></td>
      <td data-label="Recorded by">${escapeHtml(sale.recorded_by_name || "—")}</td>
      <td data-label="Date">${escapeHtml(formatDate(sale.created_at))}</td>
      <td data-label="Actions" class="products-table__actions">
        <button class="table-action table-action--delete" type="button" data-void-sale="${escapeHtml(sale.id)}">Void &amp; restock</button>
      </td>
    </tr>
  `).join("");
}

function renderSummary(summary) {
  document.querySelector("[data-summary-revenue]").textContent = formatMoney(summary.total_amount);
  document.querySelector("[data-summary-profit]").textContent = formatMoney(summary.total_profit);
  document.querySelector("[data-summary-units]").textContent = Number(summary.total_units).toLocaleString();
  document.querySelector("[data-summary-count]").textContent = Number(summary.sale_count).toLocaleString();
}

function collectBatchItems() {
  const items = [];
  let error = null;
  saleItems.querySelectorAll(".sale-item").forEach((row) => {
    const select = row.querySelector("[data-item-product]");
    const quantityInput = row.querySelector("[data-item-quantity]");
    const productId = select.value;
    const rawQuantity = quantityInput.value.trim();
    if (!productId && rawQuantity === "") return;

    if (!productId) {
      error ??= "Choose a product for every item you add.";
      return;
    }
    const quantity = Number(rawQuantity);
    if (!Number.isSafeInteger(quantity) || quantity < 1) {
      error ??= "Quantity sold must be a whole number greater than zero for every item.";
      return;
    }
    const product = productById(productId);
    if (product && quantity > product.stock_quantity) {
      error ??= `Only ${product.stock_quantity} units of ${product.name} are available.`;
      return;
    }
    items.push({ product_id: productId, quantity });
  });
  return { items, error };
}

async function loadSalesPage({ append = false } = {}) {
  const params = activeFilterParams();
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(append ? currentOffset : 0));

  const { data, response } = await apiRequest(`/sales?${params.toString()}`);
  const fetched = data;
  const headerTotal = Number(response.headers.get("X-Total-Count"));
  totalSalesCount = Number.isFinite(headerTotal) ? headerTotal : fetched.length;
  if (append) {
    sales = [...sales, ...fetched];
  } else {
    sales = fetched;
  }
  currentOffset = sales.length;
  renderSales();
}

async function loadSummary() {
  const params = activeFilterParams();
  const { data } = await apiRequest(`/sales/summary?${params.toString()}`);
  renderSummary(data);
}

async function reloadWithFilters() {
  clearMessage();
  try {
    await Promise.all([loadSalesPage(), loadSummary()]);
  } catch (error) {
    showMessage(error.message);
  }
}

async function loadPageData() {
  if (!token || !apiBaseUrl) {
    redirectToLogin();
    return;
  }

  try {
    const { data: user } = await apiRequest("/auth/me");
    document.querySelector("[data-business-identity]").textContent = `${user.full_name} · ${user.business_name}`;
    if (user.role === "owner") {
      document.querySelectorAll("[data-owner-only]").forEach((element) => { element.hidden = false; });
    }
    const { data: productList } = await apiRequest("/products");
    products = productList;
    resetBatchForm();
    renderProductOptions();
    await reloadWithFilters();
  } catch (error) {
    showMessage(error.message);
    submitSaleButton.disabled = true;
    salesCount.textContent = "—";
    salesBody.innerHTML = '<tr><td class="products-table__status" colspan="7">Sales history could not be loaded.</td></tr>';
  }
}

saleItems.addEventListener("change", (event) => {
  const row = event.target.closest(".sale-item");
  if (row && event.target.matches("[data-item-product]")) updateRowStock(row);
});

saleItems.addEventListener("click", (event) => {
  const removeButton = event.target.closest("[data-remove-item]");
  if (!removeButton) return;
  const row = removeButton.closest(".sale-item");
  if (!row) return;
  if (saleItems.children.length === 1) {
    row.querySelector("[data-item-product]").value = "";
    row.querySelector("[data-item-quantity]").value = "";
    updateRowStock(row);
    return;
  }
  row.remove();
  refreshRows();
});

addItemButton.addEventListener("click", addItemRow);

filterFrom.addEventListener("change", reloadWithFilters);
filterTo.addEventListener("change", reloadWithFilters);
filterProduct.addEventListener("change", reloadWithFilters);

document.querySelector("[data-clear-filters]").addEventListener("click", () => {
  clearMessage();
  filterFrom.value = "";
  filterTo.value = "";
  filterProduct.value = "";
  sales = [];
  totalSalesCount = 0;
  currentOffset = 0;
  salesCount.textContent = "Cleared";
  loadMoreWrap.hidden = true;
  salesBody.innerHTML = '<tr><td class="products-table__status" colspan="7">Sales history cleared from view. Refresh or change a filter to load sales again.</td></tr>';
});

loadMoreButton.addEventListener("click", async () => {
  loadMoreButton.disabled = true;
  loadMoreButton.textContent = "Loading…";
  try {
    await loadSalesPage({ append: true });
  } catch (error) {
    showMessage(error.message);
  } finally {
    loadMoreButton.disabled = false;
    loadMoreButton.textContent = "Load more sales";
  }
});

exportButton.addEventListener("click", async () => {
  clearMessage();
  exportButton.disabled = true;
  const originalLabel = exportButton.textContent;
  exportButton.textContent = "Preparing…";
  try {
    const params = activeFilterParams();
    const response = await fetch(`${apiBaseUrl}/api/reports/export/sales.csv?${params.toString()}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      throw new Error(
        typeof payload?.detail === "string"
          ? payload.detail
          : "The export could not be prepared. Please try again.",
      );
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "smart-stock-sales.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    showMessage(error.message);
  } finally {
    exportButton.disabled = false;
    exportButton.textContent = originalLabel;
  }
});

saleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  if (!saleForm.reportValidity()) return;

  const { items, error } = collectBatchItems();
  if (error) {
    showMessage(error);
    return;
  }
  if (items.length === 0) {
    showMessage("Add at least one product and quantity before recording sales.");
    return;
  }

  submitSaleButton.disabled = true;
  submitSaleButton.textContent = "Recording…";
  try {
    const { data: recorded } = await apiRequest("/sales/batch", {
      method: "POST",
      body: JSON.stringify({ items }),
    });
    const soldByProduct = new Map();
    recorded.forEach((sale) => {
      soldByProduct.set(sale.product_id, (soldByProduct.get(sale.product_id) || 0) + sale.quantity);
    });
    products = products.map((product) => (
      soldByProduct.has(product.id)
        ? { ...product, stock_quantity: product.stock_quantity - soldByProduct.get(product.id) }
        : product
    ));
    resetBatchForm();
    renderProductOptions();
    showMessage(
      `${recorded.length} ${recorded.length === 1 ? "sale" : "sales"} recorded and stock updated.`,
      "success",
    );
    await reloadWithFilters();
  } catch (error) {
    showMessage(error.message);
    await loadPageData();
  } finally {
    submitSaleButton.textContent = "Record sales";
    refreshRows();
  }
});

salesBody.addEventListener("click", async (event) => {
  const voidButton = event.target.closest("[data-void-sale]");
  if (!voidButton) return;

  const sale = sales.find((item) => item.id === voidButton.dataset.voidSale);
  if (!sale || !window.confirm(`Void this sale of ${sale.quantity} × ${sale.product_name} and return the units to stock?`)) {
    return;
  }

  clearMessage();
  voidButton.disabled = true;
  try {
    await apiRequest(`/sales/${encodeURIComponent(sale.id)}`, { method: "DELETE" });
    const product = products.find((item) => item.id === sale.product_id);
    if (product) product.stock_quantity += sale.quantity;
    renderProductOptions();
    showMessage("Sale voided and stock restored.", "success");
    await reloadWithFilters();
  } catch (error) {
    showMessage(error.message);
    voidButton.disabled = false;
  }
});

document.querySelector("[data-logout]").addEventListener("click", () => {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
});

loadPageData();
