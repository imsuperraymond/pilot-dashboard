#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Raymond 全球物流工作台 - 云端每日自动更新脚本
===============================================
功能（无需任何 API Key 即可运行）：
  1. 腾讯行情接口抓取：海康威视 / 招商轮船 / A股三大指数 / 恒生指数 / 恒生科技 / 道琼斯 / 标普500 / 纳斯达克
  2. 新浪期货接口抓取：WTI原油 / 布伦特原油 / COMEX黄金
  3. open.er-api.com 抓取 USD/CNY、EUR/CNY 汇率
  4. RSS 自动抓取国际物流新闻（The Loadstar / FreightWaves / BBC中文）写入 logistics.json.intlNews
  5. 更新 4 个 data 文件中的行情数字、日期与 updatedAt
  6. 中文深度内容（预警/运价点评/洞察/英语等）保留最近一次人工整理内容，不做编造

运行：python3 scripts/update_dashboard.py
部署：由 .github/workflows/daily-update.yml 每天北京时间 08:00/09:30/15:00/17:00 自动触发
"""
import html
import json
import os
import re
import sys
import datetime
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
BJ_TZ = datetime.timezone(datetime.timedelta(hours=8))


def now_bj():
    return datetime.datetime.now(BJ_TZ)


def fetch(url, encoding="utf-8", timeout=15, headers=None):
    h = {"User-Agent": "Mozilla/5.0 (dashboard-bot)"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(encoding, errors="replace")


def load_json(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def save_json(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    print("  saved", name)


def fmt_pct(p):
    return ("+" if p >= 0 else "") + "%.2f%%" % p


def fmt_num(v):
    return format(v, ",.2f")


def to_float(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


# ============ 1. 行情抓取（腾讯） ============
SYMBOLS = {
    "sz002415": "002415",      # 海康威视
    "sh601872": "601872",      # 招商轮船
    "sh000001": "SH000001",    # 上证指数
    "sz399001": "SZ399001",    # 深证成指
    "sz399006": "SZ399006",    # 创业板指
    "r_hkHSI": "HKHSI",        # 恒生指数
    "r_hkHSTECH": "HKHSTECH",  # 恒生科技指数
    "usDJI": "US-DJIA",        # 道琼斯
    "usINX": "US-SP500",       # 标普500
    "usIXIC": "US-IXIC",       # 纳斯达克
}

quotes = {}
try:
    raw = fetch("https://qt.gtimg.cn/q=" + ",".join(SYMBOLS.keys()), encoding="gbk")
    for line in raw.split(";"):
        m = re.search(r'v_([\w]+)="([^"]*)"', line)
        if not m:
            continue
        sym, payload = m.group(1), m.group(2)
        f = payload.split("~")
        if len(f) < 35:
            continue
        price = to_float(f[3])
        prev = to_float(f[4])
        if price is None or prev is None:
            continue
        pct = (price - prev) / prev * 100 if prev else 0.0
        vol_wan = None
        try:
            vol_wan = float(f[6]) * 100 * price / 1e8
        except (TypeError, ValueError):
            pass
        quotes[sym] = {
            "name": f[1],
            "price": price,
            "prev": prev,
            "open": to_float(f[5]),
            "high": to_float(f[33]),
            "low": to_float(f[34]),
            "pct": pct,
            "chg": price - prev,
            "time": f[30] if len(f) > 30 else "",
            "vol_wan": vol_wan,
        }
    print("行情抓取成功:", {k: (v["name"], round(v["price"], 2), round(v["pct"], 2)) for k, v in quotes.items()})
except Exception as e:
    print("行情抓取失败:", e)

# ============ 1b. 外盘期货（新浪）：WTI/布伦特/黄金 ============
FUTURES = {"hf_CL": "WTI原油", "hf_OIL": "布伦特原油", "hf_GC": "COMEX黄金"}
futures = {}
try:
    raw = fetch("https://hq.sinajs.cn/list=" + ",".join(FUTURES.keys()),
                encoding="gbk", headers={"Referer": "https://finance.sina.com.cn"})
    for line in raw.strip().split("\n"):
        if '="' not in line:
            continue
        code = line.split("=")[0].replace("var hq_str_", "")
        f = line.split('"')[1].split(",")
        price = to_float(f[0])
        prev = to_float(f[4]) if len(f) > 4 else None
        if price is None or prev is None:
            continue
        futures[code] = {
            "name": FUTURES.get(code, code),
            "price": price,
            "prev": prev,
            "pct": (price - prev) / prev * 100 if prev else 0.0,
        }
    print("外盘期货抓取成功:", {k: (v["name"], round(v["price"], 2), round(v["pct"], 2)) for k, v in futures.items()})
except Exception as e:
    print("外盘期货抓取失败:", e)

# ============ 2. 汇率抓取 ============
fx = {}
try:
    j = json.loads(fetch("https://open.er-api.com/v6/latest/USD"))
    if j.get("result") == "success":
        r = j.get("rates", {})
        cny, eur, hkd = r.get("CNY"), r.get("EUR"), r.get("HKD")
        if cny:
            fx["usdcny"] = cny
        if cny and eur:
            fx["eurcny"] = cny / eur
        if cny and hkd:
            fx["hkd"] = cny / hkd
    print("汇率抓取成功:", {k: round(v, 4) for k, v in fx.items()})
except Exception as e:
    print("汇率抓取失败:", e)

# ============ 2b. 国际物流新闻 RSS（自动抓取，无需 Key） ============
RSS_FEEDS = [
    ("The Loadstar", "https://theloadstar.com/feed/"),
    ("FreightWaves", "https://www.freightwaves.com/feed/"),
    ("BBC中文", "https://feeds.bbci.co.uk/zhongwen/simp/rss.xml"),
]
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def parse_pubdate(s):
    """'Fri, 14 Aug 2026 08:00:00 GMT' -> '2026-08-14'"""
    if not s:
        return ""
    m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", s)
    if not m:
        return ""
    d, mo, y = m.group(1), MONTHS.get(m.group(2)), m.group(3)
    return "%s-%02d-%s" % (y, mo, d.zfill(2)) if mo else ""


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch_intl_news(limit=6):
    items = []
    for source, url in RSS_FEEDS:
        try:
            body = fetch(url, timeout=12)
            for it in re.findall(r"<item>(.*?)</item>", body, re.S)[:8]:
                t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
                d = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
                lk = re.search(r"<link>(.*?)</link>", it, re.S)
                pd = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
                title = strip_html(t.group(1)) if t else ""
                if not title:
                    continue
                desc = strip_html(d.group(1))[:150] if d else ""
                link = (lk.group(1).strip() if lk else "").split("&")[0]
                date = parse_pubdate(pd.group(1)) if pd else ""
                items.append({"source": source, "title": title, "desc": desc,
                              "date": date, "link": link})
        except Exception as e:
            print("  RSS失败[%s]: %s" % (source, e))
    # 去重 + 排序（有日期的优先，其次标题长度）
    seen, uniq = set(), []
    for it in items:
        key = it["title"][:60]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    uniq.sort(key=lambda x: (x["date"], len(x["title"])), reverse=True)
    return uniq[:limit]


today = now_bj().strftime("%Y-%m-%d")
now_iso = now_bj().strftime("%Y-%m-%dT%H:%M:%S+08:00")
now_hm = now_bj().strftime("%H:%M")
changed = False


def upd_briefing():
    global changed
    print("[briefing.json]")
    brief = load_json("briefing.json")
    if brief.get("date") != today:
        brief["date"] = today
        changed = True
    brief["updatedAt"] = now_iso
    mkt = brief.setdefault("markets", {})

    def set_idx(key, sym):
        global changed
        q = quotes.get(sym)
        if not q:
            return
        if mkt.get(key) != {"value": fmt_num(q["price"]), "change": fmt_pct(q["pct"])}:
            mkt[key] = {"value": fmt_num(q["price"]), "change": fmt_pct(q["pct"])}
            changed = True

    set_idx("shanghai", "sh000001")
    set_idx("shenzhen", "sz399001")

    if fx.get("usdcny") and mkt.get("usdcny") != "%.4f" % fx["usdcny"]:
        mkt["usdcny"] = "%.4f" % fx["usdcny"]
        changed = True

    # 全球市场：A股/港股/美股/原油/黄金全部自动更新
    name_map = {
        "上证指数": "sh000001", "深证成指": "sz399001", "创业板指": "sz399006",
        "恒生指数": "r_hkHSI", "恒生科技": "r_hkHSTECH",
        "道琼斯": "usDJI", "标普500": "usINX", "纳斯达克": "usIXIC",
    }
    for g in mkt.get("global", []):
        nm = g.get("name", "")
        if nm in ("WTI原油", "布伦特原油", "COMEX黄金"):
            code = {"WTI原油": "hf_CL", "布伦特原油": "hf_OIL", "COMEX黄金": "hf_GC"}[nm]
            q = futures.get(code)
            if not q:
                continue
            new_close = "$" + fmt_num(q["price"])
            new_chg = fmt_pct(q["pct"])
            if g.get("close") != new_close or g.get("change") != new_chg:
                g["close"], g["change"] = new_close, new_chg
                changed = True
            continue
        sym = name_map.get(nm)
        q = quotes.get(sym or "")
        if not q:
            continue
        new_close, new_chg = fmt_num(q["price"]), fmt_pct(q["pct"])
        if g.get("close") != new_close or g.get("change") != new_chg:
            g["close"], g["change"] = new_close, new_chg
            changed = True
    save_json("briefing.json", brief)


def upd_portfolio():
    global changed
    print("[portfolio.json]")
    pf = load_json("portfolio.json")
    if pf.get("date") != today:
        pf["date"] = today
        changed = True
    pf["updatedAt"] = now_iso

    for st in pf.get("stocks", []):
        code = st.get("code", "")
        sym = ("sz" if code[:1] in "013" else "sh") + code
        q = quotes.get(sym)
        if not q:
            continue
        st["close"] = round(q["price"], 2)
        st["prevClose"] = round(q["prev"], 2)
        st["change"] = fmt_pct(q["pct"])
        st["changeAmount"] = round(q["chg"], 2)
        if q["open"] is not None:
            st["open"] = round(q["open"], 2)
        if q["high"] is not None:
            st["high"] = round(q["high"], 2)
        if q["low"] is not None:
            st["low"] = round(q["low"], 2)
        if q["vol_wan"] is not None:
            st["amount"] = "%.2f亿" % q["vol_wan"]
        st["source"] = "腾讯行情自动更新 %s" % now_hm
        changed = True

    mkt = pf.setdefault("market", {})
    idx_map = {"shIndex": "sh000001", "szIndex": "sz399001", "cybIndex": "sz399006",
               "hsi": "r_hkHSI", "hstech": "r_hkHSTECH"}
    for key, sym in idx_map.items():
        q = quotes.get(sym)
        if not q:
            continue
        cur = mkt.get(key, {})
        new_close, new_chg = round(q["price"], 2), fmt_pct(q["pct"])
        if cur.get("close") != new_close or cur.get("change") != new_chg:
            cur["close"] = new_close
            cur["change"] = new_chg
            mkt[key] = cur
            changed = True

    mac = pf.setdefault("macro", {})
    if fx.get("usdcny") and mac.get("usdcnh") != "%.4f" % fx["usdcny"]:
        mac["usdcnh"] = "%.4f" % fx["usdcny"]
        changed = True
    if fx.get("eurcny") and mac.get("eurcnh") != "%.4f" % fx["eurcny"]:
        mac["eurcnh"] = "%.4f" % fx["eurcny"]
        changed = True
    save_json("portfolio.json", pf)


def upd_logistics():
    global changed
    print("[logistics.json]")
    lg = load_json("logistics.json")
    if lg.get("date") != today:
        lg["date"] = today
        changed = True
    lg["updatedAt"] = now_iso
    # 国际物流新闻自动抓取
    news = fetch_intl_news(limit=6)
    if news:
        lg["intlNews"] = news
        changed = True
        print("  国际新闻更新 %d 条: %s" % (len(news), [n["source"] for n in news]))
    else:
        print("  国际新闻抓取失败，保留上次内容")
    save_json("logistics.json", lg)


def upd_cognition():
    global changed
    print("[cognition.json]")
    cg = load_json("cognition.json")
    if cg.get("date") != today:
        cg["date"] = today
        changed = True
    cg["updatedAt"] = now_iso
    save_json("cognition.json", cg)


def main():
    if not quotes:
        print("!! 行情抓取全部失败，检查网络或接口。仍更新日期与汇率。")
    upd_briefing()
    upd_portfolio()
    upd_logistics()
    upd_cognition()
    print("完成：", today, "| 有变更" if changed else "| 无行情变化")
    sys.exit(0)


if __name__ == "__main__":
    main()
