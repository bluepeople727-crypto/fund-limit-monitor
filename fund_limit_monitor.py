#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


F10_URL = "https://fundf10.eastmoney.com/jjfl_{code}.html"
PINGZHONG_URL = "https://fund.eastmoney.com/pingzhongdata/{code}.js"
FUND_CODE_SEARCH_URL = "https://fund.eastmoney.com/js/fundcode_search.js"
DEFAULT_TIMEOUT = 20
DEFAULT_FETCH_ATTEMPTS = 3
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)


@dataclass
class FundResult:
    code: str
    group_name: str
    group_type: str
    configured_name: str = ""
    name: str = ""
    purchase_status: str = ""
    redeem_status: str = ""
    invest_status: str = ""
    daily_limit: str = ""
    daily_limit_yuan: float | None = None
    banner_limit: str = ""
    purchase_start: str = ""
    first_purchase: str = ""
    additional_purchase: str = ""
    holding_limit: str = ""
    source_url: str = ""
    fetched_at: str = ""
    changed: list[str] = field(default_factory=list)
    limit_change: str = ""
    error: str = ""

    def state_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purchase_status": self.purchase_status,
            "daily_limit": self.daily_limit,
            "banner_limit": self.banner_limit,
            "holding_limit": self.holding_limit,
            "error": self.error,
        }


class MonitorError(RuntimeError):
    pass


def fetch_text(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    attempts: int = DEFAULT_FETCH_ATTEMPTS,
) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
            try:
                return body.decode(charset, errors="replace")
            except LookupError:
                return body.decode("utf-8", errors="replace")
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(0.8 * (attempt + 1))
    assert last_error is not None
    raise last_error


def clean_text(fragment: str) -> str:
    fragment = html.unescape(fragment)
    fragment = re.sub(r"(?is)<script.*?</script>", "", fragment)
    fragment = re.sub(r"(?is)<style.*?</style>", "", fragment)
    fragment = re.sub(r"(?s)<[^>]+>", "", fragment)
    fragment = fragment.replace("\xa0", " ")
    return re.sub(r"\s+", " ", fragment).strip()


def extract_cell(page: str, label: str) -> str:
    pattern = (
        r"<td[^>]*>\s*"
        + re.escape(label)
        + r"\s*</td>\s*<td[^>]*>(.*?)</td>"
    )
    match = re.search(pattern, page, flags=re.S)
    return clean_text(match.group(1)) if match else ""


def extract_title_name(page: str, code: str) -> str:
    match = re.search(r"<title>(.*?)</title>", page, flags=re.S)
    if not match:
        return ""
    title = clean_text(match.group(1))
    title = re.sub(r"\(" + re.escape(code) + r"\).*", "", title).strip()
    title = re.sub(r"基金费率.*", "", title).strip()
    return title


def extract_pingzhong_name(page: str) -> str:
    match = re.search(r'var\s+fS_name\s*=\s*"([^"]+)"', page)
    return html.unescape(match.group(1)).strip() if match else ""


def parse_money_yuan(text: str) -> float | None:
    text = clean_text(text)
    if not text or "---" in text or "无限" in text or "不限" in text:
        return None
    text = text.replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([万亿]?)\s*元?", text)
    if not match:
        return None
    try:
        value = Decimal(match.group(1))
    except InvalidOperation:
        return None
    unit = match.group(2)
    if unit == "万":
        value *= Decimal("10000")
    elif unit == "亿":
        value *= Decimal("100000000")
    return float(value)


def fetch_fund_catalog() -> list[dict[str, str]]:
    page = fetch_text(FUND_CODE_SEARCH_URL, timeout=25)
    match = re.search(r"var\s+r\s*=\s*(\[.*\]);", page, flags=re.S)
    if not match:
        raise MonitorError("没有解析到天天基金代码全集")
    rows = json.loads(match.group(1))
    catalog: list[dict[str, str]] = []
    for row in rows:
        if len(row) >= 4 and re.fullmatch(r"\d{6}", row[0]):
            catalog.append({"code": row[0], "name": row[2], "fund_type": row[3]})
    return catalog


def discover_funds(group: dict[str, Any], catalog: list[dict[str, str]]) -> list[dict[str, str]]:
    discover = group.get("discover") or {}
    if not discover.get("enabled", False):
        return []

    raw_keywords = discover.get("keywords", discover.get("keyword", []))
    if isinstance(raw_keywords, str):
        keywords = [raw_keywords]
    else:
        keywords = [str(keyword) for keyword in raw_keywords]

    include_pattern = str(discover.get("include_name_regex", "")).strip()
    exclude_pattern = str(discover.get("exclude_name_regex", "")).strip()
    fund_type_contains = str(discover.get("fund_type_contains", "")).strip()
    exclude_codes = {str(code) for code in discover.get("exclude_codes", [])}

    discovered: list[dict[str, str]] = []
    for item in catalog:
        code = item["code"]
        name = item["name"]
        fund_type = item["fund_type"]
        if code in exclude_codes:
            continue
        if keywords and not all(keyword in name for keyword in keywords):
            continue
        if fund_type_contains and fund_type_contains not in fund_type:
            continue
        if include_pattern and not re.search(include_pattern, name):
            continue
        if exclude_pattern and re.search(exclude_pattern, name):
            continue
        discovered.append({"code": code, "alias": name})
    return discovered


def parse_limit_page(code: str, group_name: str, group_type: str, alias: str, now: str) -> FundResult:
    url = F10_URL.format(code=code)
    result = FundResult(
        code=code,
        group_name=group_name,
        group_type=group_type,
        configured_name=alias,
        source_url=url,
        fetched_at=now,
    )

    page = fetch_text(url)
    result.name = extract_title_name(page, code) or alias
    result.purchase_status = extract_cell(page, "申购状态")
    result.redeem_status = extract_cell(page, "赎回状态")
    result.invest_status = extract_cell(page, "定投状态")
    result.daily_limit = extract_cell(page, "日累计申购限额")
    result.purchase_start = extract_cell(page, "申购起点")
    result.first_purchase = extract_cell(page, "首次购买")
    result.additional_purchase = extract_cell(page, "追加购买")
    result.holding_limit = extract_cell(page, "持仓上限")

    status_match = re.search(r"交易状态：\s*<span[^>]*>(.*?)</span>", page, flags=re.S)
    if status_match and not result.purchase_status:
        result.purchase_status = clean_text(status_match.group(1))

    banner_match = re.search(r"单日累计购买上限\s*([^<）]+)", page)
    if banner_match:
        result.banner_limit = clean_text(banner_match.group(1))

    result.daily_limit_yuan = parse_money_yuan(result.daily_limit or result.banner_limit)

    if not result.name:
        try:
            js_page = fetch_text(PINGZHONG_URL.format(code=code))
            result.name = extract_pingzhong_name(js_page) or alias
        except Exception:
            result.name = alias

    return result


def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    return value


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise MonitorError(f"配置文件不存在：{path}")
    with path.open("r", encoding="utf-8") as file:
        config = expand_env(json.load(file))
    notify = config.setdefault("notify", {})
    force_notify = os.getenv("FUND_NOTIFY_ENABLED", "").strip().lower()
    if force_notify in {"1", "true", "yes", "on"}:
        notify["enabled"] = True
    channel = os.getenv("FUND_NOTIFY_CHANNEL", "").strip()
    if channel:
        notify["channel"] = channel
    return config


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "funds": {}}
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        return {"version": 1, "funds": {}}


def save_state(path: Path, results: list[FundResult], now: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": now,
        "funds": {result.code: result.state_payload() for result in results},
    }
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def describe_changes(previous: dict[str, Any] | None, result: FundResult) -> list[str]:
    if previous is None:
        if result.error:
            return [f"错误状态: 空 -> {result.error}"]
        return ["首次记录"]

    labels = {
        "purchase_status": "申购状态",
        "daily_limit": "日累计限额",
        "banner_limit": "购买上限",
        "holding_limit": "持仓上限",
        "error": "错误状态",
    }
    if result.error:
        labels = {"error": "错误状态"}
    changes: list[str] = []
    current = result.state_payload()
    for field_name, label in labels.items():
        old_value = previous.get(field_name) or ""
        new_value = current.get(field_name) or ""
        if old_value != new_value:
            changes.append(f"{label}: {old_value or '空'} -> {new_value or '空'}")
    return changes


def describe_limit_change(previous: dict[str, Any] | None, result: FundResult) -> str:
    if previous is None or result.error:
        return ""
    old_limit = previous.get("daily_limit") or previous.get("banner_limit") or ""
    new_limit = result.daily_limit or result.banner_limit or ""
    if not old_limit or old_limit == new_limit:
        return ""
    return f"{compact_limit(old_limit)} -> {compact_limit(new_limit)}"


def configured_funds(config: dict[str, Any]) -> list[dict[str, str]]:
    funds: list[dict[str, str]] = []
    catalog_cache: list[dict[str, str]] | None = None
    for group in config.get("fund_groups", []):
        if group.get("enabled", True) is False:
            continue
        group_name = str(group.get("name", "未分组"))
        group_type = str(group.get("type", "other"))

        raw_funds = group.get("funds", [])
        disabled_codes = {
            str(fund.get("code", "")).strip()
            for fund in raw_funds
            if isinstance(fund, dict) and fund.get("enabled", True) is False
        }
        group_entries: list[dict[str, str]] = []

        for fund in raw_funds:
            if isinstance(fund, str):
                code, alias, enabled = fund, "", True
            else:
                code = str(fund.get("code", "")).strip()
                alias = str(fund.get("name") or fund.get("alias") or "").strip()
                enabled = fund.get("enabled", True)
            if not enabled:
                continue
            if not re.fullmatch(r"\d{6}", code):
                raise MonitorError(f"基金代码格式不正确：{code}")
            group_entries.append({"code": code, "alias": alias})

        if (group.get("discover") or {}).get("enabled", False):
            if catalog_cache is None:
                catalog_cache = fetch_fund_catalog()
            group_entries.extend(discover_funds(group, catalog_cache))

        seen_codes: set[str] = set()
        for entry in group_entries:
            code = entry["code"]
            if code in disabled_codes or code in seen_codes:
                continue
            seen_codes.add(code)
            funds.append(
                {
                    "code": code,
                    "alias": entry["alias"],
                    "group_name": group_name,
                    "group_type": group_type,
                }
            )
    return funds


def group_order(config: dict[str, Any]) -> list[str]:
    return [str(group.get("name", "未分组")) for group in config.get("fund_groups", [])]


def compact_limit(text: str) -> str:
    value = clean_text(text)
    if not value:
        return "未取到"
    if "无限" in value or "不限" in value:
        return "无限额"
    amount = parse_money_yuan(value)
    if amount is None:
        return value
    decimal = Decimal(str(amount))
    if decimal == decimal.to_integral_value():
        return f"{int(decimal)}元"
    return f"{decimal.normalize()}元"


def compact_fund_name(name: str) -> str:
    value = clean_text(name)
    replacements = [
        ("纳斯达克100", "纳指100"),
        ("纳斯达克", "纳指"),
        ("ETF发起式联接", "ETF联接"),
        ("发起式联接", "联接"),
        ("发起式", ""),
        ("股票发起式", "股票"),
        ("人民币", ""),
        ("美元现汇", "美元"),
        ("美元现钞", "美元"),
    ]
    for old, new in replacements:
        value = value.replace(old, new)
    value = re.sub(r"[（(]QDII(?:-LOF)?[）)]", "", value)
    value = re.sub(r"[（(]人民币[）)]", "", value)
    value = re.sub(r"[（(]\s*[）)]", "", value)
    value = re.sub(r"\s+", "", value)
    return value or name


def status_rank(status: str) -> int:
    if "限" in status:
        return 0
    if "暂停" in status:
        return 1
    if "开放" in status:
        return 2
    return 3


def limit_rank(limit: str) -> float:
    amount = parse_money_yuan(limit)
    if amount is None:
        return float("inf")
    return amount


def status_marker(status: str) -> str:
    if "暂停" in status:
        return "【暂停】"
    if "限" in status:
        return "【限额】"
    if "开放" in status:
        return "【开放】"
    return "【未知】"


def md_text(text: Any) -> str:
    value = str(text or "")
    return value.replace("\\", "\\\\").replace("|", "\\|").strip()


def render_mobile_group(group_name: str, group_results: list[FundResult]) -> list[str]:
    lines = [f"## {md_text(group_name)} · {len(group_results)}只"]
    errors = [result for result in group_results if result.error]
    ok_results = [result for result in group_results if not result.error]

    buckets: dict[tuple[str, str], list[FundResult]] = {}
    for result in ok_results:
        status = result.purchase_status or "未知状态"
        limit = compact_limit(result.daily_limit or result.banner_limit)
        buckets.setdefault((status, limit), []).append(result)

    sorted_keys = sorted(
        buckets,
        key=lambda item: (status_rank(item[0]), limit_rank(item[1]), item[0], item[1]),
    )
    for status, limit in sorted_keys:
        bucket = sorted(buckets[(status, limit)], key=lambda item: item.code)
        lines.append("")
        lines.append(f"### {status_marker(status)} {md_text(status)} / {md_text(limit)} · {len(bucket)}只")
        for result in bucket:
            name = compact_fund_name(result.name or result.configured_name or "未取到名称")
            change = ""
            if result.limit_change:
                change += f"  \n  限额变化：{md_text(result.limit_change)}"
            if result.changed:
                other_changes = [
                    item for item in result.changed if not item.startswith("日累计限额:")
                ]
                if other_changes:
                    change += "  \n  其他变化：" + md_text("；".join(other_changes))
            lines.append(f"- **{result.code}** {md_text(name)}{change}")

    if errors:
        lines.append("")
        lines.append(f"### 【失败】获取失败 · {len(errors)}只")
        for result in sorted(errors, key=lambda item: item.code):
            name = compact_fund_name(result.name or result.configured_name or "未取到名称")
            lines.append(f"- **{result.code}** {md_text(name)}：{md_text(result.error)}")

    return lines


def render_limit_change_summary(results: list[FundResult]) -> list[str]:
    changed = [result for result in results if result.limit_change]
    if not changed:
        return ["> 限额变化：无"]

    lines = [f"> 限额变化：{len(changed)}只", "", "## 限额变化明细"]
    for result in sorted(changed, key=lambda item: (item.group_name, item.code)):
        name = compact_fund_name(result.name or result.configured_name or "未取到名称")
        lines.append(f"- **{result.code}** {md_text(name)}：{md_text(result.limit_change)}")
    return lines


def render_summary(
    results: list[FundResult],
    config: dict[str, Any],
    now: datetime,
    only_changed: bool = False,
) -> str:
    source_name = config.get("source_name", "天天基金 F10 购买信息")
    meta = f"{now.strftime('%Y-%m-%d %H:%M')}｜{source_name}｜{len(results)}只"
    lines = [
        "# 基金申购限额监控",
        f"> {md_text(meta)}",
    ]
    lines.extend(render_limit_change_summary(results))
    lines.extend(["", "---"])
    by_group: dict[str, list[FundResult]] = {}
    for result in results:
        by_group.setdefault(result.group_name, []).append(result)

    ordered_groups = group_order(config)
    ordered_groups += [name for name in by_group if name not in ordered_groups]

    for group_name in ordered_groups:
        group_results = by_group.get(group_name, [])
        if only_changed:
            group_results = [result for result in group_results if result.changed or result.error]
        if not group_results:
            continue

        lines.append("")
        lines.extend(render_mobile_group(group_name, group_results))

    if len(lines) <= 6:
        lines.append("")
        lines.append("没有需要展示的基金变化。")
    return "\n".join(lines)


def result_status_kind(result: FundResult) -> str:
    if result.error:
        return "error"
    status = result.purchase_status or ""
    if "暂停" in status:
        return "paused"
    if "限" in status:
        return "limited"
    if "开放" in status:
        return "open"
    return "unknown"


def build_site_payload(
    results: list[FundResult],
    config: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    by_group: dict[str, list[FundResult]] = {}
    for result in results:
        by_group.setdefault(result.group_name, []).append(result)

    ordered_groups = group_order(config)
    ordered_groups += [name for name in by_group if name not in ordered_groups]

    group_payloads: list[dict[str, Any]] = []
    for group_name in ordered_groups:
        group_results = sorted(by_group.get(group_name, []), key=lambda item: item.code)
        if not group_results:
            continue
        first = group_results[0]
        group_payloads.append(
            {
                "name": group_name,
                "type": first.group_type,
                "count": len(group_results),
                "changed_count": sum(1 for item in group_results if item.changed),
                "limit_changed_count": sum(1 for item in group_results if item.limit_change),
                "error_count": sum(1 for item in group_results if item.error),
            }
        )

    fund_payloads = []
    for result in sorted(results, key=lambda item: (item.group_name, item.code)):
        display_name = result.name or result.configured_name or "未取到名称"
        raw_limit = result.daily_limit or result.banner_limit
        fund_payloads.append(
            {
                "code": result.code,
                "group_name": result.group_name,
                "group_type": result.group_type,
                "name": display_name,
                "short_name": compact_fund_name(display_name),
                "configured_name": result.configured_name,
                "purchase_status": result.purchase_status or "未知状态",
                "redeem_status": result.redeem_status,
                "invest_status": result.invest_status,
                "status_kind": result_status_kind(result),
                "daily_limit": result.daily_limit,
                "banner_limit": result.banner_limit,
                "display_limit": compact_limit(raw_limit),
                "daily_limit_yuan": result.daily_limit_yuan,
                "purchase_start": result.purchase_start,
                "first_purchase": result.first_purchase,
                "additional_purchase": result.additional_purchase,
                "holding_limit": result.holding_limit,
                "display_holding_limit": compact_limit(result.holding_limit),
                "source_url": result.source_url,
                "fetched_at": result.fetched_at,
                "changed": result.changed,
                "limit_change": result.limit_change,
                "error": result.error,
            }
        )

    changed_funds = [
        item for item in fund_payloads if item["limit_change"] or item["changed"] or item["error"]
    ]
    return {
        "version": 1,
        "title": "纳斯达克基金限额看板",
        "source_name": config.get("source_name", "天天基金 F10 购买信息"),
        "updated_at": now.isoformat(timespec="seconds"),
        "updated_at_display": now.strftime("%Y-%m-%d %H:%M"),
        "timezone": str(config.get("timezone", "Asia/Shanghai")),
        "summary": {
            "total": len(results),
            "groups": len(group_payloads),
            "changed": len(changed_funds),
            "limit_changed": sum(1 for item in fund_payloads if item["limit_change"]),
            "errors": sum(1 for item in fund_payloads if item["error"]),
            "limited": sum(1 for item in fund_payloads if item["status_kind"] == "limited"),
            "paused": sum(1 for item in fund_payloads if item["status_kind"] == "paused"),
            "open": sum(1 for item in fund_payloads if item["status_kind"] == "open"),
        },
        "groups": group_payloads,
        "changes": changed_funds,
        "funds": fund_payloads,
        "disclaimer": "数据来自天天基金公开页面，交易前请以实际下单平台为准。本页面不构成投资建议。",
    }


def write_site_payload(
    path: Path,
    results: list[FundResult],
    config: dict[str, Any],
    now: datetime,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_site_payload(results, config, now)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def placeholder_secret(value: str) -> bool:
    stripped = value.strip()
    return not stripped or stripped.startswith("${") or stripped.endswith("_HERE")


def send_serverchan(notify: dict[str, Any], title: str, content: str) -> None:
    sendkey = str(notify.get("serverchan_sendkey", "")).strip()
    if placeholder_secret(sendkey):
        raise MonitorError("缺少 Server酱 sendkey，请设置 SERVERCHAN_SENDKEY 或填写配置")
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = urllib.parse.urlencode({"title": title, "desp": content}).encode("utf-8")
    post_form(url, data)


def send_pushplus(notify: dict[str, Any], title: str, content: str) -> None:
    token = str(notify.get("pushplus_token", "")).strip()
    if placeholder_secret(token):
        raise MonitorError("缺少 PushPlus token，请设置 PUSHPLUS_TOKEN 或填写配置")
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "markdown",
    }
    post_json("https://www.pushplus.plus/send", payload)


def send_wecom_robot(notify: dict[str, Any], title: str, content: str) -> None:
    webhook = str(notify.get("wecom_robot_webhook", "")).strip()
    if placeholder_secret(webhook):
        raise MonitorError("缺少企业微信机器人 webhook，请设置 WECOM_ROBOT_WEBHOOK 或填写配置")
    payload = {"msgtype": "markdown", "markdown": {"content": f"**{title}**\n\n{content}"}}
    post_json(webhook, payload)


def post_form(url: str, data: bytes) -> None:
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        body = response.read().decode("utf-8", errors="replace")
        if response.status >= 400:
            raise MonitorError(f"推送失败 HTTP {response.status}: {body}")


def post_json(url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        body = response.read().decode("utf-8", errors="replace")
        if response.status >= 400:
            raise MonitorError(f"推送失败 HTTP {response.status}: {body}")


def send_notification(config: dict[str, Any], title: str, content: str) -> None:
    notify = config.get("notify", {})
    channel = str(notify.get("channel", "serverchan")).lower()
    if channel in {"serverchan", "server_chan", "sct"}:
        send_serverchan(notify, title, content)
    elif channel in {"pushplus", "push_plus"}:
        send_pushplus(notify, title, content)
    elif channel in {"wecom", "wechat_work", "qywx", "enterprise_wechat"}:
        send_wecom_robot(notify, title, content)
    else:
        raise MonitorError(f"不支持的推送渠道：{channel}")


def should_send(results: list[FundResult], config: dict[str, Any]) -> bool:
    notify = config.get("notify", {})
    if not notify.get("enabled", False):
        return False
    has_change = any(result.changed for result in results)
    has_error = any(result.error for result in results)
    if notify.get("only_on_change", False):
        return has_change or (has_error and notify.get("send_on_error", True))
    return True


def monitor_once(config: dict[str, Any], state: dict[str, Any], now: datetime) -> list[FundResult]:
    funds = configured_funds(config)
    if not funds:
        raise MonitorError("配置里没有启用的基金")

    state_funds = state.get("funds", {})
    delay = float(config.get("request_interval_seconds", 0.3))
    fetched_at = now.isoformat(timespec="seconds")
    results: list[FundResult] = []
    for index, fund in enumerate(funds):
        if index and delay > 0:
            time.sleep(delay)
        try:
            result = parse_limit_page(
                fund["code"],
                fund["group_name"],
                fund["group_type"],
                fund["alias"],
                fetched_at,
            )
        except Exception as exc:
            result = FundResult(
                code=fund["code"],
                group_name=fund["group_name"],
                group_type=fund["group_type"],
                configured_name=fund["alias"],
                name=fund["alias"],
                fetched_at=fetched_at,
                source_url=F10_URL.format(code=fund["code"]),
                error=str(exc),
            )
        previous = state_funds.get(result.code)
        result.changed = describe_changes(previous, result)
        result.limit_change = describe_limit_change(previous, result)
        results.append(result)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="监控国内基金申购限额并推送到微信。")
    parser.add_argument(
        "--config",
        default="config.json",
        help="配置文件路径，默认 config.json。",
    )
    parser.add_argument(
        "--state",
        default=".fund_limit_state.json",
        help="状态文件路径，默认 .fund_limit_state.json。",
    )
    parser.add_argument("--no-push", action="store_true", help="只打印结果，不发送微信推送。")
    parser.add_argument("--dry-run", action="store_true", help="同 --no-push。")
    parser.add_argument("--only-changed", action="store_true", help="输出内容只包含变化项。")
    parser.add_argument("--print-json", action="store_true", help="以 JSON 输出本次抓取结果。")
    parser.add_argument("--site-output", help="把本次抓取结果导出为公开网页使用的 JSON。")
    parser.add_argument("--test-push", action="store_true", help="发送一条微信推送测试消息。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.exists() and config_path.name == "config.json":
        config_path = Path("config.example.json")

    try:
        config = load_config(config_path)
        timezone = ZoneInfo(str(config.get("timezone", "Asia/Shanghai")))
        now = datetime.now(timezone)

        if args.test_push:
            title = "基金限额监控测试"
            content = f"这是一条测试推送，发送时间 {now.strftime('%Y-%m-%d %H:%M:%S')}。"
            send_notification(config, title, content)
            print("测试推送已发送。")
            return 0

        state_path = Path(args.state)
        state = load_state(state_path)
        results = monitor_once(config, state, now)

        if args.site_output:
            write_site_payload(Path(args.site_output), results, config, now)

        if args.print_json:
            print(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2))
        else:
            print(render_summary(results, config, now, only_changed=args.only_changed))

        push_disabled = args.no_push or args.dry_run
        push_ok = True
        if not push_disabled and should_send(results, config):
            title = f"基金限额监控 {now.strftime('%Y-%m-%d')}"
            content = render_summary(results, config, now, only_changed=args.only_changed)
            try:
                send_notification(config, title, content)
                print("\n微信推送已发送。")
            except (MonitorError, urllib.error.URLError, TimeoutError) as exc:
                push_ok = False
                print(f"\n微信推送失败：{exc}", file=sys.stderr)

        if push_ok or push_disabled or not config.get("notify", {}).get("enabled", False):
            save_state(state_path, results, now.isoformat(timespec="seconds"))

        return 0 if push_ok else 2
    except (MonitorError, OSError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
