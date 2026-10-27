"""
爬虫编排 —— 把「请求」「解析」「翻页」「去重」串起来。

界面（gui.py）和命令行（cli.py）都只调用这里的一个函数：Crawler.crawl()。
好处：写界面的同学不用懂翻页逻辑，改翻页逻辑也不用动界面。
"""

from dataclasses import dataclass, field

from spider import parser
from spider.client import FetchError, HttpClient


@dataclass
class CrawlReport:
    """一次抓取的结果汇总。"""
    keyword: str = ""
    records: list = field(default_factory=list)
    total: int = 0            # 接口说一共有多少条结果
    pages_done: int = 0       # 实际抓了几页
    stopped: bool = False     # 是不是被用户中途按了「停止」


class Crawler:
    def __init__(self, client=None):
        self.client = client or HttpClient()

    def crawl(self, keyword, pages=3, mode=0, on_log=None, on_progress=None,
              on_page=None, stop_event=None):
        """
        抓取 keyword 的前 pages 页搜索结果。

        keyword   : 搜索关键词
        pages     : 抓几页（一页 20 条左右）
        mode      : 搜索分类，见 parser.MODES（0 综合 / 5 长视频优先 / 3 短视频）
        on_log    : 回调函数，收到一行日志文字
        on_progress: 回调函数，收到 0.0~1.0 的进度
        on_page   : 回调函数 (页码, 总页数, 本页新增记录列表)
        stop_event: threading.Event，被 set 了就提前停下来

        返回 CrawlReport。
        """
        keyword = (keyword or "").strip()
        if not keyword:
            raise ValueError("关键词不能为空")

        report = CrawlReport(keyword=keyword)
        seen = set()                      # 已经抓过的，用来去重
        log = on_log or (lambda message: None)

        for page in range(1, max(1, pages) + 1):
            if stop_event is not None and stop_event.is_set():
                report.stopped = True
                log("⏹ 已停止")
                break

            url = parser.build_search_url(keyword, page, mode)
            log(f"第 {page}/{pages} 页 → {url}")

            try:
                payload = self.client.get_json(url)
            except FetchError as error:
                log(f"⚠ 第 {page} 页失败：{error}")
                if page == 1:
                    raise
                continue                  # 后面几页失败就跳过，别整个项目崩掉

            error_message = parser.describe_error(payload)
            if error_message:
                log(f"⚠ {error_message}")
                if page == 1:
                    raise FetchError(error_message)
                break

            if page == 1:
                report.total = parser.total_results(payload)
                log(f"接口说「{keyword}」一共有 {report.total} 条结果")

            page_records = parser.parse_search_payload(payload)
            if not page_records:
                # 第一页就空，通常是关键词没搜到东西，不是接口坏了
                log("没有搜到结果，换个关键词试试" if page == 1 else "没有更多结果了，提前收工")
                break

            fresh = []
            for record in page_records:
                key = record.get("url") or record.get("video_id") or record.get("title")
                if key and key not in seen:
                    seen.add(key)
                    fresh.append(record)
            report.records.extend(fresh)
            report.pages_done = page
            log(f"  本页 {len(page_records)} 条，新增 {len(fresh)} 条，累计 {len(report.records)} 条")

            if on_page:
                on_page(page, pages, fresh)
            if on_progress:
                on_progress(page / max(1, pages))

        return report
