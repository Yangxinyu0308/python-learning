"""
保存模块 —— 把内存里的记录写成文件（CSV 给 Excel 看，JSON 给程序看）。

小知识：
  CSV 用 utf-8-sig 编码保存，Excel 双击打开才不会变成乱码（那个 sig 就是文件头的 BOM）。
"""

import csv
import json
from datetime import datetime
from pathlib import Path

from spider.parser import FIELDS

# 项目根目录（spider 文件夹的上一层），这样不管从哪个目录启动，data 都存对地方
PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTDIR = PROJECT_DIR / "data"


def save_csv(records, path):
    """保存成 CSV。records 是 parse 出来的记录列表，path 是完整文件路径。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    headers = ["序号"] + [label for _, label in FIELDS]
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for index, record in enumerate(records, start=1):
            row = {"序号": index}
            for key, label in FIELDS:
                row[label] = record.get(key, "")
            writer.writerow(row)
    return path


def save_json(records, path, keyword=""):
    """保存成 JSON，外面再包一层说明信息（关键词、时间、条数）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "keyword": keyword,
        "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(records),
        "records": records,
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return path


def make_filename(keyword, suffix, outdir=None):
    """生成一个带时间戳的文件名：data/狂飙_20261027_140102.csv"""
    folder = Path(outdir) if outdir else DEFAULT_OUTDIR
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{_clean(keyword)}_{stamp}.{suffix}"
    return folder / name


def _clean(text):
    """去掉文件名里不能用的字符（Windows 的 \\ / : * ? " < > |），再截短一点。"""
    safe = "".join(char for char in str(text) if char not in '\\/:*?"<>|').strip()
    return (safe or "搜索结果")[:40]
