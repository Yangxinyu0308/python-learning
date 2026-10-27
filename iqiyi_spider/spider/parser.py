"""
解析模块 —— 只干一件事：把接口返回的一大坨 JSON，变成一行行整齐的数据。

这个文件里全是"纯函数"：给它数据，它给你结果，不联网、不读写文件。
好处是特别好测试 —— 就算断网，tests/ 里也能验证它对不对。

【给杨鑫玉的话】
看不懂某个函数别慌，先看 docstring（三引号里那句中文），再看 return 的那一行。
    python -c "from spider import parser; print(parser.build_search_url('狂飙'))"
可以随便改、随便试。
"""

import urllib.parse

# 爱奇艺搜索页背后调用的公开接口（打开 F12 → Network 就能看到它）
# 注意：这不是官方文档里的接口，是"观察"出来的，随时可能变。
SEARCH_API = "https://mesh.if.iqiyi.com/portal/lw/search/homePageV3"

# 搜索页顶上那几个分类标签。数字是接口的 mode 参数，属于"观察"出来的经验值，
# 不保证和网页上的标签一一对应 —— 这也是爬虫的日常：接口不给文档，只能试。
MODES = {"综合": 0, "长视频优先": 5, "短视频": 3}

# 记录里有哪些字段，以及导出 CSV / 显示在表格里时的中文表头。
# 想加字段？在这里加一行，然后去 normalize_item() 里把值取出来。
FIELDS = [
    ("title", "标题"),
    ("channel", "频道"),
    ("source", "来源"),
    ("year", "年份"),
    ("region", "地区"),
    ("rating", "评分"),
    ("hot", "热度"),
    ("duration", "时长"),
    ("actors", "主演"),
    ("tags", "标签"),
    ("summary", "简介"),
    ("vip", "VIP"),
    ("url", "链接"),
    ("video_id", "视频ID"),
]


def build_search_url(keyword, page=1, mode=0):
    """拼出第 page 页的搜索地址。中文关键词会自动做 URL 编码。"""
    params = {"key": keyword, "pageNum": page, "mode": mode}
    return SEARCH_API + "?" + urllib.parse.urlencode(params)


def describe_error(payload):
    """接口如果报错，返回一句人话；正常就返回 None。"""
    code = payload.get("code")
    if code in (None, "0", 0):
        return None
    msg = payload.get("msg") or payload.get("message") or ""
    return f"接口返回错误 code={code} {msg}".strip()


def normalize_item(template):
    """
    把一个 template（接口里的一条结果）变成一条干净的记录。
    如果这条结果没有标题（广告位、提示条之类），返回 None —— 直接丢掉。
    """
    album = template.get("albumInfo") or {}
    title = _text(album.get("title"))
    if not title:
        return None

    # channel 长这样："电视剧,2" —— 逗号前面是分类名，后面是分类编号
    channel = _text(album.get("channel"))
    channel_name = channel.split(",")[0] if channel else ""

    return {
        "title": title,
        "channel": channel_name,
        "source": _text(template.get("s3")),          # 短视频 / 剧集类型展示 / 电影类长视频 …
        "year": _year_of(album),
        "region": _text(_value_of(album.get("region"))),
        "rating": _number(album.get("rating")),
        "hot": _number(album.get("hot")),
        "duration": _duration_of(album),
        "actors": _join_people(album.get("actors") or album.get("directors")),
        "tags": _join_tags(album),
        "summary": _text(_value_of(album.get("brief"))) or _text(album.get("introduction")),
        "vip": "VIP" if _as_bool(album.get("firstVideoIsVip")) else "",
        "url": _text(album.get("pageUrl")),
        "video_id": _text(album.get("qipuId")),
    }


def parse_search_payload(payload):
    """从接口返回的整个 dict 里，取出所有视频记录（list[dict]）。"""
    data = payload.get("data") or {}
    templates = data.get("templates") or []
    records = []
    for template in templates:
        if isinstance(template, dict):
            record = normalize_item(template)
            if record:
                records.append(record)
    return records


def total_results(payload):
    """搜索结果总数，取不到就返回 0。"""
    try:
        return int((payload.get("data") or {}).get("resultNum") or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------- 下面是"工具函数"
# 接口里同一个意思的字段，有的包成 {"key": "简介", "value": "..."}，有的直接给字符串。
# 这堆小函数就是专门用来"抹平"这些差异的。


def _value_of(field):
    """{"key": "年份", "value": "2023"} -> "2023"；本来就是字符串 -> 原样返回。"""
    if isinstance(field, dict):
        return field.get("value")
    return field


def _text(value):
    """任何东西 -> 去掉两头空白的字符串。None 变成空字符串。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "、".join(_text(v) for v in value if v is not None)
    return str(value).strip()


def _number(value):
    """评分/热度：能转成数字就转，转不了给空字符串。"""
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value)
    # 9.0 显示成 9，9.5 保持 9.5
    return str(int(number)) if number == int(number) else f"{number:g}"


def _year_of(album):
    """年份：优先用 year 字段，没有就从不带年份的发布时间里截前 4 位。"""
    year = _text(_value_of(album.get("year")))
    if year:
        return year[:4] if year[:4].isdigit() else year
    release = _text(_value_of(album.get("releaseTime")))
    if len(release) >= 4 and release[:4].isdigit():
        return release[:4]
    return ""


def _duration_of(album):
    """
    时长：三种长相都要认。
      - 剧集："39集全"、"更新至12集"  → 原样返回
      - 短视频 / 部分电影："00:37"、"2:53:11" → 原样返回
      - 电影：subscriptContent 里放的其实是评分（"9.0"），真正的时长在 duration（毫秒）
    这是爬虫的日常：同一个字段，在不同类型的数据里装的是不一样的东西。
    """
    text = _text(album.get("subscriptContent"))

    # 带"集"或带冒号的，才是真正的时长文字
    if text and ("集" in text or ":" in text):
        return text

    milliseconds = album.get("duration")
    try:
        seconds = int(milliseconds) // 1000
    except (TypeError, ValueError):
        # 没有毫秒数时：纯数字的 label 多半是评分，宁可不显示也别写错
        return "" if _looks_like_number(text) else text

    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _looks_like_number(text):
    """判断一个字符串是不是"9"、"9.0"、"8.8" 这种纯数字（大概率是评分）。"""
    if not text:
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def _join_people(field):
    """主演：{"key": "主演", "value": [{"title": "张译"}, …]} -> "张译、张颂文"。"""
    people = _value_of(field)
    if not people:
        return ""
    if isinstance(people, dict):
        people = [people]
    if not isinstance(people, (list, tuple)):
        return _text(people)
    names = []
    for person in people:
        name = _text(person.get("title") or person.get("name")) if isinstance(person, dict) else _text(person)
        if name:
            names.append(name)
    return "、".join(names)


def _join_tags(album):
    """标签：baseTags / tags / metaTags 三个字段里，把"看起来像标签"的取出来拼一起。"""
    tags = []
    for item in album.get("baseTags") or []:
        tags.append(_text(_value_of(item)))
    for item in album.get("tags") or []:
        tags.append(_text(item.get("text")) if isinstance(item, dict) else _text(item))
    for item in album.get("metaTags") or []:
        if isinstance(item, dict) and item.get("style") == "special":
            tags.append(_text(item.get("name")))
    result = []
    for tag in tags:
        if tag and tag not in result:
            result.append(tag)
    return "、".join(result[:8])


def _as_bool(value):
    """接口里布尔值有时候给 True，有时候给字符串 "False"，这里统一成 True/False。"""
    if isinstance(value, bool):
        return value
    return _text(value).lower() in ("true", "1", "yes")
