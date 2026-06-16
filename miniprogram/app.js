App({
  onLaunch() {
    if (!this.globalData.useCloudData || !wx.cloud) return;
    const options = { traceUser: false };
    if (this.globalData.cloudEnv) {
      options.env = this.globalData.cloudEnv;
    }
    wx.cloud.init(options);
  },

  globalData: {
    useCloudData: true,
    cloudEnv: "",
    cloudFunctionName: "getLatestFundData",
    dataUrl: "https://bluepeople727-crypto.github.io/fund-limit-monitor/data/latest.json"
  }
});
