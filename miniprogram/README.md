# 纳斯达克基金限额小程序

这个目录是微信小程序项目。首页展示 GitHub Actions 每天生成的基金限额数据。当前默认使用直连数据源：

```text
https://bluepeople727-crypto.github.io/fund-limit-monitor/data/latest.json
```

项目里也保留了一个可选微信云函数：

```text
cloudfunctions/getLatestFundData
```

云函数同样会请求：

```text
https://bluepeople727-crypto.github.io/fund-limit-monitor/data/latest.json
```

## 本地预览

1. 安装并打开微信开发者工具。
2. 导入项目，目录选择 `miniprogram/`。
3. 没有正式 AppID 时，可以先用 `touristappid` 预览。
4. 当前版本选择“不使用云服务”即可，本地调试会直连 GitHub Pages 数据。

## 正式发布

1. 在微信公众平台注册小程序，拿到 AppID。
2. 把 `project.config.json` 里的 `appid` 改成正式 AppID。
3. 先在开发者工具里预览，确认首页能加载 30 只基金。
4. 点击“上传”，到微信公众平台提交审核。

如果你后续换成正式小程序并开通云开发，可以把 `app.js` 里的 `useCloudData` 改成 `true`，把 `cloudEnv` 填成云环境 ID，然后右键 `cloudfunctions/getLatestFundData`，选择“上传并部署：云端安装依赖”。

## 域名说明

当前默认直连 GitHub Pages，因此开发预览依赖 `project.config.json` 里的 `urlCheck: false`。正式发布时，需要在微信公众平台配置 request 合法域名；如果 GitHub Pages 域名不能用于审核，后续更稳的方案是换自己的备案域名，或启用上面的微信云函数。
