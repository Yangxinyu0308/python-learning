"""
图形界面（tkinter）—— 双击就能用的那个"软件"。

界面卡死的经典坑：tkinter 是单线程的，如果在主线程里发网络请求，
窗口就会白屏 + "未响应"。所以这里用后台线程抓数据，再用 queue 把消息
送回主线程更新界面。这是做桌面小工具最常用的套路，值得记住。

启动：python main.py    或者在 VSCode 里按 F5
"""

import os
import queue
import threading
import traceback
import webbrowser
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from spider import parser, storage
from spider.crawler import Crawler

# ---------------------------------------------------------------- 配色（爱奇艺绿）
BG = "#f4f6f8"
CARD = "#ffffff"
ACCENT = "#00be06"
ACCENT_DARK = "#00a005"
ACCENT_LIGHT = "#e6f8e7"
TEXT = "#1f2329"
MUTED = "#8a8f99"
BORDER = "#e3e6ea"
FONT = "Microsoft YaHei UI"

HEADERS = ["序号", "标题", "频道", "年份", "评分", "时长", "标签"]
WIDTHS = [56, 440, 88, 64, 56, 84, 200]


class SpiderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("爱奇艺视频信息爬虫 · 课堂练习")
        self.configure(bg=BG)
        self.geometry("1120x720")
        self.minsize(940, 600)

        self.records = []                  # 当前表格里的所有记录
        self.message_queue = queue.Queue()  # 后台线程 -> 界面 的消息管道
        self.worker = None
        self.stop_event = None
        self.keyword = ""

        self._setup_style()
        self._build_ui()
        self._center_window()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_queue)

    # ------------------------------------------------------------ 界面搭建
    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", font=(FONT, 10), padding=(12, 7))
        style.configure("Accent.TButton", font=(FONT, 10, "bold"),
                        padding=(16, 8), background=ACCENT, foreground="white", borderwidth=0)
        style.map("Accent.TButton",
                  background=[("active", ACCENT_DARK), ("disabled", "#a9dcab")],
                  foreground=[("disabled", "#f2f2f2")])
        style.configure("TCombobox", padding=4)
        style.configure("TSpinbox", padding=4)
        style.configure("Treeview", font=(FONT, 10), rowheight=28,
                        background=CARD, fieldbackground=CARD, borderwidth=0)
        style.configure("Treeview.Heading", font=(FONT, 10, "bold"),
                        background="#eef0f3", foreground=TEXT, padding=(6, 8))
        style.map("Treeview.Heading", background=[("active", "#e4e7eb")])
        style.map("Treeview", background=[("selected", ACCENT_LIGHT)],
                  foreground=[("selected", TEXT)])
        style.configure("TProgressbar", background=ACCENT, troughcolor="#e8ebee",
                        borderwidth=0, thickness=8)
        style.configure("Vertical.TScrollbar", background="#d5d9de", borderwidth=0, arrowsize=12)
        style.configure("Horizontal.TScrollbar", background="#d5d9de", borderwidth=0, arrowsize=12)

    def _build_ui(self):
        # ---------- 顶部标题栏
        header = tk.Frame(self, bg=CARD)
        header.pack(fill="x")
        tk.Frame(header, bg=ACCENT, height=3).pack(fill="x")
        title_box = tk.Frame(header, bg=CARD)
        title_box.pack(fill="x", padx=22, pady=(14, 12))
        tk.Label(title_box, text="爱奇艺视频信息爬虫", bg=CARD, fg=ACCENT,
                 font=(FONT, 18, "bold")).pack(side="left")
        tk.Label(title_box, text="课堂练习 · 只抓公开的搜索结果信息，不下载正片",
                 bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(12, 0), pady=(6, 0))
        tk.Label(title_box, text="标准库实现 · 零依赖", bg=ACCENT_LIGHT, fg=ACCENT_DARK,
                 font=(FONT, 9), padx=8, pady=2).pack(side="right")

        # ---------- 搜索条件卡片
        card = tk.Frame(self, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER)
        card.pack(fill="x", padx=18, pady=(14, 0))

        form = tk.Frame(card, bg=CARD)
        form.pack(fill="x", padx=18, pady=14)

        tk.Label(form, text="关键词", bg=CARD, fg=TEXT, font=(FONT, 10)).pack(side="left")
        self.keyword_var = tk.StringVar(value="狂飙")
        self.keyword_entry = ttk.Entry(form, textvariable=self.keyword_var, width=24, font=(FONT, 10))
        self.keyword_entry.pack(side="left", padx=(8, 18))
        self.keyword_entry.bind("<Return>", lambda _event: self.start_crawl())

        tk.Label(form, text="类型", bg=CARD, fg=TEXT, font=(FONT, 10)).pack(side="left")
        self.mode_var = tk.StringVar(value="综合")
        self.mode_box = ttk.Combobox(form, textvariable=self.mode_var, width=8,
                                     values=list(parser.MODES.keys()), state="readonly",
                                     font=(FONT, 10))
        self.mode_box.pack(side="left", padx=(8, 18))

        tk.Label(form, text="页数", bg=CARD, fg=TEXT, font=(FONT, 10)).pack(side="left")
        self.pages_var = tk.StringVar(value="3")
        self.pages_box = ttk.Spinbox(form, from_=1, to=20, textvariable=self.pages_var,
                                     width=5, font=(FONT, 10))
        self.pages_box.pack(side="left", padx=(8, 22))

        self.start_button = ttk.Button(form, text="开始抓取", style="Accent.TButton",
                                       command=self.start_crawl)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(form, text="停止", command=self.stop_crawl, state="disabled")
        self.stop_button.pack(side="left", padx=(10, 0))

        # ---------- 结果操作栏
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=18, pady=(12, 6))
        self.export_csv_button = ttk.Button(bar, text="导出 CSV", command=lambda: self.export("csv"))
        self.export_csv_button.pack(side="left")
        self.export_json_button = ttk.Button(bar, text="导出 JSON", command=lambda: self.export("json"))
        self.export_json_button.pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="打开数据文件夹", command=self.open_data_folder).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="清空结果", command=self.clear_records).pack(side="left", padx=(8, 0))
        self.count_label = tk.Label(bar, text="共 0 条", bg=BG, fg=MUTED, font=(FONT, 10))
        self.count_label.pack(side="right")

        # ---------- 表格
        table_card = tk.Frame(self, bg=CARD, highlightthickness=1,
                              highlightbackground=BORDER, highlightcolor=BORDER)
        table_card.pack(fill="both", expand=True, padx=18)

        self.tree = ttk.Treeview(table_card, columns=HEADERS, show="headings",
                                 selectmode="browse")
        for header, width in zip(HEADERS, WIDTHS):
            anchor = "center" if header != "标题" and header != "标签" else "w"
            self.tree.heading(header, text=header, anchor=anchor)
            self.tree.column(header, width=width, anchor=anchor,
                             stretch=(header == "标题"))
        self.tree.tag_configure("odd", background=CARD)
        self.tree.tag_configure("even", background="#fafbfc")

        vertical = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(table_card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        table_card.rowconfigure(0, weight=1)
        table_card.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._open_selected)

        # ---------- 进度条 + 状态
        status_bar = tk.Frame(self, bg=BG)
        status_bar.pack(fill="x", padx=18, pady=(10, 4))
        self.progress = ttk.Progressbar(status_bar, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True)
        self.status_var = tk.StringVar(value="输入关键词，点「开始抓取」")
        tk.Label(status_bar, textvariable=self.status_var, bg=BG, fg=MUTED,
                 font=(FONT, 9), width=34, anchor="e").pack(side="left", padx=(12, 0))

        # ---------- 日志
        log_card = tk.Frame(self, bg=CARD, highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=BORDER)
        log_card.pack(fill="x", padx=18, pady=(0, 16))
        log_title = tk.Frame(log_card, bg=CARD)
        log_title.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(log_title, text="运行日志", bg=CARD, fg=TEXT,
                 font=(FONT, 9, "bold")).pack(side="left")
        tk.Label(log_title, text="（抓不到数据时，先看这里）", bg=CARD, fg=MUTED,
                 font=(FONT, 9)).pack(side="left", padx=(6, 0))

        log_box = tk.Frame(log_card, bg=CARD)
        log_box.pack(fill="both", expand=True, padx=12, pady=(4, 10))
        self.log_text = tk.Text(log_box, height=5, bg="#fbfcfd", fg="#3c4149",
                                font=("Consolas", 9), relief="flat", wrap="word",
                                state="disabled", insertbackground=TEXT)
        log_scroll = ttk.Scrollbar(log_box, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        self._set_running(False)

    def _center_window(self):
        """按屏幕大小决定窗口尺寸：屏幕小就缩一点，保证整个窗口都在屏幕里。"""
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(1120, screen_w - 60)
        height = max(560, min(720, screen_h - 100))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ------------------------------------------------------------ 抓取流程
    def start_crawl(self):
        if self.worker and self.worker.is_alive():
            return
        keyword = self.keyword_var.get().strip()
        if not keyword:
            messagebox.showwarning("还没填关键词", "请先输入要搜索的视频名称，比如：狂飙")
            return
        try:
            pages = max(1, min(20, int(self.pages_var.get())))
        except (TypeError, ValueError):
            messagebox.showwarning("页数不对", "页数要填 1~20 之间的整数")
            return

        mode = parser.MODES.get(self.mode_var.get(), 0)
        self.keyword = keyword
        self.clear_records()
        self._append_log(f"=== 开始抓取「{keyword}」，类型：{self.mode_var.get()}，共 {pages} 页 ===")
        self._set_running(True)
        self.progress.configure(value=0)
        self.status_var.set("正在抓取…")

        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._crawl_worker,
                                       args=(keyword, pages, mode), daemon=True)
        self.worker.start()

    def _crawl_worker(self, keyword, pages, mode):
        """在后台线程里跑，绝对不能碰界面控件，只能往 queue 里放消息。"""
        try:
            crawler = Crawler()
            report = crawler.crawl(
                keyword, pages=pages, mode=mode,
                on_log=lambda message: self.message_queue.put(("log", message)),
                on_progress=lambda value: self.message_queue.put(("progress", value)),
                on_page=lambda page, total, new: self.message_queue.put(("page", page, total, new)),
                stop_event=self.stop_event,
            )
            self.message_queue.put(("done", report, crawler.client.request_count))
        except Exception as error:  # noqa: BLE001 - 界面必须兜住所有异常，否则线程静默死掉
            self.message_queue.put(("error", error, traceback.format_exc()))

    def stop_crawl(self):
        if self.stop_event:
            self.stop_event.set()
            self.status_var.set("正在停止…")
            self._append_log("收到停止指令，本页抓完就停")

    def _drain_queue(self):
        """主线程每 100 毫秒看一眼：后台有没有新消息？"""
        try:
            while True:
                message = self.message_queue.get_nowait()
                kind = message[0]
                if kind == "log":
                    self._append_log(message[1])
                elif kind == "progress":
                    self.progress.configure(value=message[1] * 100)
                elif kind == "page":
                    _page, total, new_records = message[1], message[2], message[3]
                    self._add_rows(new_records)
                    self.status_var.set(f"已抓取 {len(self.records)} 条 · 第 {_page}/{total} 页")
                elif kind == "done":
                    self._on_finished(message[1], message[2])
                elif kind == "error":
                    self._on_failed(message[1], message[2])
        except queue.Empty:
            pass
        except Exception:  # 处理消息时出意外，也不该让整个界面"停摆"
            traceback.print_exc()
        finally:
            try:
                self.after(100, self._drain_queue)
            except tk.TclError:
                pass                      # 窗口已经关了，不用再调度

    def _on_finished(self, report, request_count):
        self._set_running(False)
        if not report.stopped:
            self.progress.configure(value=100)
        self._add_rows([])  # 触发一次计数刷新
        if report.stopped:
            self.status_var.set(f"已停止 · 共 {len(self.records)} 条")
            self._append_log(f"=== 用户停止，共 {len(self.records)} 条，请求 {request_count} 次 ===")
        else:
            self.status_var.set(f"完成 · 共 {len(self.records)} 条")
            self._append_log(f"=== 完成：{len(self.records)} 条，请求 {request_count} 次 ===")

        if not self.records:
            if report.stopped:
                messagebox.showinfo("已停止", "还没抓到数据就停了。")
            elif report.total == 0:
                messagebox.showinfo("没有结果", "这个关键词没搜到东西，换个词试试（比如：狂飙）。")
            else:
                messagebox.showinfo("没抓到数据", "接口可能变了，看日志里的最后一行为什么失败。\n"
                                                "可以先打开爱奇艺搜索页，按 F12 看它现在调用的是哪个地址。")
            return

        # 自动存一份到 data 文件夹，省得每次手动导出
        try:
            csv_path = storage.make_filename(self.keyword, "csv")
            json_path = csv_path.with_suffix(".json")     # 和 CSV 用同一个时间戳
            storage.save_csv(self.records, csv_path)
            storage.save_json(self.records, json_path, self.keyword)
            self._append_log(f"已自动保存：{csv_path.name} / {json_path.name}")
            self._append_log(f"文件位置：{storage.DEFAULT_OUTDIR}")
        except OSError as error:
            self._append_log(f"⚠ 自动保存失败：{error}")

    def _on_failed(self, error, detail):
        self._set_running(False)
        self.status_var.set("出错了")
        self._append_log(f"✗ {type(error).__name__}: {error}")
        print(detail)
        messagebox.showerror("抓取出错", f"{type(error).__name__}\n{error}\n\n详细信息已打印到终端。")

    # ------------------------------------------------------------ 表格
    def _add_rows(self, records):
        start = len(self.records)
        self.records.extend(records)
        for offset, record in enumerate(records):
            number = start + offset + 1
            self.tree.insert(
                "", "end", iid=str(number),
                values=(number, record["title"], record["channel"], record["year"],
                        record["rating"], record["duration"], record["tags"]),
                tags=("odd" if number % 2 else "even",),
            )
        self.count_label.configure(text=f"共 {len(self.records)} 条")

    def clear_records(self):
        self.records.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.count_label.configure(text="共 0 条")

    def _open_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        index = int(selection[0]) - 1
        if 0 <= index < len(self.records):
            url = self.records[index].get("url")
            if url:
                webbrowser.open(url)
                self._append_log(f"打开：{url}")

    # ------------------------------------------------------------ 导出 / 杂项
    def export(self, kind):
        if not self.records:
            messagebox.showinfo("没有数据", "先抓一点数据再导出吧")
            return
        default_path = storage.make_filename(self.keyword or "搜索结果", kind)
        filetypes = [("CSV 表格", "*.csv")] if kind == "csv" else [("JSON 数据", "*.json")]
        path = filedialog.asksaveasfilename(
            title="导出到…",
            initialdir=str(storage.DEFAULT_OUTDIR),
            initialfile=default_path.name,
            defaultextension=f".{kind}",
            filetypes=filetypes,
        )
        if not path:
            return
        try:
            if kind == "csv":
                saved = storage.save_csv(self.records, path)
            else:
                saved = storage.save_json(self.records, path, self.keyword)
        except OSError as error:
            messagebox.showerror("保存失败", f"{error}\n\n是不是文件正被 Excel 打开着？")
            return
        self._append_log(f"已导出 {len(self.records)} 条 → {saved}")
        self.status_var.set("导出完成")
        messagebox.showinfo("导出成功", f"已保存到：\n{saved}")

    def open_data_folder(self):
        folder = storage.DEFAULT_OUTDIR
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(folder)
        except (AttributeError, OSError):
            messagebox.showinfo("数据文件夹", str(folder))

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_running(self, running):
        """
        抓取时把「开始抓取」按钮锁住、把「停止」按钮放开，其它输入框保持可编辑。
        为什么不连输入框一起 disable？一是抓取用的关键词在点按钮那一刻已经记下来了，
        改输入框不影响正在跑的任务；二是省掉"禁用→启用"这一圈状态切换，
        少一类 tkinter 重绘上的坑（ttk.Entry 这类控件偶尔会不刷新显示的文本）。
        """
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("还在抓取", "任务还没结束，确定要退出吗？"):
                return
            if self.stop_event:
                self.stop_event.set()
        self.destroy()


def main():
    app = SpiderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
