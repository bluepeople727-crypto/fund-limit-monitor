const app = getApp();

const STATUS_TABS = [
  { key: "all", label: "全部" },
  { key: "limited", label: "限额" },
  { key: "open", label: "开放" },
  { key: "paused", label: "暂停" },
  { key: "error", label: "异常" }
];

const STATUS_LABELS = {
  limited: "限额",
  paused: "暂停",
  open: "开放",
  error: "异常",
  unknown: "未知"
};

function cleanText(value, fallback = "未取到") {
  const text = String(value || "").trim();
  return text || fallback;
}

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

function displayDateOnly(value) {
  const text = String(value || "").trim();
  return text.split(/\s+/)[0] || "--";
}

function prepareFund(fund) {
  const statusClass = fund.status_kind || "unknown";
  const changed = Array.isArray(fund.changed) ? fund.changed : [];
  const otherChanges = changed.filter((item) => !String(item).startsWith("日累计限额:"));
  const displayName = fund.short_name || fund.name || fund.code;
  return {
    ...fund,
    displayName,
    displayLimit: cleanText(fund.display_limit),
    purchaseStatus: cleanText(fund.purchase_status),
    holdingLimit: cleanText(fund.display_holding_limit),
    statusClass,
    statusText: STATUS_LABELS[statusClass] || STATUS_LABELS.unknown,
    hasChange: Boolean(fund.limit_change) || changed.length > 0,
    hasError: Boolean(fund.error),
    otherChangeText: otherChanges.join("；"),
    haystack: normalize(`${fund.code} ${fund.name} ${fund.short_name} ${fund.group_name}`)
  };
}

Page({
  data: {
    loading: true,
    error: "",
    query: "",
    activeStatus: "all",
    activeGroup: "all",
    updatedText: "等待数据更新",
    disclaimer: "",
    metrics: [],
    statusTabs: [],
    groupTabs: [],
    funds: [],
    filteredFunds: [],
    limitChanges: []
  },

  onLoad() {
    this.fetchData();
  },

  onPullDownRefresh() {
    this.fetchData(true);
  },

  refreshData() {
    this.fetchData();
  },

  fetchData(isPullDown = false) {
    if (!isPullDown) {
      this.setData({ loading: true, error: "" });
    }
    this.loadPayload()
      .then((payload) => {
        this.applyPayload(payload);
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error.message || "网络请求失败"
        });
      })
      .finally(() => {
        if (isPullDown) {
          wx.stopPullDownRefresh();
        }
      });
  },

  loadPayload() {
    if (app.globalData.useCloudData && wx.cloud && wx.cloud.callFunction) {
      return this.requestPayloadFromCloud().catch(() => this.requestPayloadDirectly());
    }
    return this.requestPayloadDirectly();
  },

  requestPayloadFromCloud() {
    return new Promise((resolve, reject) => {
      wx.cloud.callFunction({
        name: app.globalData.cloudFunctionName,
        success: (response) => {
          const result = response.result || {};
          const payload = result.data || result;
          if (payload && Array.isArray(payload.funds)) {
            resolve(payload);
            return;
          }
          reject(new Error(result.error || "云函数返回数据异常"));
        },
        fail: (error) => {
          reject(new Error(error.errMsg || "云函数调用失败"));
        }
      });
    });
  },

  requestPayloadDirectly() {
    return new Promise((resolve, reject) => {
      wx.request({
        url: `${app.globalData.dataUrl}?t=${Date.now()}`,
        method: "GET",
        timeout: 12000,
        success: (response) => {
          if (response.statusCode < 200 || response.statusCode >= 300 || !response.data) {
            reject(new Error(`HTTP ${response.statusCode || "异常"}`));
            return;
          }
          resolve(response.data);
        },
        fail: (error) => {
          reject(new Error(error.errMsg || "网络请求失败"));
        }
      });
    });
  },

  applyPayload(payload) {
    const funds = (payload.funds || []).map(prepareFund);
    const limitChanges = funds.filter((fund) => Boolean(fund.limit_change));
    const summary = payload.summary || {};
    this.setData(
      {
        loading: false,
        error: "",
        updatedText: `${displayDateOnly(payload.updated_at_display)} 更新｜${payload.source_name || "数据源"}`,
        disclaimer: payload.disclaimer || "",
        metrics: [
          { label: "监控基金", value: summary.total || funds.length || 0, tone: "teal" },
          { label: "限额变化", value: summary.limit_changed || 0, tone: "amber" },
          { label: "限额状态", value: summary.limited || 0, tone: "blue" },
          { label: "获取异常", value: summary.errors || 0, tone: "red" }
        ],
        groups: payload.groups || [],
        funds,
        limitChanges
      },
      () => {
        this.refreshTabs();
        this.applyFilters();
      }
    );
  },

  refreshTabs() {
    const funds = this.data.funds;
    const activeStatus = this.data.activeStatus;
    const activeGroup = this.data.activeGroup;
    const statusTabs = STATUS_TABS.map((tab) => ({
      ...tab,
      count: tab.key === "all" ? funds.length : funds.filter((fund) => fund.status_kind === tab.key).length,
      active: tab.key === activeStatus
    }));
    const groupTabs = [
      { key: "all", label: "全部分组", count: funds.length, active: activeGroup === "all" },
      ...(this.data.groups || []).map((group) => ({
        key: group.name,
        label: group.name,
        count: group.count,
        active: group.name === activeGroup
      }))
    ];
    this.setData({ statusTabs, groupTabs });
  },

  applyFilters() {
    const query = normalize(this.data.query);
    const activeStatus = this.data.activeStatus;
    const activeGroup = this.data.activeGroup;
    const filteredFunds = this.data.funds.filter((fund) => {
      const statusOk = activeStatus === "all" || fund.status_kind === activeStatus;
      const groupOk = activeGroup === "all" || fund.group_name === activeGroup;
      const queryOk = !query || fund.haystack.includes(query);
      return statusOk && groupOk && queryOk;
    });
    this.setData({ filteredFunds });
  },

  onSearchInput(event) {
    this.setData({ query: event.detail.value || "" }, () => {
      this.applyFilters();
    });
  },

  changeStatus(event) {
    const activeStatus = event.currentTarget.dataset.key;
    this.setData({ activeStatus }, () => {
      this.refreshTabs();
      this.applyFilters();
    });
  },

  changeGroup(event) {
    const activeGroup = event.currentTarget.dataset.key;
    this.setData({ activeGroup }, () => {
      this.refreshTabs();
      this.applyFilters();
    });
  },

  copySource(event) {
    const url = event.currentTarget.dataset.url;
    if (!url) return;
    wx.setClipboardData({
      data: url,
      success: () => {
        wx.showToast({
          title: "已复制来源",
          icon: "success"
        });
      }
    });
  }
});
