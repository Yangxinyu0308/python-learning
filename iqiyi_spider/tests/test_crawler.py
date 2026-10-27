"""离线测试：翻页和去重逻辑。用一个假的 client 顶替真实网络请求。"""
import threading
import unittest
import urllib.parse

from spider.crawler import Crawler


def make_payload(*titles):
    """捏一个长得像接口返回的假数据。"""
    return {
        "code": "0",
        "data": {
            "resultNum": 100,
            "templates": [
                {"template": 108, "s3": "短视频", "albumInfo": {
                    "title": title,
                    # 链接跟着标题走，这样"同一条视频"在第二页出现时能认出来
                    "pageUrl": f"https://www.iqiyi.com/v_{title}.html",
                }}
                for title in titles
            ],
        },
    }


class FakeClient:
    """假 client：不联网，按页码返回事先准备好的数据，并记下被请求了哪些页。"""

    def __init__(self, pages):
        self.pages = pages
        self.requested_pages = []
        self.request_count = 0

    def get_json(self, url):
        page = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["pageNum"][0])
        self.requested_pages.append(page)
        self.request_count += 1
        return self.pages.get(page, make_payload())


class CrawlerTest(unittest.TestCase):
    def test_pages_and_dedupe(self):
        client = FakeClient({
            1: make_payload("A", "B"),
            2: make_payload("B", "C"),      # B 重复，应该被去掉
        })
        logs = []
        report = Crawler(client=client).crawl("测试", pages=2, on_log=logs.append)

        self.assertEqual([record["title"] for record in report.records], ["A", "B", "C"])
        self.assertEqual(report.pages_done, 2)
        self.assertEqual(report.total, 100)
        self.assertEqual(client.requested_pages, [1, 2])
        self.assertTrue(any("累计 3 条" in line for line in logs))

    def test_stops_when_page_is_empty(self):
        client = FakeClient({1: make_payload("A")})       # 第 2 页开始是空数据
        report = Crawler(client=client).crawl("测试", pages=5)
        self.assertEqual(len(report.records), 1)
        self.assertEqual(client.requested_pages, [1, 2])  # 第 2 页发现没数据就不再往下抓

    def test_empty_first_page_is_not_blamed_on_the_api(self):
        """第一页就空，应该提示"换个关键词"，而不是"没有更多结果"。"""
        client = FakeClient({})                            # 每一页都是空数据
        logs = []
        report = Crawler(client=client).crawl("测试", pages=2, on_log=logs.append)
        self.assertEqual(report.records, [])
        self.assertTrue(any("没有搜到结果" in line for line in logs), logs)

    def test_stop_event(self):
        client = FakeClient({1: make_payload("A")})
        stop_event = threading.Event()
        stop_event.set()                                  # 一开始就被叫停
        report = Crawler(client=client).crawl("测试", pages=3, stop_event=stop_event)
        self.assertTrue(report.stopped)
        self.assertEqual(report.records, [])
        self.assertEqual(client.requested_pages, [])

    def test_empty_keyword_raises(self):
        with self.assertRaises(ValueError):
            Crawler(client=FakeClient({})).crawl("   ")


if __name__ == "__main__":
    unittest.main()
