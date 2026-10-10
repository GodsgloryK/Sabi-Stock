"use strict";

const TOKEN_STORAGE_KEY = "smartStock.accessToken";
const PAGE_SIZE = 100;
const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
const apiBaseUrl = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");
const productSelect = document.querySelector("[data-sale-product]");
const quantityInput = document.querySelector("[data-sale-quantity]");
const availableStock = document.querySelector("[data-available-stock]");
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
    throw new Error("Unable to reach Smart-Stock. Check your connection and try again.");
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

function selectedProduct() {
  return products.find((product) => product.id === productSelect.value);
}

function activeFilterParams() {
  const params = new URLSearchParams();
  if (filterFrom.value) params.set("date_from", filterFrom.value);
  if (filterTo.value) params.set("date_to", filterTo.value);
  if (filterProduct.value) params.set("product_id", filterProduct.value);
  return params;
}

function updateSelectedStock() {
  const product = selectedProduct();
  availableStock.textContent = product ? String(product.stock_quantity) : "—";
  quantityInput.max = product ? String(product.stock_quantity) : "2147483647";
  if (!product || product.stock_quantity < 1) {
    quantityInput.value = "";
    quantityInput.disabled = true;
    submitSaleButton.disabled = true;
    return;
  }
  quantityInput.disabled = false;
  submitSaleButton.disabled = false;
}

function renderProductOptions() {
  const availableProductId = productSelect.value;
  productSelect.replaceChildren(new Option("Select a product", ""));
  products.forEach((product) => {
    const option = new Option(
      `${product.name} · ${product.stock_quantity} available`,
      product.id,
    );
    option.disabled = product.stock_quantity < 1;
    productSelect.add(option);
  });
  if (products.some((product) => product.id === availableProductId)) {
    productSelect.value = availableProductId;
  }
  if (products.length === 0) {
    productSelect.replaceChildren(new Option("No products found", ""));
    submitSaleButton.disabled = true;
  }

  const filterSelection = filterProduct.value;
  filterProduct.replaceChildren(new Option("All products", ""));
  products.forEach((product) => {
    filterProduct.add(new Option(product.name, product.id));
  });
  if (products.some((product) => product.id === filterSelection)) {
    filterProduct.value = filterSelection;
  }

  updateSelectedStock();
}

function renderSales() {
  const shown = sales.length;
  salesCount.textContent = totalSalesCount > shown
    ? `Showing ${shown} of ${totalSalesCount} sales`
    : `${sales.length} ${sales.length === 1 ? "sale" : "sales"}`;
  loadMoreWrap.hidden = shown >= totalSalesCount;

  if (sales.length === 0) {
    salesBody.innerHTML = '<tr><td class="products-table__status" colspan="6">No sales recorded yet. Record your first sale above.</td></tr>';
    return;
  }

  salesBody.innerHTML = sales.map((sale) => `
    <tr>
      <td data-label="Product"><span class="product-name">${escapeHtml(sale.product_name)}</span></td>
      <td data-label="Quantity sold"><span class="stock-value">${sale.quantity}</span></td>
      <td data-label="Total amount">${formatMoney(sale.total_amount)}</td>
      <td data-label="Profit"><span class="${Number(sale.profit) < 0 ? "profit-value profit-value--negative" : "profit-value"}">${formatMoney(sale.profit)}</span></td>
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
    renderProductOptions();
    await reloadWithFilters();
  } catch (error) {
    showMessage(error.message);
    productSelect.replaceChildren(new Option("Products could not be loaded", ""));
    submitSaleButton.disabled = true;
    salesCount.textContent = "—";
    salesBody.innerHTML = '<tr><td class="products-table__status" colspan="6">Sales history could not be loaded.</td></tr>';
  }
}

productSelect.addEventListener("change", updateSelectedStock);
filterFrom.addEventListener("change", reloadWithFilters);
filterTo.addEventListener("change", reloadWithFilters);
filterProduct.addEventListener("change", reloadWithFilters);

document.querySelector("[data-clear-filters]").addEventListener("click", () => {
  filterFrom.value = "";
  filterTo.value = "";
  filterProduct.value = "";
  reloadWithFilters();
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

document.querySelector("[data-sale-form]").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  if (!event.currentTarget.reportValidity()) return;

  const product = selectedProduct();
  const quantity = Number(quantityInput.value);
  if (!product) {
    showMessage("Choose a product before recording a sale.");
    return;
  }
  if (!Number.isSafeInteger(quantity) || quantity < 1) {
    showMessage("Quantity sold must be a whole number greater than zero.");
    return;
  }
  if (quantity > product.stock_quantity) {
    showMessage(`Only ${product.stock_quantity} units of ${product.name} are available.`);
    return;
  }

  submitSaleButton.disabled = true;
  submitSaleButton.textContent = "Recording…";
  try {
    const { data: sale } = await apiRequest("/sales", {
      method: "POST",
      body: JSON.stringify({ product_id: product.id, quantity }),
    });
    products = products.map((item) => (
      item.id === product.id
        ? { ...item, stock_quantity: item.stock_quantity - sale.quantity }
        : item
    ));
    renderProductOptions();
    quantityInput.value = "";
    showMessage("Sale recorded and stock updated.", "success");
    await reloadWithFilters();
  } catch (error) {
    showMessage(error.message);
    await loadPageData();
  } finally {
    submitSaleButton.textContent = "Record sale";
    updateSelectedStock();
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
