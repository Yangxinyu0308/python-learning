"""离线测试：解析器。用 tests/fixtures 里保存的真实接口返回，不联网。"""
import json
import unittest
from pathlib import Path

from spider import parser

FIXTURE = Path(__file__).parent / "fixtures" / "search_page1.json"


class ParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.records = parser.parse_search_payload(cls.payload)

    def test_build_url_encodes_chinese(self):
        url = parser.build_search_url("狂飙", page=2, mode=5)
        self.assertIn("key=%E7%8B%82%E9%A3%99", url)   # "狂飙" 的 URL 编码
        self.assertIn("pageNum=2", url)
        self.assertIn("mode=5", url)
        self.assertTrue(url.startswith("https://mesh.if.iqiyi.com/"))

    def test_items_without_title_are_dropped(self):
        # fixture 里塞了 4 条，其中 1 条没有标题，应该只剩 3 条
        self.assertEqual(len(self.records), 3)

    def test_long_video_fields(self):
        record = self.records[0]
        self.assertEqual(record["title"], "狂飙")
        self.assertEqual(record["channel"], "电视剧")
        self.assertEqual(record["source"], "剧集类型展示")
        self.assertEqual(record["year"], "2023")
        self.assertEqual(record["region"], "内地")
        self.assertEqual(record["rating"], "9.5")
        self.assertEqual(record["hot"], "3147")
        self.assertEqual(record["duration"], "39集全")
        self.assertEqual(record["actors"], "张译、张颂文、李一桐、张志坚")
        self.assertEqual(record["vip"], "VIP")
        self.assertEqual(record["url"], "https://www.iqiyi.com/v_xkt6z3z798.html")
        self.assertEqual(record["video_id"], "5328486914190101")
        self.assertIn("扫黑除恶", record["summary"])

    def test_short_video_fields(self):
        record = self.records[1]
        self.assertIn("强哥逗大嫂", record["title"])
        self.assertEqual(record["channel"], "片花")
        self.assertEqual(record["year"], "2026")        # 没有 year，就从发布时间里截
        self.assertEqual(record["duration"], "00:37")
        self.assertEqual(record["rating"], "")
        self.assertEqual(record["vip"], "")             # 字符串 "False" 不能被当成真

    def test_tags_have_no_duplicates(self):
        tags = self.records[0]["tags"].split("、")
        self.assertEqual(len(tags), len(set(tags)))
        self.assertLessEqual(len(tags), 8)

    def test_duration_falls_back_to_milliseconds(self):
        record = parser.normalize_item({"albumInfo": {"title": "测试", "duration": 3723000}})
        self.assertEqual(record["duration"], "1:02:03")

    def test_movie_duration_is_not_rating(self):
        # 电影的 subscriptContent 装的是评分（9.0），真正的时长在 duration 毫秒里。
        # 这是真实数据里踩出来的坑，别改回去。
        record = parser.normalize_item({"albumInfo": {
            "title": "流浪地球2", "subscriptContent": "9.0", "duration": 10391000,
        }})
        self.assertEqual(record["duration"], "2:53:11")

    def test_rating_label_without_duration_is_dropped(self):
        record = parser.normalize_item({"albumInfo": {"title": "某电影", "subscriptContent": "8.8"}})
        self.assertEqual(record["duration"], "")

    def test_total_results(self):
        self.assertEqual(parser.total_results(self.payload), 19831)
        self.assertEqual(parser.total_results({}), 0)

    def test_describe_error(self):
        self.assertIsNone(parser.describe_error({"code": "0"}))
        message = parser.describe_error({"code": "-1", "msg": "param[key] required"})
        self.assertIn("param[key] required", message)


if __name__ == "__main__":
    unittest.main()
