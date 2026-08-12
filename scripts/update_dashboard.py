#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Raymond 全球物流工作台 - 云端每日自动更新脚本
===============================================
功能（无需任何 API Key 即可运行）：
  1. 通过腾讯行情接口抓取 海康威视 / 招商轮船 / A股三大指数 / 恒生指数 / 恒生科技 实时行情
  2. 通过 open.er-api.com 抓取 USD/CNY、EUR/CNY 汇率
  3. 更新 data/briefing.json 与 data/portfolio.json 中的行情数字与日期
  4. 内容类数据（预警/运价/洞察/英语等）保留最近一次人工整理内容，不做编造

运行：python3 scripts/update_dashboard.py
部署：由 .github/workflows/daily-update.yml 每天北京时间 9:00 自动触发
"""
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


def fetch(url, encoding="utf-8", timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (dashboard-bot)"})
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
        # 成交量(手)*100*价 => 元，转亿
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

    name_map = {
        "上证指数": "sh000001", "深证成指": "sz399001", "创业板指": "sz399006",
        "恒生指数": "r_hkHSI", "恒生科技": "r_hkHSTECH",
    }
    for g in mkt.get("global", []):
        sym = name_map.get(g.get("name"))
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


def main():
    if not quotes:
        print("!! 行情抓取全部失败，检查网络或接口。仍更新日期与汇率。")
    upd_briefing()
    upd_portfolio()
    print("完成：", today, "| 有变更" if changed else "| 无行情变化")
    sys.exit(0)


if __name__ == "__main__":
    main()
