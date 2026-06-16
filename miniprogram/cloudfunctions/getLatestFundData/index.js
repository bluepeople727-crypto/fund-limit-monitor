const cloud = require("wx-server-sdk");
const https = require("https");

const DATA_URL = "https://bluepeople727-crypto.github.io/fund-limit-monitor/data/latest.json";
const REQUEST_TIMEOUT = 12000;

cloud.init({
  env: cloud.DYNAMIC_CURRENT_ENV
});

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    const request = https.get(
      `${url}?t=${Date.now()}`,
      {
        headers: {
          "User-Agent": "fund-limit-monitor-miniprogram/1.0",
          Accept: "application/json"
        },
        timeout: REQUEST_TIMEOUT
      },
      (response) => {
        const chunks = [];
        response.on("data", (chunk) => chunks.push(chunk));
        response.on("end", () => {
          const body = Buffer.concat(chunks).toString("utf8");
          if (response.statusCode < 200 || response.statusCode >= 300) {
            reject(new Error(`HTTP ${response.statusCode}: ${body.slice(0, 120)}`));
            return;
          }
          try {
            resolve(JSON.parse(body));
          } catch (error) {
            reject(new Error(`JSON parse failed: ${error.message}`));
          }
        });
      }
    );

    request.on("timeout", () => {
      request.destroy(new Error("Request timeout"));
    });
    request.on("error", reject);
  });
}

exports.main = async () => {
  try {
    const data = await fetchJson(DATA_URL);
    return {
      ok: true,
      fetchedAt: new Date().toISOString(),
      data
    };
  } catch (error) {
    return {
      ok: false,
      error: error.message || "Fetch latest fund data failed"
    };
  }
};
