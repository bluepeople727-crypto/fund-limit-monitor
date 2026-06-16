const state = {
  data: null,
  group: "all",
  status: "all",
  query: "",
};

const statusFilters = [
  ["all", "全部"],
  ["limited", "限额"],
  ["open", "开放"],
  ["paused", "暂停"],
  ["error", "异常"],
];

const statusLabels = {
  limited: "限额",
  paused: "暂停",
  open: "开放",
  error: "异常",
  unknown: "未知",
};

const elements = {
  updatedAt: document.querySelector("#updatedAt"),
  metricTotal: document.querySelector("#metricTotal"),
  metricLimitChanged: document.querySelector("#metricLimitChanged"),
  metricLimited: document.querySelector("#metricLimited"),
  metricErrors: document.querySelector("#metricErrors"),
  changesSection: document.querySelector("#changesSection"),
  searchInput: document.querySelector("#searchInput"),
  statusTabs: document.querySelector("#statusTabs"),
  groupTabs: document.querySelector("#groupTabs"),
  fundList: document.querySelector("#fundList"),
  emptyState: document.querySelector("#emptyState"),
  disclaimer: document.querySelector("#disclaimer"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalize(value) {
  return String(value ?? "").trim().toLowerCase();
}

function display(value, fallback = "未取到") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function setMetric(element, value) {
  element.textContent = Number.isFinite(value) ? String(value) : "--";
}

function renderMetrics() {
  const summary = state.data.summary || {};
  setMetric(elements.metricTotal, summary.total);
  setMetric(elements.metricLimitChanged, summary.limit_changed);
  setMetric(elements.metricLimited, summary.limited);
  setMetric(elements.metricErrors, summary.errors);
  elements.updatedAt.textContent = `${state.data.updated_at_display} 更新｜${state.data.source_name}`;
  elements.disclaimer.textContent = state.data.disclaimer;
}

function buttonHtml(key, label, count, active) {
  const suffix = typeof count === "number" ? `<span>${count}</span>` : "";
  return `<button type="button" data-key="${escapeHtml(key)}" aria-pressed="${active}">${escapeHtml(label)}${suffix}</button>`;
}

function renderTabs() {
  const funds = state.data.funds || [];
  elements.statusTabs.innerHTML = statusFilters
    .map(([key, label]) => {
      const count = key === "all" ? funds.length : funds.filter((fund) => fund.status_kind === key).length;
      return buttonHtml(key, label, count, state.status === key);
    })
    .join("");

  const groups = state.data.groups || [];
  const groupButtons = [buttonHtml("all", "全部分组", funds.length, state.group === "all")];
  for (const group of groups) {
    groupButtons.push(buttonHtml(group.name, group.name, group.count, state.group === group.name));
  }
  elements.groupTabs.innerHTML = groupButtons.join("");
}

function renderChanges() {
  const changes = state.data.changes || [];
  const limitChanges = changes.filter((fund) => fund.limit_change);
  if (!limitChanges.length) {
    elements.changesSection.hidden = false;
    elements.changesSection.innerHTML = `
      <div class="section-head">
        <h2>今日限额变化</h2>
        <span>无变化</span>
      </div>
      <p class="muted">当前批次没有发现日累计限额变化。</p>
    `;
    return;
  }

  elements.changesSection.hidden = false;
  elements.changesSection.innerHTML = `
    <div class="section-head">
      <h2>今日限额变化</h2>
      <span>${limitChanges.length} 只</span>
    </div>
    <div class="change-grid">
      ${limitChanges
        .map(
          (fund) => `
            <article class="change-item">
              <strong>${escapeHtml(fund.code)} ${escapeHtml(fund.short_name)}</strong>
              <small>${escapeHtml(fund.limit_change)}</small>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function filteredFunds() {
  const query = normalize(state.query);
  return (state.data.funds || []).filter((fund) => {
    const groupOk = state.group === "all" || fund.group_name === state.group;
    const statusOk = state.status === "all" || fund.status_kind === state.status;
    const queryOk =
      !query ||
      normalize(fund.code).includes(query) ||
      normalize(fund.name).includes(query) ||
      normalize(fund.short_name).includes(query);
    return groupOk && statusOk && queryOk;
  });
}

function renderFundCard(fund) {
  const statusKind = fund.status_kind || "unknown";
  const changedClass = fund.limit_change || (fund.changed || []).length ? " changed" : "";
  const errorClass = fund.error ? " error" : "";
  const statusLabel = statusLabels[statusKind] || "未知";
  const otherChanges = (fund.changed || []).filter((item) => !item.startsWith("日累计限额:"));
  return `
    <article class="fund-card${changedClass}${errorClass}">
      <div class="fund-main">
        <div class="fund-title">
          <span class="code">${escapeHtml(fund.code)}</span>
          <strong>${escapeHtml(fund.short_name || fund.name)}</strong>
        </div>
        <span class="pill ${escapeHtml(statusKind)}">${escapeHtml(statusLabel)}</span>
      </div>
      <div class="fund-data">
        <div class="data-cell">
          <span>日限额</span>
          <strong>${escapeHtml(display(fund.display_limit))}</strong>
        </div>
        <div class="data-cell">
          <span>申购状态</span>
          <strong>${escapeHtml(display(fund.purchase_status))}</strong>
        </div>
        <div class="data-cell">
          <span>持仓上限</span>
          <strong>${escapeHtml(display(fund.display_holding_limit))}</strong>
        </div>
      </div>
      ${
        fund.limit_change
          ? `<div class="fund-change">限额变化：${escapeHtml(fund.limit_change)}</div>`
          : ""
      }
      ${
        otherChanges.length
          ? `<div class="fund-change">其他变化：${escapeHtml(otherChanges.join("；"))}</div>`
          : ""
      }
      ${fund.error ? `<div class="fund-error">${escapeHtml(fund.error)}</div>` : ""}
      <div class="card-actions">
        <a href="${escapeHtml(fund.source_url)}" target="_blank" rel="noreferrer">查看来源</a>
      </div>
    </article>
  `;
}

function renderFunds() {
  const funds = filteredFunds();
  elements.fundList.innerHTML = funds.map(renderFundCard).join("");
  elements.emptyState.hidden = funds.length > 0;
}

function render() {
  renderMetrics();
  renderTabs();
  renderChanges();
  renderFunds();
}

function bindEvents() {
  elements.searchInput.addEventListener("input", (event) => {
    state.query = event.target.value;
    renderFunds();
  });
  elements.statusTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-key]");
    if (!button) return;
    state.status = button.dataset.key;
    renderTabs();
    renderFunds();
  });
  elements.groupTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-key]");
    if (!button) return;
    state.group = button.dataset.key;
    renderTabs();
    renderFunds();
  });
}

async function boot() {
  bindEvents();
  try {
    const response = await fetch("./data/latest.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.data = await response.json();
    render();
  } catch (error) {
    elements.updatedAt.textContent = "数据暂不可用";
    elements.fundList.innerHTML = "";
    elements.emptyState.hidden = false;
    elements.emptyState.querySelector("h2").textContent = "数据加载失败";
    elements.emptyState.querySelector("p").textContent = "请稍后刷新页面。";
  }
}

boot();
