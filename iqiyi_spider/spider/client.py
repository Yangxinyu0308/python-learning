"""
网络请求模块 —— 只干一件事：把网址变成网页内容。

只用 Python 自带的 urllib，所以你不需要 pip install 任何东西，换台电脑也能直接跑。
（想换成 requests 库？去 README 的「作业 1」看看怎么写。）
"""

import gzip
import http.client
import json
import time
import urllib.error
import urllib.request
import zlib

# 伪装成浏览器。很多网站看到 User-Agent 里写着 "python-urllib" 会直接拒绝你。
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://so.iqiyi.com/",
}


class FetchError(Exception):
    """请求失败（重试次数用完了）。界面里会把这句话原样显示出来。"""


class HttpClient:
    """
    一个会"礼貌请求"的小客户端：
      - 自动重试（网络抖动很常见，试第二次往往就好了）
      - 自动限速（两次请求之间至少隔 delay 秒，别把人家服务器打崩）
      - 自动处理 gzip 压缩和文件开头的 BOM
    """

    def __init__(self, timeout=15, retries=3, delay=0.8, headers=None):
        self.timeout = timeout
        self.retries = retries
        self.delay = delay
        self.headers = {**DEFAULT_HEADERS, **(headers or {})}
        self._last_request_at = 0.0
        self.request_count = 0        # 一共发了几次请求，界面上会显示

    def get_text(self, url):
        """下载一个网址，返回解码后的字符串。失败会抛 FetchError。"""
        last_error = ""
        for attempt in range(1, self.retries + 1):
            self._wait_for_turn()
            try:
                request = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    if response.headers.get("Content-Encoding", "").lower() == "gzip":
                        raw = gzip.decompress(raw)
                    self.request_count += 1
                    # utf-8-sig：顺便把文件开头那个看不见的 BOM 字符去掉
                    return raw.decode("utf-8-sig", "replace")
            except urllib.error.HTTPError as error:
                last_error = f"HTTP {error.code} {error.reason}"
                if error.code in (403, 404, 410):
                    break                     # 这类错误再试也是一样的结果，别浪费时间
            except (urllib.error.URLError, http.client.HTTPException,
                    TimeoutError, OSError, EOFError, zlib.error) as error:
                # IncompleteRead / 坏 gzip 都不是 OSError，得单独列出来，否则会直接抛给用户
                last_error = f"网络错误：{error}"
            if attempt < self.retries:
                time.sleep(attempt * 1.0)     # 第 2 次等 1 秒，第 3 次等 2 秒
        raise FetchError(f"下载失败（试了 {self.retries} 次）：{last_error}\n{url}")

    def get_json(self, url):
        """下载一个网址，并把内容解析成 JSON（Python 的 dict / list）。"""
        text = self.get_text(url)
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise FetchError(
                f"返回的不是合法 JSON：{error}\n前 200 个字符：{text[:200]!r}"
            ) from error

    def _wait_for_turn(self):
        """限速：保证两次请求之间至少隔 self.delay 秒。"""
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_at = time.monotonic()
