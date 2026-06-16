# 基金申购限额监控

这个小工具每天抓取天天基金 F10 的“购买信息（费率表）”，提取每只基金的申购状态、日累计申购限额、持仓上限，并按“纳斯达克100A”“纳斯达克主动基”“美股科技主动基”“其他主动基”分组输出或微信推送。微信内容会按状态和限额聚合成手机友好的 Markdown 列表，用标题、粗体状态标签和分隔线区分层级，避免表格在窄屏里挤成一团。Server酱不会渲染 HTML 颜色标签，所以当前版本不使用颜色。

## 快速开始

1. 复制配置：

   ```bash
   cp config.example.json config.json
   ```

2. 编辑 `config.json`：

   - `纳斯达克100A`：默认会从天天基金代码全集自动发现“纳斯达克100”相关的人民币/A 类基金，排除美元、C/E/I/D 类和场内 ETF。
   - `纳斯达克主动基`：默认会自动发现名称包含“纳斯达克”、类型为 `QDII-普通股票` 的 A 类主动基金。
   - `美股科技主动基`：放入互联网上常被用作“纳指/美股科技主动替代”的主动 QDII 人民币/A 类基金。
   - `其他主动基`：把你要监控的主动基金代码填进去，并把 `enabled` 改成 `true`。
   - `notify.enabled`：确认结果后改成 `true`。

3. 手动跑一次：

   ```bash
   python3 fund_limit_monitor.py --no-push
   ```

4. 配微信推送，三选一：

   Server酱：

   ```bash
   export SERVERCHAN_SENDKEY="你的_SENDKEY"
   ```

   PushPlus：

   ```bash
   export PUSHPLUS_TOKEN="你的_TOKEN"
   ```

   企业微信机器人：

   ```bash
   export WECOM_ROBOT_WEBHOOK="你的_WEBHOOK"
   ```

   同时把 `config.json` 里的 `notify.channel` 改为 `serverchan`、`pushplus` 或 `wecom`。

   如果后面用 launchd 定时运行，终端里的 `export` 通常不会被继承；最省心的方式是把对应 token 直接填进本地 `config.json`，并把 `notify.enabled` 改成 `true`。

5. 测试推送：

   ```bash
   python3 fund_limit_monitor.py --test-push
   ```

6. 正式运行：

   ```bash
   python3 fund_limit_monitor.py
   ```

## 每天自动运行

macOS 可以用仓库里的 `launchd/com.pkq.fund-limit-monitor.plist` 做模板。确认里面的路径和 Python 命令可用后：

```bash
cp launchd/com.pkq.fund-limit-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.pkq.fund-limit-monitor.plist
```

默认每天 08:30 运行一次。日志会写到 `logs/fund-limit-monitor.log` 和 `logs/fund-limit-monitor.err.log`。

如果已经加载过旧版本，修改后重载：

```bash
launchctl unload ~/Library/LaunchAgents/com.pkq.fund-limit-monitor.plist
cp launchd/com.pkq.fund-limit-monitor.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.pkq.fund-limit-monitor.plist
```

注意：本地 launchd 依赖电脑开机/唤醒和网络可用。如果电脑 08:30 不在线，推送无法保证准时。

## 云端 08:30 推送

仓库里提供了 GitHub Actions 模板：

```text
.github/workflows/daily-fund-limit-monitor.yml
```

它会在北京时间每天 08:30 运行，并用缓存保存上一轮状态，用来判断限额是否变化。使用前在 GitHub 仓库设置 Secret：

```text
SERVERCHAN_SENDKEY = 你的 Server酱 SendKey
```

路径：仓库 Settings -> Secrets and variables -> Actions -> New repository secret。

云端运行不依赖你的电脑是否联网，更适合固定时间推送。

## 常用参数

```bash
python3 fund_limit_monitor.py --no-push
python3 fund_limit_monitor.py --only-changed
python3 fund_limit_monitor.py --print-json
python3 fund_limit_monitor.py --config config.json --state .fund_limit_state.json
```

`notify.only_on_change` 设为 `true` 后，只有限额或状态变化时才推送；默认是每天推送一份完整摘要。

每次运行会读取 `.fund_limit_state.json` 和上一轮结果比较。正文顶部会显示 `限额变化：无` 或 `限额变化：N只`；如果某只基金日累计限额变了，会先在顶部 `限额变化明细` 里列出基金代码、短名和 `旧值 -> 新值`，并在该基金下方再次标出。

## 纳指基金自动发现规则

`config.json` 里的 `纳斯达克100A.discover` 和 `纳斯达克主动基.discover` 会每次运行时读取：

```text
https://fund.eastmoney.com/js/fundcode_search.js
```

默认筛选规则：

- 名称包含 `纳斯达克100`
- 类型包含 `指数型-海外股票`
- 名称包含 A，或是无份额后缀的 `国泰纳斯达克100指数`
- 排除美元、现汇、现钞份额
- 排除场内 ETF 代码 `159513`、`159659`

如果你想监控 C 类、美元份额或场内 ETF，可以直接改 `discover` 规则，或在 `funds` 里手动加代码。

当前严格“纳斯达克主动基”的自动发现口径较窄：名称包含 `纳斯达克`，且基金类型为 `QDII-普通股票`。更宽口径的美股科技主动基金放在 `美股科技主动基`，避免和纳指 100 指数基金混在一起。

## 数据说明

数据来自天天基金公开页面，例如：

```text
https://fundf10.eastmoney.com/jjfl_040046.html
```

页面展示的是天天基金销售渠道信息，不一定等同于所有平台或基金公司直销渠道的限额。交易前仍应以你实际下单平台显示为准。
