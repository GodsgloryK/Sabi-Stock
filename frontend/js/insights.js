"use strict";

const TOKEN_STORAGE_KEY = "smartStock.accessToken";
const token = sessionStorage.getItem(TOKEN_STORAGE_KEY);
const apiBaseUrl = window.SMART_STOCK_CONFIG?.apiBaseUrl?.replace(/\/+$/, "");
const messageElement = document.querySelector("[data-insights-message]");
const refreshButton = document.querySelector("[data-refresh]");
const refreshLabel = document.querySelector("[data-refresh-label]");
const restockBody = document.querySelector("[data-restock-body]");
const insightList = document.querySelector("[data-insight-list]");
const insightCount = document.querySelector("[data-insight-count]");
const briefingText = document.querySelector("[data-briefing]");
const briefingSource = document.querySelector("[data-briefing-source]");
const productSelect = document.querySelector("[data-forecast-product]");
const forecastChartEmpty = document.querySelector("[data-forecast-chart-empty]");

let forecastProducts = [];
let forecastChart = null;

const URGENCY_LABELS = {
  out: "Out of stock",
  critical: "Order today",
  soon: "Order soon",
  ok: "On track",
  no_sales: "No sales",
};

const URGENCY_MODIFIERS = {
  out: "urgency-badge--out",
  critical: "urgency-badge--critical",
  soon: "urgency-badge--soon",
  ok: "urgency-badge--ok",
  no_sales: "urgency-badge--idle",
};

const SEVERITY_LABELS = { high: "High", medium: "Medium", low: "Low" };

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

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(`${String(value).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatCount(value) {
  return Number(value).toLocaleString();
}

function trendMarkup(trendPct) {
  const value = Number(trendPct);
  if (!Number.isFinite(value) || value === 0) {
    return '<span class="forecast-trend forecast-trend--flat" title="No change vs previous month">→ 0%</span>';
  }
  const direction = value > 0 ? "up" : "down";
  const arrow = value > 0 ? "↑" : "↓";
  return `<span class="forecast-trend forecast-trend--${direction}">${arrow} ${Math.abs(value).toFixed(0)}%</span>`;
}

function urgencyBadge(urgency) {
  const modifier = URGENCY_MODIFIERS[urgency] || "urgency-badge--idle";
  const label = URGENCY_LABELS[urgency] || urgency;
  return `<span class="urgency-badge ${modifier}">${escapeHtml(label)}</span>`;
}

function renderBriefing(data) {
  briefingText.textContent = data.briefing;
  if (data.briefing_source === "gemini") {
    briefingSource.textContent = "Gemini AI";
    briefingSource.hidden = false;
  } else {
    briefingSource.textContent = "Forecast engine";
    briefingSource.hidden = false;
  }
  document.querySelector("[data-lead-time]").textContent = String(data.lead_time_days);
}

function renderRestockTable(products) {
  if (products.length === 0) {
    restockBody.innerHTML = '<tr><td class="dashboard-table__empty" colspan="8">No products yet. Add products to get a forecast.</td></tr>';
    return;
  }

  restockBody.innerHTML = products.map((product) => `
    <tr>
      <td>
        <span class="dashboard-product-name">${escapeHtml(product.name)}</span>
        <span class="sku-code">${escapeHtml(product.sku)}</span>
      </td>
      <td>${formatCount(product.stock_quantity)}</td>
      <td>${Number(product.avg_daily_sales).toFixed(1)}</td>
      <td>${trendMarkup(product.trend_pct)}</td>
      <td>${product.predicted_stockout_date ? escapeHtml(formatDate(product.predicted_stockout_date)) : "—"}</td>
      <td>${product.reorder_by_date ? escapeHtml(formatDate(product.reorder_by_date)) : "—"}</td>
      <td>${product.suggested_reorder_qty > 0 ? formatCount(product.suggested_reorder_qty) : "—"}</td>
      <td>${urgencyBadge(product.urgency)}</td>
    </tr>
  `).join("");
}

function populateProductSelect(products) {
  const previous = productSelect.value;
  productSelect.replaceChildren();
  products.forEach((product, index) => {
    const option = new Option(`${product.name} (${product.sku})`, String(index));
    productSelect.add(option);
  });
  if (previous && Number(previous) < products.length) {
    productSelect.value = previous;
  }
}

function renderForecastChart(product) {
  const canvas = document.querySelector("#forecast-chart");
  const hasHistory = product.history.some((point) => point.units > 0);
  const hasForecast = product.forecast.length > 0;
  forecastChartEmpty.hidden = hasHistory && hasForecast;
  canvas.hidden = !(hasHistory && hasForecast);
  if (!(hasHistory && hasForecast)) {
    forecastChart?.destroy();
    forecastChart = null;
    return;
  }
  if (typeof window.Chart !== "function") {
    forecastChartEmpty.textContent = "The chart could not load. The forecast table above still has every number.";
    forecastChartEmpty.hidden = false;
    return;
  }

  const labels = [
    ...product.history.map((point) => point.day),
    ...product.forecast.map((point) => point.day),
  ];
  const historyData = [
    ...product.history.map((point) => point.units),
    ...product.forecast.map(() => null),
  ];
  const lastHistoryValue = product.history.length
    ? product.history[product.history.length - 1].units
    : null;
  const forecastData = [
    ...product.history.map(() => null),
    lastHistoryValue,
    ...product.forecast.map((point) => point.units),
  ];

  const chartData = {
    labels,
    datasets: [
      {
        label: "Units sold (history)",
        data: historyData,
        borderColor: "#F59E0B",
        backgroundColor: "rgb(245 158 11 / 14%)",
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 5,
        spanGaps: false,
      },
      {
        label: "Forecast",
        data: forecastData,
        borderColor: "#2563EB",
        borderDash: [6, 5],
        backgroundColor: "rgba(37, 99, 235, 8%)",
        fill: false,
        tension: 0.3,
        pointRadius: 3,
        pointHoverRadius: 5,
        spanGaps: false,
      },
    ],
  };

  if (forecastChart) {
    forecastChart.data = chartData;
    forecastChart.options.plugins.tooltip.callbacks.label = (context) =>
      `${context.dataset.label}: ${formatCount(context.parsed.y)} units`;
    forecastChart.update();
    return;
  }

  forecastChart = new window.Chart(canvas, {
    type: "line",
    data: chartData,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: "bottom",
          labels: { color: "#6E5F52", boxWidth: 12, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: (context) => `${context.dataset.label}: ${formatCount(context.parsed.y)} units`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#6E5F52", maxTicksLimit: 8, maxRotation: 0 },
          grid: { display: false },
          border: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: { precision: 0, color: "#6E5F52" },
          grid: { color: "#E6DED2" },
          border: { display: false },
        },
      },
    },
  });
}

function renderInsights(insights) {
  insightCount.textContent = `${insights.length} flag${insights.length === 1 ? "" : "s"}`;
  if (insights.length === 0) {
    insightList.innerHTML = '<p class="panel-empty-inline">Nothing unusual in your recent sales. Spikes, drops, stale stock, and below-cost sales will show up here.</p>';
    return;
  }

  insightList.innerHTML = insights.map((insight) => `
    <div class="insight-item insight-item--${escapeHtml(insight.severity)}">
      <div class="insight-item__head">
        <span class="insight-severity insight-severity--${escapeHtml(insight.severity)}">${escapeHtml(SEVERITY_LABELS[insight.severity] || insight.severity)}</span>
        <strong>${escapeHtml(insight.title)}</strong>
      </div>
      <p>${escapeHtml(insight.detail)}</p>
    </div>
  `).join("");
}

function renderChartForSelection() {
  const product = forecastProducts[Number(productSelect.value) || 0];
  if (product) renderForecastChart(product);
}

async function requestJson(path) {
  let response;
  try {
    response = await fetch(`${apiBaseUrl}/api${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new Error("Unable to reach Smart Stock. Check your connection and try again.");
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
        : "Insights could not be loaded. Please try again.",
    );
  }
  return response.json();
}

async function refreshInsights({ loadIdentity = false } = {}) {
  clearMessage();
  refreshButton.disabled = true;
  refreshLabel.textContent = "Analysing…";
  try {
    const forecastPromise = requestJson("/ai/forecast");
    const insightsPromise = requestJson("/ai/insights");
    const identityPromise = loadIdentity ? requestJson("/auth/me") : Promise.resolve(null);
    const [forecast, insights, user] = await Promise.all([
      forecastPromise,
      insightsPromise,
      identityPromise,
    ]);
    if (user) {
      document.querySelector("[data-user-identity]").textContent = `${user.full_name} · ${user.business_name}`;
      document.querySelector("[data-avatar]").textContent = user.full_name.trim().charAt(0).toLocaleUpperCase();
      if (user.role === "owner") {
        document.querySelectorAll("[data-owner-only]").forEach((element) => { element.hidden = false; });
      }
    }
    forecastProducts = forecast.products;
    renderBriefing(forecast);
    renderRestockTable(forecast.products);
    populateProductSelect(forecast.products);
    renderChartForSelection();
    renderInsights(insights.insights);
    document.querySelector("[data-last-updated]").textContent = `Updated ${new Intl.DateTimeFormat(
      undefined,
      { hour: "numeric", minute: "2-digit" },
    ).format(new Date())}`;
  } catch (error) {
    showMessage(error instanceof Error ? error.message : "Insights could not be loaded.");
  } finally {
    refreshButton.disabled = false;
    refreshLabel.textContent = "Refresh analysis";
  }
}

refreshButton.addEventListener("click", () => refreshInsights());
productSelect.addEventListener("change", renderChartForSelection);
document.querySelector("[data-logout]").addEventListener("click", () => {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.location.replace("./login.html");
});

if (!token || !apiBaseUrl) {
  returnToLogin();
} else {
  refreshInsights({ loadIdentity: true });
}
