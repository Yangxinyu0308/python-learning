r"""
核算表审计脚本
--------------------------------------------------
作用：把你手工填的《阿米巴经营分析·核算表》重新算一遍，
      和表里现有的数字比对，把「算错的 / 没算的 / 口径不一致的」全部揪出来。

用法：
    python audit_核算表.py "C:\路径\8月阿米巴经营分析.xlsx"
    python audit_核算表.py "C:\路径\某表.xlsx" --sheet "1.核算表"

为什么要有它：
    Excel 公式拖错了不会报错，只会静默地错。程序算错会立刻暴露。
"""

import sys
from datetime import datetime

import openpyxl

# Windows 终端默认是 GBK，输出中文/符号会崩，强制成 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------- 列位置（从 1 开始数）----------
COL_NAME = 1      # A 项目
COL_SUB = 2       # B 子项
COL_ITEM = 3      # C 细项
COL_FORMULA = 4   # D 计算公式
COL_PLAN = 5      # E 预定金额
COL_PLAN_PCT = 6  # F 预计占比
COL_ACT = 7       # G 实际金额
COL_ACT_PCT = 8   # H 实际占比
COL_DIFF = 9      # I 差异金额
COL_RATE = 10     # J 达成比
COL_LAST = 11     # K 上期金额
COL_MOM = 12      # L 环比
COL_YOY_BASE = 13 # M 去年同期
COL_YOY = 14      # N 同比

TOL = 0.005  # 容许误差 0.5%（手工填的四舍五入）


def to_number(v):
    """把单元格里的值转成数字；转不了就返回 None。

    能处理：数字、"1,234.5"、"12.5%"、"/"、空、'#DIV/0!'
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in ("", "/", "-", "—", "#DIV/0!", "#VALUE!", "#REF!"):
        return None
    s = s.replace(",", "").replace("元", "").replace("次", "").replace("家", "")
    is_pct = s.endswith("%")
    if is_pct:
        s = s[:-1]
    try:
        num = float(s)
    except ValueError:
        return None
    return num / 100 if is_pct else num


def close(a, b):
    """两个数是否足够接近（相对误差）。"""
    if a is None or b is None:
        return None
    if b == 0:
        return abs(a) < 1e-9
    return abs(a - b) / abs(b) <= TOL


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    path = sys.argv[1]
    sheet = "1.核算表"
    if "--sheet" in sys.argv:
        sheet = sys.argv[sys.argv.index("--sheet") + 1]

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet]

    rows = []
    for r in range(4, ws.max_row + 1):
        name = ws.cell(r, COL_NAME).value
        sub = ws.cell(r, COL_SUB).value
        item = ws.cell(r, COL_ITEM).value
        label = " / ".join(str(x) for x in (name, sub, item) if x)
        if not label:
            continue
        rows.append({
            "row": r,
            "label": label,
            "plan": to_number(ws.cell(r, COL_PLAN).value),
            "act": to_number(ws.cell(r, COL_ACT).value),
            "diff": to_number(ws.cell(r, COL_DIFF).value),
            "rate": to_number(ws.cell(r, COL_RATE).value),
            "last": to_number(ws.cell(r, COL_LAST).value),
            "mom": to_number(ws.cell(r, COL_MOM).value),
            "yoy_base": to_number(ws.cell(r, COL_YOY_BASE).value),
            "yoy": to_number(ws.cell(r, COL_YOY).value),
            "raw_rate": ws.cell(r, COL_RATE).value,
        })

    problems = []      # 硬错误：算错、漏算
    warnings = []      # 口径/格式问题

    print("=" * 78)
    print(f"核算表审计 —— {path}")
    print(f"工作表：{sheet}    数据行：{len(rows)}")
    print("=" * 78)

    # 1) 达成比 = 实际 / 预定
    print("\n【1】预实达成率  公式：实际 ÷ 预定")
    print(f"{'行':>3} {'项目':<28} {'预定':>12} {'实际':>12} {'应得':>9} {'表里':>9} {'判定'}")
    for d in rows:
        plan, act = d["plan"], d["act"]
        if plan is None or plan == 0:
            continue
        expect = act / plan if act is not None else None
        ok = close(d["rate"], expect)
        flag = "OK" if ok else "❌ 不一致"
        print(f"{d['row']:>3} {d['label'][:28]:<28} {plan:>12,.0f} "
              f"{(act or 0):>12,.0f} {expect:>8.2%} "
              f"{(d['rate'] if d['rate'] is not None else -1):>8.2%} {flag}")
        if not ok:
            problems.append(f"第 {d['row']} 行「{d['label']}」达成比应为 {expect:.2%}，表里是 {d['rate']:.2%}"
                            if d["rate"] is not None else
                            f"第 {d['row']} 行「{d['label']}」达成比为空，应为 {expect:.2%}")

    # 2) 差异金额的符号约定
    print("\n【2】差异金额  检查符号口径是否统一")
    sign_plan_minus_act = []
    sign_act_minus_plan = []
    for d in rows:
        plan, act, diff = d["plan"], d["act"], d["diff"]
        if None in (plan, act, diff):
            continue
        if abs((plan - act) - diff) < 0.01:
            sign_plan_minus_act.append(d["row"])
        elif abs((act - plan) - diff) < 0.01:
            sign_act_minus_plan.append(d["row"])
        else:
            problems.append(f"第 {d['row']} 行「{d['label']}」差异金额 {diff:,.2f} 与 预定-实际={plan-act:,.2f} 都不符")
    print(f"  用「预定 − 实际」的行：{sign_plan_minus_act}")
    print(f"  用「实际 − 预定」的行：{sign_act_minus_plan}")
    if sign_plan_minus_act and sign_act_minus_plan:
        warnings.append(
            "同一张表里差异金额用了两套相反的符号："
            f"第 {sign_plan_minus_act} 行是「预定−实际」，第 {sign_act_minus_plan} 行是「实际−预定」。"
            "读表的人会误解正负号的含义。"
        )

    # 3) 环比 = 实际 / 上期 - 1
    print("\n【3】环比  公式：实际 ÷ 上期 − 1")
    for d in rows:
        last, act = d["last"], d["act"]
        if last is None or last == 0 or act is None:
            continue
        expect = act / last - 1
        ok = close(d["mom"], expect)
        if not ok:
            problems.append(
                f"第 {d['row']} 行「{d['label']}」环比应为 {expect:+.2%}，表里是 "
                f"{'空' if d['mom'] is None else format(d['mom'], '+.2%')}"
            )

    # 4) 同比 = 实际 / 去年同期 - 1
    print("\n【4】同比  公式：实际 ÷ 去年同期 − 1")
    for d in rows:
        base, act = d["yoy_base"], d["act"]
        if base is None or base == 0 or act is None:
            continue
        expect = act / base - 1
        ok = close(d["yoy"], expect)
        if not ok:
            problems.append(
                f"第 {d['row']} 行「{d['label']}」同比应为 {expect:+.2%}，表里是 "
                f"{'空' if d['yoy'] is None else format(d['yoy'], '+.2%')}"
            )

    # 5) Excel 错误值
    print("\n【5】Excel 错误值（#DIV/0! 之类）")
    err_cells = []
    for r in range(4, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            v = ws.cell(r, c).value
            if isinstance(v, str) and v.startswith("#"):
                err_cells.append((r, c, v))
    if err_cells:
        for r, c, v in err_cells:
            print(f"  第 {r} 行 第 {c} 列 → {v}")
        warnings.append(f"表里有 {len(err_cells)} 个 Excel 错误值（#DIV/0!），"
                        "说明预定为 0 时公式还在除。程序可以输出「—」而不是报错。")
    else:
        print("  无")

    # 6) 三周的周度数据是文本还是数字——留待 v2

    # ---------- 汇总 ----------
    print("\n" + "=" * 78)
    print(f"结论：{len(problems)} 个硬错误，{len(warnings)} 个口径/格式问题")
    print("=" * 78)
    for i, p in enumerate(problems, 1):
        print(f"❌ {i}. {p}")
    for i, w in enumerate(warnings, 1):
        print(f"⚠️  {i}. {w}")

    # 写一份报告
    out = f"审计报告_{datetime.now():%Y%m%d_%H%M}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# 核算表审计报告\n\n- 文件：`{path}`\n- 工作表：{sheet}\n"
                f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M}\n\n")
        f.write(f"## 硬错误（{len(problems)}）\n\n")
        for p in problems:
            f.write(f"- {p}\n")
        f.write(f"\n## 口径/格式问题（{len(warnings)}）\n\n")
        for w in warnings:
            f.write(f"- {w}\n")
    print(f"\n📄 报告已保存：{out}")
    wb.close()


if __name__ == "__main__":
    main()
