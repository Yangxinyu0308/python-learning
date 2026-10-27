"""离线测试：保存模块（CSV / JSON 能不能正确写出来、再读回来）。"""
import csv
import json
import unittest
from pathlib import Path

from spider import storage
from spider.parser import FIELDS

# 测试写文件用的临时文件夹（tests/_tmp），跑完就把里面的文件删掉
TMP_DIR = Path(__file__).parent / "_tmp"

SAMPLE = [{
    "title": "流浪地球, 加长版",          # 故意带逗号，测试 CSV 的引号处理
    "channel": "电影",
    "source": "电影类长视频",
    "year": "2019",
    "region": "内地",
    "rating": "8.8",
    "hot": "1200",
    "duration": "02:05:00",
    "actors": "吴京、屈楚萧",
    "tags": "科幻、灾难",
    "summary": "太阳即将毁灭，人类开启流浪地球计划。",
    "vip": "",
    "url": "https://www.iqiyi.com/v_test.html",
    "video_id": "123",
}]


class StorageTest(unittest.TestCase):
    def setUp(self):
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        self.prefix = self._testMethodName          # 每个测试用自己的文件名，互不干扰

    def tearDown(self):
        # 只删文件，不删文件夹（有些系统会锁住目录，删不掉也不该让测试报错）
        for path in TMP_DIR.glob(f"{self.prefix}*"):
            if path.is_file():
                path.unlink(missing_ok=True)

    def test_save_csv(self):
        path = storage.save_csv(SAMPLE, TMP_DIR / f"{self.prefix}_out.csv")
        self.assertTrue(path.exists())
        with open(path, encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["序号"], "1")
        self.assertEqual(rows[0]["标题"], "流浪地球, 加长版")
        for _key, label in FIELDS:
            self.assertIn(label, rows[0])

    def test_save_json(self):
        path = storage.save_json(SAMPLE, TMP_DIR / f"{self.prefix}_out.json", keyword="流浪地球")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["keyword"], "流浪地球")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["records"][0]["title"], "流浪地球, 加长版")
        self.assertIn("crawled_at", payload)

    def test_make_filename_strips_illegal_chars(self):
        path = storage.make_filename('狂飙/第:一季*?', "csv", TMP_DIR)
        self.assertEqual(path.parent, TMP_DIR)
        self.assertTrue(path.name.endswith(".csv"))
        for char in '\\/:*?"<>|':
            self.assertNotIn(char, path.name)
        self.assertIn("狂飙", path.name)
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
