"""
命令行版 —— 不开窗口也能用，适合放进脚本 / 定时任务。

用法（在 iqiyi_spider 文件夹里打开终端）：
    python cli.py 狂飙
    python cli.py 狂飙 --pages 5
    python cli.py 甄嬛传 --type 长视频优先 --pages 2 --format csv

命令行版的代码比界面版短得多，建议你先读这个，再读 gui.py。
"""

import argparse
import sys
import time
import unicodedata

from spider import parser, storage
from spider.client import FetchError
from spider.crawler import Crawler


def build_arg_parser():
    arg_parser = argparse.ArgumentParser(
        description="爱奇艺视频信息爬虫（课堂练习版）：按关键词抓取公开搜索结果并保存。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""例子：
  python cli.py 狂飙
  python cli.py 狂飙 --pages 5 --type 综合
  python cli.py 流浪地球 --format json --outdir data
""",
    )
    arg_parser.add_argument("keyword", nargs="?", help="搜索关键词，比如 狂飙")
    arg_parser.add_argument("-p", "--pages", type=int, default=3, help="抓几页（默认 3，一页约 20 条）")
    arg_parser.add_argument("-t", "--type", default="综合", choices=list(parser.MODES),
                            help="搜索分类（默认 综合）")
    arg_parser.add_argument("-f", "--format", default="both", choices=["csv", "json", "both"],
                            help="保存格式（默认 both）")
    arg_parser.add_argument("-o", "--outdir", default=None, help="保存到哪个文件夹（默认 data）")
    arg_parser.add_argument("--delay", type=float, default=0.8,
                            help="每次请求之间歇几秒（默认 0.8，别调太小）")
    arg_parser.add_argument("--quiet", action="store_true", help="不打印表格，只保存文件")
    return arg_parser


def display_width(text):
    """中文占 2 个字符宽，英文占 1 个，算宽度得按这个来，否则表格对不齐。"""
    return sum(2 if unicodedata.east_asian_width(char) in ("W", "F") else 1 for char in text)


def fit(text, width):
    """把文字裁到指定显示宽度，右边补空格。"""
    if display_width(text) > width:
        kept, used = "", 0
        for char in text:
            char_width = 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
            if used + char_width > width - 1:
                break
            kept += char
            used += char_width
        text = kept + "…"
    return text + " " * max(0, width - display_width(text))


def print_table(records, limit=30):
    columns = [("序号", 5), ("标题", 38), ("频道", 9), ("年份", 6), ("评分", 5), ("时长", 9), ("标签", 20)]
    gap = "  "

    def render(cells):
        return gap.join(fit(value, width) for value, width in cells)

    print(render(columns))
    print("-" * (sum(width for _, width in columns) + len(gap) * (len(columns) - 1)))
    for index, record in enumerate(records[:limit], start=1):
        row = [
            (str(index), 5),
            (record["title"], 38),
            (record["channel"], 9),
            (record["year"], 6),
            (record["rating"], 5),
            (record["duration"], 9),
            (record["tags"], 20),
        ]
        print(render(row))
    if len(records) > limit:
        print(f"… 还有 {len(records) - limit} 条，见保存的文件")


def main(argv=None):
    # Windows 终端默认是 GBK，遇到 emoji 会崩，这里统一按 UTF-8 输出
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    args = build_arg_parser().parse_args(argv)
    keyword = (args.keyword or "").strip()
    while not keyword:
        try:
            keyword = input("请输入要搜索的视频名（比如 狂飙）：").strip()
        except (EOFError, KeyboardInterrupt):
            # Ctrl+D / Ctrl+C：安静地退出，别甩用户一脸堆栈
            print("\n已取消")
            return 130
    if args.pages < 1:
        print("页数至少是 1")
        return 1

    mode = parser.MODES[args.type]
    started = time.time()
    crawler = Crawler()
    crawler.client.delay = max(0.2, args.delay)

    try:
        report = crawler.crawl(
            keyword, pages=args.pages, mode=mode,
            on_log=lambda message: print(f"  {message}"),
        )
    except FetchError as error:
        print(f"\n✗ 抓取失败：{error}")
        print("  可能原因：没联网 / 接口地址变了 / 请求被限流。")
        return 1
    except KeyboardInterrupt:
        print("\n已取消")
        return 130

    elapsed = time.time() - started
    if not report.records:
        if report.stopped:
            print("\n已停止，还没抓到数据。")
        elif report.total == 0:
            print("\n没有搜到结果，换个关键词再试试。")
        else:
            print("\n没抓到数据。可能接口变了，打开爱奇艺搜索页按 F12 看看现在调的是哪个地址。")
        return 1

    print()
    if not args.quiet:
        print_table(report.records)

    # 保存也可能失败：目录不存在、没权限、同名文件正被 Excel 打开着……
    # 这时候数据其实已经抓到了，所以要给一句人话，而不是甩 FileExistsError 堆栈。
    saved_files = []
    try:
        csv_path = storage.make_filename(keyword, "csv", args.outdir)
        if args.format in ("csv", "both"):
            saved_files.append(storage.save_csv(report.records, csv_path))
        if args.format in ("json", "both"):
            saved_files.append(storage.save_json(report.records, csv_path.with_suffix(".json"), keyword))
    except OSError as error:
        print(f"\n✗ 保存失败：{error}")
        print("  换个有写入权限的目录（-o），或者先关掉正在占用该文件的 Excel。")
        return 1

    print(f"\n✓ 共 {len(report.records)} 条（接口说有 {report.total} 条），用时 {elapsed:.1f} 秒，请求 {crawler.client.request_count} 次")
    for path in saved_files:
        print(f"  已保存：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
