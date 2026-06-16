# 纳斯达克基金限额小程序

这个目录是微信小程序项目。首页展示 GitHub Actions 每天生成的基金限额数据，并优先通过微信云函数读取：

```text
cloudfunctions/getLatestFundData
```

云函数会请求：

```text
https://bluepeople727-crypto.github.io/fund-limit-monitor/data/latest.json
```

## 本地预览

1. 安装并打开微信开发者工具。
2. 导入项目，目录选择 `miniprogram/`。
3. 没有正式 AppID 时，可以先用 `touristappid` 预览。
4. 本地调试如果没开通云开发，页面会自动退回直连 GitHub Pages 数据。

## 正式发布

1. 在微信公众平台注册小程序，拿到 AppID。
2. 把 `project.config.json` 里的 `appid` 改成正式 AppID。
3. 在开发者工具里开通云开发，复制云环境 ID。
4. 把 `app.js` 里的 `cloudEnv` 填成云环境 ID。
5. 右键 `cloudfunctions/getLatestFundData`，选择“上传并部署：云端安装依赖”。
6. 在开发者工具里预览，确认首页能加载 30 只基金。
7. 点击“上传”，到微信公众平台提交审核。

## 域名说明

当前小程序端优先请求微信云函数，不直接请求 GitHub Pages。这样正式版通常只需要保证云函数能访问外网数据；如果你关闭云函数改为直连，则需要在微信公众平台配置 request 合法域名。生产长期使用更稳的方案是把 `latest.json` 同步到自己的备案域名或完全放进云开发存储/数据库。
