from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .config import Config


def week_dates(week_id: str) -> tuple[date, date]:
    """2026-w42 → 那一週的週一和週五（ISO 週）。"""
    year, week = week_id.split("-w")
    monday = date.fromisocalendar(int(year), int(week), 1)
    return monday, monday + timedelta(days=4)


def pct(new: float, old: float) -> float:
    return round((new / old - 1) * 100, 2)


def fetch(week_id: str, cfg: Config, out: Path) -> dict:
    """用 Yahoo Finance 抓指數和觀察名單的週漲跌，寫成 market.json（保留手寫的 note）。"""
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("缺少套件，請先執行：pip install -r requirements.txt")
    monday, friday = week_dates(week_id)
    items = [("index", x) for x in cfg.market["indices"]] + [("stock", x) for x in cfg.market["watchlist"]]
    symbols = [x["symbol"] for _, x in items]
    closes = yf.download(symbols, start=monday - timedelta(days=10), end=friday + timedelta(days=1),
                         auto_adjust=False, progress=False)["Close"]

    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    notes = {s["symbol"]: s.get("note", "") for s in old.get("stocks", [])}
    result = {"as_of": None, "base_date": None, "source": "Yahoo Finance（yfinance）", "indices": [], "stocks": []}
    for kind, item in items:
        series = closes[item["symbol"]].dropna()
        before = series[series.index.date < monday]
        during = series[(series.index.date >= monday) & (series.index.date <= friday)]
        if before.empty or during.empty:
            print(f"  ⚠ {item['symbol']} 資料不足，略過")
            continue
        base, last = float(before.iloc[-1]), float(during.iloc[-1])
        result["base_date"] = str(before.index[-1].date())
        result["as_of"] = str(during.index[-1].date())
        row = {"symbol": item["symbol"], "name": item["name"], "close": round(last, 2), "change_pct": pct(last, base)}
        if kind == "index":
            result["indices"].append(row)
        else:
            row["base_close"] = round(base, 2)
            row["closes"] = [[str(d.date()), round(float(v), 2)] for d, v in during.items()]
            row["note"] = notes.get(item["symbol"], "")
            result["stocks"].append(row)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
