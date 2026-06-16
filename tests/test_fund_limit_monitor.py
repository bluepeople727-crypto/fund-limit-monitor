import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from fund_limit_monitor import (
    FundResult,
    compact_fund_name,
    compact_limit,
    build_site_payload,
    describe_changes,
    describe_limit_change,
    discover_funds,
    extract_cell,
    parse_money_yuan,
    render_summary,
)


SAMPLE_HTML = """
<html><body>
交易状态：<span>限大额 </span><span>（<span>单日累计购买上限10元</span>）</span>
<table>
  <tr>
    <td class="th w110">申购状态</td><td class="w135">限大额</td>
    <td class="th w110">赎回状态</td><td class="w135">开放赎回</td>
    <td class="th w110">定投状态</td><td class="w135">支持</td>
  </tr>
  <tr>
    <td class="th w110">申购起点</td><td class="w135">10.00元</td>
    <td class="th w110">定投起点</td><td class="w135">10.00元</td>
    <td class="th w110">日累计申购限额</td><td class="w135">100.00元</td>
  </tr>
</table>
</body></html>
"""


class ParserTest(unittest.TestCase):
    def test_extract_cell(self):
        self.assertEqual(extract_cell(SAMPLE_HTML, "申购状态"), "限大额")
        self.assertEqual(extract_cell(SAMPLE_HTML, "赎回状态"), "开放赎回")
        self.assertEqual(extract_cell(SAMPLE_HTML, "日累计申购限额"), "100.00元")

    def test_parse_money_yuan(self):
        self.assertEqual(parse_money_yuan("10.00元"), 10.0)
        self.assertEqual(parse_money_yuan("1.5万元"), 15000.0)
        self.assertIsNone(parse_money_yuan("无限额"))
        self.assertIsNone(parse_money_yuan("---份"))

    def test_compact_display_text(self):
        self.assertEqual(compact_limit("10.00元"), "10元")
        self.assertEqual(compact_limit("无限额"), "无限额")
        self.assertEqual(
            compact_fund_name("华安纳斯达克100ETF联接(QDII)A"),
            "华安纳指100ETF联接A",
        )
        self.assertEqual(
            compact_fund_name("华夏全球科技先锋混合(QDII)A(人民币)"),
            "华夏全球科技先锋混合A",
        )

    def test_describe_changes(self):
        result = FundResult(
            code="040046",
            group_name="纳斯达克100A",
            group_type="nasdaq100_a",
            purchase_status="限大额",
            daily_limit="10.00元",
        )
        previous = {"purchase_status": "开放申购", "daily_limit": "100.00元"}
        changes = describe_changes(previous, result)
        self.assertIn("申购状态: 开放申购 -> 限大额", changes)
        self.assertIn("日累计限额: 100.00元 -> 10.00元", changes)

    def test_describe_limit_change(self):
        result = FundResult(
            code="040046",
            group_name="纳斯达克100A",
            group_type="nasdaq100_a",
            daily_limit="10.00元",
        )
        previous = {"daily_limit": "100.00元"}
        self.assertEqual(describe_limit_change(previous, result), "100元 -> 10元")
        self.assertEqual(describe_limit_change(None, result), "")

    def test_discover_nasdaq100_a_rmb(self):
        group = {
            "discover": {
                "enabled": True,
                "keywords": ["纳斯达克100"],
                "fund_type_contains": "指数型-海外股票",
                "include_name_regex": "A|^国泰纳斯达克100指数$",
                "exclude_name_regex": "美元|现汇|现钞",
                "exclude_codes": ["159513"],
            }
        }
        catalog = [
            {"code": "015299", "name": "华夏纳斯达克100ETF发起式联接(QDII)A", "fund_type": "指数型-海外股票"},
            {"code": "015300", "name": "华夏纳斯达克100ETF发起式联接(QDII)C", "fund_type": "指数型-海外股票"},
            {"code": "015518", "name": "华夏纳斯达克100ETF发起式联接(QDII)A美元现汇", "fund_type": "指数型-海外股票"},
            {"code": "160213", "name": "国泰纳斯达克100指数", "fund_type": "指数型-海外股票"},
            {"code": "159513", "name": "纳斯达克100ETF大成", "fund_type": "指数型-海外股票"},
        ]
        codes = [fund["code"] for fund in discover_funds(group, catalog)]
        self.assertEqual(codes, ["015299", "160213"])

    def test_render_summary_uses_mobile_list(self):
        result = FundResult(
            code="040046",
            group_name="纳斯达克100A",
            group_type="nasdaq100_a",
            name="华安纳斯达克100ETF联接(QDII)A",
            purchase_status="限大额",
            daily_limit="10.00元",
            holding_limit="无限额",
            limit_change="100元 -> 10元",
        )
        text = render_summary(
            [result],
            {"source_name": "测试源", "fund_groups": [{"name": "纳斯达克100A"}]},
            datetime(2026, 6, 16, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        self.assertIn("## 纳斯达克100A · 1只", text)
        self.assertIn("> 限额变化：1只", text)
        self.assertIn("## 限额变化明细", text)
        self.assertIn("- **040046** 华安纳指100ETF联接A：100元 -> 10元", text)
        self.assertIn("### 【限额】 限大额 / 10元 · 1只", text)
        self.assertIn("- **040046** 华安纳指100ETF联接A", text)
        self.assertIn("限额变化：100元 -> 10元", text)
        self.assertNotIn("<font", text)
        self.assertNotIn("| 代码 |", text)

    def test_build_site_payload_groups_and_changes(self):
        result = FundResult(
            code="040046",
            group_name="纳斯达克100A",
            group_type="nasdaq100_a",
            name="华安纳斯达克100ETF联接(QDII)A",
            purchase_status="限大额",
            daily_limit="10.00元",
            holding_limit="无限额",
            limit_change="100元 -> 10元",
            changed=["日累计限额: 100.00元 -> 10.00元"],
            source_url="https://fundf10.eastmoney.com/jjfl_040046.html",
        )
        payload = build_site_payload(
            [result],
            {"source_name": "测试源", "fund_groups": [{"name": "纳斯达克100A"}]},
            datetime(2026, 6, 16, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["limit_changed"], 1)
        self.assertEqual(payload["groups"][0]["name"], "纳斯达克100A")
        self.assertEqual(payload["funds"][0]["status_kind"], "limited")
        self.assertEqual(payload["funds"][0]["display_limit"], "10元")
        self.assertEqual(payload["changes"][0]["code"], "040046")


if __name__ == "__main__":
    unittest.main()
