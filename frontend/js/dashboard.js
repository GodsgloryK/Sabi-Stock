"use strict";

const TOKEN_STORAGE_KEY = "smartStock.accessToken";
const REFRESH_INTERVAL_MS = 60_000;
const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
const apiBaseUrl = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");
const messageElement = document.querySelector("[data-dashboard-message]");
const refreshButton = document.querySelector("[data-refresh]");
const refreshLabel = document.querySelector("[data-refresh-label]");
const chartEmpty = document.querySelector("[data-chart-empty]");
let topProductsChart = null;
let refreshTimer = null;

function returnToLogin() {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
}

function showMessage(message) {
  messageElement.textContent = message;
  messageElement.hidden = false;
}

function clearMessage() {
  messageElement.textContent = "";
  messageElement.hidden = true;
}

function formatCount(value) {
  return Number(value).toLocaleString();
}

function formatAmount(value) {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? amount.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
    : "0.00";
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

function renderLowStock(products) {
  const list = document.querySelector("[data-low-stock-list]");
  if (products.length === 0) {
    list.innerHTML = '<p class="panel-empty-inline">All products have at least 5 units in stock.</p>';
    return;
  }

  list.innerHTML = products.map((product) => `
    <div class="low-stock-item">
      <span class="low-stock-item__icon" aria-hidden="true">!</span>
      <span class="low-stock-item__details">
        <strong>${escapeHtml(product.name)}</strong>
        <span>${escapeHtml(product.category)}</span>
      </span>
      <span class="low-stock-quantity">${formatCount(product.stock_quantity)} left</span>
    </div>
  `).join("");
}

function renderTopProducts(products) {
  const table = document.querySelector("[data-top-products]");
  if (products.length === 0) {
    table.innerHTML = '<tr><td class="dashboard-table__empty" colspan="3">No sales recorded yet.</td></tr>';
    return;
  }

  table.innerHTML = products.map((product, index) => `
    <tr>
      <td><span class="rank-badge">${index + 1}</span></td>
      <td><span class="dashboard-product-name">${escapeHtml(product.product_name)}</span></td>
      <td>${formatCount(product.quantity_sold)} units</td>
    </tr>
  `).join("");
}

function renderChart(products) {
  const canvas = document.querySelector("#top-products-chart");
  chartEmpty.hidden = products.length > 0;
  canvas.hidden = products.length === 0;
  if (products.length === 0) {
    topProductsChart?.destroy();
    topProductsChart = null;
    return;
  }
  if (typeof window.Chart !== "function") {
    chartEmpty.textContent = "The chart could not load. The best-selling products are listed below.";
    chartEmpty.hidden = false;
    return;
  }

  const chartData = {
    labels: products.map((product) => product.product_name),
    datasets: [{
      label: "Units sold",
      data: products.map((product) => product.quantity_sold),
      backgroundColor: ["#19764f", "#67a17b", "#9fc6a0", "#c9d9bd", "#e2e9d8"],
      borderRadius: 7,
      borderSkipped: false,
      maxBarThickness: 36,
    }],
  };

  if (topProductsChart) {
    topProductsChart.data = chartData;
    topProductsChart.update();
    return;
  }

  topProductsChart = new window.Chart(canvas, {
    type: "bar",
    data: chartData,
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (context) => `${formatCount(context.parsed.x)} units sold`,
          },
        },
      },
      scales: {
        x: {
          beginAtZero: true,
          ticks: { precision: 0, color: "#78867d" },
          grid: { color: "#edf1ec" },
          border: { display: false },
        },
        y: {
          ticks: { color: "#4e5d53" },
          grid: { display: false },
          border: { display: false },
        },
      },
    },
  });
}

function renderDashboard(data) {
  document.querySelector("[data-total-products]").textContent = formatCount(data.total_products);
  document.querySelector("[data-total-stock]").textContent = formatCount(data.total_stock_quantity);
  document.querySelector("[data-today-sales]").textContent = formatAmount(data.today_total_sales);
  document.querySelector("[data-today-profit]").textContent = formatAmount(data.today_total_profit);
  renderLowStock(data.low_stock_products);
  renderTopProducts(data.top_selling_products);
  renderChart(data.top_selling_products);
  document.querySelector("[data-last-updated]").textContent = `Updated ${new Intl.DateTimeFormat(
    undefined,
    { hour: "numeric", minute: "2-digit" },
  ).format(new Date())}`;
}

async function requestJson(path) {
  let response;
  try {
    response = await fetch(`${apiBaseUrl}/api${path}`, {
      headers: { Authorization: `Bearer ${token}` },
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
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : "Dashboard data could not be loaded. Please try again.",
    );
  }
  return response.json();
}

async function refreshDashboard({ loadIdentity = false } = {}) {
  clearMessage();
  refreshButton.disabled = true;
  refreshLabel.textContent = "Refreshing…";
  try {
    const dashboardPromise = requestJson("/dashboard");
    const identityPromise = loadIdentity ? requestJson("/auth/me") : Promise.resolve(null);
    const [data, user] = await Promise.all([dashboardPromise, identityPromise]);
    if (user) {
      document.querySelector("[data-user-identity]").textContent = `${user.full_name} · ${user.business_name}`;
      document.querySelector("[data-avatar]").textContent = user.full_name.trim().charAt(0).toLocaleUpperCase();
    }
    renderDashboard(data);
  } catch (error) {
    showMessage(error instanceof Error ? error.message : "Dashboard data could not be loaded.");
  } finally {
    refreshButton.disabled = false;
    refreshLabel.textContent = "Refresh data";
  }
}

refreshButton.addEventListener("click", () => refreshDashboard());
document.querySelector("[data-logout]").addEventListener("click", () => {
  if (refreshTimer !== null) window.clearInterval(refreshTimer);
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
});

if (!token || !apiBaseUrl) {
  returnToLogin();
} else {
  refreshDashboard({ loadIdentity: true });
  refreshTimer = window.setInterval(() => {
    if (!document.hidden) refreshDashboard();
  }, REFRESH_INTERVAL_MS);
}
