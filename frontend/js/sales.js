"use strict";

const TOKEN_STORAGE_KEY = "smartStock.accessToken";
const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
const apiBaseUrl = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");
const productSelect = document.querySelector("[data-sale-product]");
const quantityInput = document.querySelector("[data-sale-quantity]");
const availableStock = document.querySelector("[data-available-stock]");
const salesBody = document.querySelector("[data-sales-body]");
const salesCount = document.querySelector("[data-sales-count]");
const salesMessage = document.querySelector("[data-sales-message]");
const submitSaleButton = document.querySelector("[data-submit-sale]");

let products = [];
let sales = [];

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

  if (response.status === 204) return null;
  return response.json();
}

function formatMoney(value) {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
  updateSelectedStock();
}

function renderSales() {
  salesCount.textContent = `${sales.length} ${sales.length === 1 ? "sale" : "sales"}`;
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

async function loadPageData() {
  if (!token || !apiBaseUrl) {
    redirectToLogin();
    return;
  }

  try {
    const [user, productList, saleList] = await Promise.all([
      apiRequest("/auth/me"),
      apiRequest("/products"),
      apiRequest("/sales"),
    ]);
    document.querySelector("[data-business-identity]").textContent = `${user.full_name} · ${user.business_name}`;
    products = productList;
    sales = saleList;
    renderProductOptions();
    renderSales();
  } catch (error) {
    showMessage(error.message);
    productSelect.replaceChildren(new Option("Products could not be loaded", ""));
    submitSaleButton.disabled = true;
    salesCount.textContent = "—";
    salesBody.innerHTML = '<tr><td class="products-table__status" colspan="6">Sales history could not be loaded.</td></tr>';
  }
}

productSelect.addEventListener("change", updateSelectedStock);

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
    const sale = await apiRequest("/sales", {
      method: "POST",
      body: JSON.stringify({ product_id: product.id, quantity }),
    });
    products = products.map((item) => (
      item.id === product.id
        ? { ...item, stock_quantity: item.stock_quantity - sale.quantity }
        : item
    ));
    sales = [sale, ...sales];
    renderProductOptions();
    renderSales();
    quantityInput.value = "";
    showMessage("Sale recorded and stock updated.", "success");
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
    sales = sales.filter((item) => item.id !== sale.id);
    const product = products.find((item) => item.id === sale.product_id);
    if (product) product.stock_quantity += sale.quantity;
    renderProductOptions();
    renderSales();
    showMessage("Sale voided and stock restored.", "success");
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
