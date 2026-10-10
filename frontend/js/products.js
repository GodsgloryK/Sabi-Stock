"use strict";

const TOKEN_STORAGE_KEY = "smartStock.accessToken";
const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
const apiBaseUrl = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");
const productForm = document.querySelector("[data-product-form]");
const formCard = document.querySelector("[data-form-card]");
const productsBody = document.querySelector("[data-products-body]");
const pageMessage = document.querySelector("[data-page-message]");
const productCount = document.querySelector("[data-product-count]");
const categoryFilter = document.querySelector("[data-category-filter]");
const searchInput = document.querySelector("[data-search]");
const exportProductsButton = document.querySelector("[data-export-products]");

const LOW_STOCK_THRESHOLD = 5;
let products = [];
let editingProductId = null;

function returnToLogin() {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
}

function showMessage(message, type = "error") {
  pageMessage.textContent = message;
  pageMessage.className = `form-message form-message--${type} product-page-message`;
  pageMessage.hidden = false;
}

function clearMessage() {
  pageMessage.textContent = "";
  pageMessage.hidden = true;
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
    const message = typeof detail === "string"
      ? detail
      : response.status >= 500
        ? "The service is temporarily unavailable. Please try again shortly."
        : "The request could not be completed. Check your details and try again.";
    throw new Error(message);
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

function stockBadge(quantity) {
  if (quantity === 0) {
    return `<span class="stock-value">${quantity}</span><span class="stock-badge stock-badge--out">Out</span>`;
  }
  if (quantity < LOW_STOCK_THRESHOLD) {
    return `<span class="stock-value">${quantity}</span><span class="stock-badge stock-badge--low">Low</span>`;
  }
  return `<span class="stock-value">${quantity}</span>`;
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

function refreshCategories() {
  const selectedCategory = categoryFilter.value;
  const categories = [...new Set(products.map((product) => product.category))]
    .sort((first, second) => first.localeCompare(second));

  categoryFilter.replaceChildren(new Option("All categories", ""));
  categories.forEach((category) => {
    categoryFilter.add(new Option(category, category));
  });
  if (categories.includes(selectedCategory)) {
    categoryFilter.value = selectedCategory;
  }
}

function renderProducts() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  const category = categoryFilter.value;
  const visibleProducts = products.filter((product) => {
    const matchesName = product.name.toLocaleLowerCase().includes(query);
    const matchesCategory = !category || product.category === category;
    return matchesName && matchesCategory;
  });

  productCount.textContent = `${visibleProducts.length} ${visibleProducts.length === 1 ? "product" : "products"}`;
  if (visibleProducts.length === 0) {
    const message = products.length === 0
      ? "No products yet. Add your first product to get started."
      : "No products match your search or category filter.";
    productsBody.innerHTML = `<tr><td class="products-table__status" colspan="6">${message}</td></tr>`;
    return;
  }

  productsBody.innerHTML = visibleProducts.map((product) => `
    <tr>
      <td data-label="Product"><span class="product-name">${escapeHtml(product.name)}</span></td>
      <td data-label="Category"><span class="category-badge">${escapeHtml(product.category)}</span></td>
      <td data-label="Buying price">${formatPrice(product.buying_price)}</td>
      <td data-label="Selling price">${formatPrice(product.selling_price)}</td>
      <td data-label="Stock quantity">${stockBadge(product.stock_quantity)}</td>
      <td data-label="Actions" class="products-table__actions">
        <button class="table-action" type="button" data-edit-product="${escapeHtml(product.id)}">Edit</button>
        <button class="table-action table-action--delete" type="button" data-delete-product="${escapeHtml(product.id)}">Delete</button>
      </td>
    </tr>
  `).join("");
}

async function loadProducts() {
  productsBody.innerHTML = '<tr><td class="products-table__status" colspan="6">Loading your products…</td></tr>';
  const result = await apiRequest("/products");
  products = result;
  refreshCategories();
  renderProducts();
}

function closeForm() {
  editingProductId = null;
  productForm.reset();
  formCard.hidden = true;
  document.querySelector("[data-form-title]").textContent = "Add a product";
  document.querySelector("[data-save-product]").textContent = "Save product";
}

function openCreateForm() {
  clearMessage();
  closeForm();
  formCard.hidden = false;
  document.querySelector("#product-name").focus();
  formCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function openEditForm(productId) {
  clearMessage();
  const editButton = productsBody.querySelector(`[data-edit-product="${CSS.escape(productId)}"]`);
  if (editButton) editButton.disabled = true;

  try {
    const product = await apiRequest(`/products/${encodeURIComponent(productId)}`);
    editingProductId = product.id;
    productForm.elements.name.value = product.name;
    productForm.elements.category.value = product.category;
    productForm.elements.buying_price.value = product.buying_price;
    productForm.elements.selling_price.value = product.selling_price;
    productForm.elements.stock_quantity.value = product.stock_quantity;
    document.querySelector("[data-form-title]").textContent = "Edit product";
    document.querySelector("[data-save-product]").textContent = "Save changes";
    formCard.hidden = false;
    document.querySelector("#product-name").focus();
    formCard.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showMessage(error.message);
    if (editButton) editButton.disabled = false;
  }
}

async function deleteProduct(productId) {
  const product = products.find((item) => item.id === productId);
  if (!product || !window.confirm(`Delete "${product.name}"? This cannot be undone.`)) return;

  clearMessage();
  try {
    await apiRequest(`/products/${encodeURIComponent(productId)}`, { method: "DELETE" });
    products = products.filter((item) => item.id !== productId);
    refreshCategories();
    renderProducts();
    showMessage("Product deleted.", "success");
  } catch (error) {
    showMessage(error.message);
  }
}

productForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearMessage();
  if (!productForm.reportValidity()) return;

  const values = new FormData(productForm);
  const payload = {
    name: String(values.get("name")).trim(),
    category: String(values.get("category")).trim(),
    buying_price: Number(values.get("buying_price")),
    selling_price: Number(values.get("selling_price")),
    stock_quantity: Number(values.get("stock_quantity")),
  };
  if (
    !payload.name
    || !payload.category
    || !Number.isFinite(payload.buying_price)
    || !Number.isFinite(payload.selling_price)
    || !Number.isSafeInteger(payload.stock_quantity)
    || payload.buying_price < 0
    || payload.selling_price < 0
    || payload.stock_quantity < 0
  ) {
    showMessage("Enter a name and category, prices of zero or more, and a whole-number stock quantity of zero or more.");
    return;
  }

  const submitButton = document.querySelector("[data-save-product]");
  const originalLabel = submitButton.textContent;
  submitButton.disabled = true;
  submitButton.textContent = editingProductId ? "Saving…" : "Adding…";

  try {
    const path = editingProductId
      ? `/products/${encodeURIComponent(editingProductId)}`
      : "/products";
    const savedProduct = await apiRequest(path, {
      method: editingProductId ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    const wasEditing = Boolean(editingProductId);
    const index = products.findIndex((product) => product.id === savedProduct.id);
    if (index >= 0) products[index] = savedProduct;
    else products.push(savedProduct);
    refreshCategories();
    closeForm();
    renderProducts();
    showMessage(wasEditing ? "Product updated." : "Product added.", "success");
  } catch (error) {
    showMessage(error.message);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = originalLabel;
  }
});

document.querySelector("[data-add-product]").addEventListener("click", openCreateForm);
document.querySelectorAll("[data-cancel-form]").forEach((button) => {
  button.addEventListener("click", closeForm);
});

exportProductsButton.addEventListener("click", async () => {
  clearMessage();
  exportProductsButton.disabled = true;
  const originalLabel = exportProductsButton.textContent;
  exportProductsButton.textContent = "Preparing…";
  try {
    const response = await fetch(`${apiBaseUrl}/api/reports/export/products.csv`, {
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
    link.download = "smart-stock-products.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    showMessage(error.message);
  } finally {
    exportProductsButton.disabled = false;
    exportProductsButton.textContent = originalLabel;
  }
});
document.querySelector("[data-logout]").addEventListener("click", () => {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
});
searchInput.addEventListener("input", renderProducts);
categoryFilter.addEventListener("change", renderProducts);
productsBody.addEventListener("click", (event) => {
  const editButton = event.target.closest("[data-edit-product]");
  if (editButton) {
    openEditForm(editButton.dataset.editProduct);
    return;
  }

  const deleteButton = event.target.closest("[data-delete-product]");
  if (deleteButton) deleteProduct(deleteButton.dataset.deleteProduct);
});

async function initializeProductsPage() {
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
    await loadProducts();
  } catch (error) {
    showMessage(error.message);
    productsBody.innerHTML = '<tr><td class="products-table__status" colspan="6">Products could not be loaded.</td></tr>';
    productCount.textContent = "—";
  }
}

initializeProductsPage();
