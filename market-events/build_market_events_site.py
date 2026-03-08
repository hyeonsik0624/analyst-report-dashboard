#!/usr/bin/env python3
from __future__ import annotations
import re
import ssl
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))

SOURCES = {
    "fomc": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    "cpi": "https://www.bls.gov/schedule/news_release/cpi.htm",
    "ppi": "https://www.bls.gov/schedule/news_release/ppi.htm",
}

# YYYY-MM-DD 형식이면 주간 목록에 자동 포함
MANUAL_EVENTS = [
    {"date": "TBD", "title": "한미 정상회담", "tag": "정책", "note": "확정 시 외교/방산/환율 민감도 확대"},
]


def fetch_text(url: str) -> str:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_us_dates(text: str):
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"\b({months})\s+(\d{{1,2}}),\s*(20\d{{2}})\b")
    out = []
    for m in pat.finditer(text):
        s = m.group(0)
        try:
            out.append(datetime.strptime(s, "%B %d, %Y"))
        except Exception:
            pass
    return sorted({d for d in out})


def parse_fomc_dates(text: str):
    # e.g. January 27-28, 2026 -> start date only
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"\b({months})\s+(\d{{1,2}})(?:-\d{{1,2}})?,\s*(20\d{{2}})\b")
    out = []
    for m in pat.finditer(text):
        month, day, year = m.group(1), m.group(2), m.group(3)
        try:
            out.append(datetime.strptime(f"{month} {day}, {year}", "%B %d, %Y"))
        except Exception:
            pass
    return sorted({d for d in out})


def build():
    now = datetime.now(KST)
    today = now.date()
    week_end = today + timedelta(days=6)
    out = Path('/Users/hyeonsik/.openclaw/workspace/sites/market-events/index.html')

    errs = []
    cpi, ppi, fomc = [], [], []

    try:
        cpi = parse_us_dates(fetch_text(SOURCES['cpi']))
    except Exception as e:
        errs.append(f"CPI 수집 실패: {e}")
    try:
        ppi = parse_us_dates(fetch_text(SOURCES['ppi']))
    except Exception as e:
        errs.append(f"PPI 수집 실패: {e}")
    try:
        fomc = parse_fomc_dates(fetch_text(SOURCES['fomc']))
    except Exception as e:
        errs.append(f"FOMC 수집 실패: {e}")

    weekly_events = []
    for d in cpi:
        if today <= d.date() <= week_end:
            weekly_events.append((d.date(), "미국 CPI 발표", "매크로"))
    for d in ppi:
        if today <= d.date() <= week_end:
            weekly_events.append((d.date(), "미국 PPI 발표", "매크로"))
    for d in fomc:
        if today <= d.date() <= week_end:
            weekly_events.append((d.date(), "FOMC 금리결정/성명", "연준"))

    # manual dated events
    for ev in MANUAL_EVENTS:
        ds = ev.get("date", "")
        if re.match(r"^20\d{2}-\d{2}-\d{2}$", ds):
            d = datetime.strptime(ds, "%Y-%m-%d").date()
            if today <= d <= week_end:
                weekly_events.append((d, ev["title"], ev.get("tag", "중요")))

    weekly_events.sort(key=lambda x: x[0])

    # top 3 points
    top_points = []
    if any(x[2] == "매크로" for x in weekly_events):
        top_points.append("미국 물가지표(CPI/PPI) 발표 주간")
    if any(x[2] == "연준" for x in weekly_events):
        top_points.append("연준(FOMC) 이벤트 체크 필요")
    top_points.append("미국 주요 기업 실적 발표 일정(장전/장후) 확인")
    while len(top_points) < 3:
        top_points.append("국내 공시(DART/KIND) 및 수급 변화 점검")
    top_points = top_points[:3]

    # 형광펜 느낌으로 '진짜 중요한 것'만 추림
    important_tags = {"매크로", "연준", "정책"}
    important_events = [(d, t, g) for d, t, g in weekly_events if g in important_tags][:7]
    if not important_events:
        important_events = weekly_events[:5]

    highlight_items = []
    for d, t, g in important_events:
        highlight_items.append(
            f"<li class='highlight'><strong>{d.strftime('%m/%d')}</strong> · {t} <span class='tag'>{g}</span></li>"
        )
    highlights_html = ''.join(highlight_items) if highlight_items else "<li class='meta'>이번 주 확정된 초중요 이벤트 없음</li>"

    top_html = ''.join(f"<li>{p}</li>" for p in top_points)
    warn_html = ""
    if errs:
        warn_html = "<section class='card warn'><h2>수집 경고</h2><ul>" + ''.join(f"<li>{e}</li>" for e in errs) + "</ul></section>"

    html = f"""<!doctype html>
<html lang='ko'><head>
<meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>이번 주 핵심 일정</title>
<style>
body{{margin:0;background:#0b1020;color:#edf2ff;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}}
.wrap{{max-width:980px;margin:0 auto;padding:22px}}
.card{{background:#121a31;border:1px solid #2c3f7a;border-radius:14px;padding:14px 16px;margin:12px 0}}
h1,h2{{margin:.2rem 0 .6rem 0}} ul{{margin:0;padding-left:18px}} li{{margin:7px 0;line-height:1.45}}
.tag{{background:#334b99;border:1px solid #5673d4;color:#d8e4ff;padding:2px 7px;border-radius:999px;font-size:.78rem}}
.highlight{{background:linear-gradient(transparent 45%, rgba(255,235,59,.45) 45%); padding:2px 0}}
.meta{{color:#9fb0e8;font-size:.9rem}} .warn{{border-color:#7d5f1f}}
a{{color:#d7e5ff}}
</style></head>
<body><div class='wrap'>
<h1>이번 주 핵심 일정</h1>
<div class='meta'>업데이트: {now.strftime('%Y-%m-%d %H:%M KST')} · 기간: {today.strftime('%m/%d')} ~ {week_end.strftime('%m/%d')}</div>

<section class='card'>
<h2>이번 주 영향 포인트 3가지</h2>
<ul>{top_html}</ul>
</section>

<section class='card'>
<h2>이번 주 진짜 중요한 일정만</h2>
<ul>{highlights_html}</ul>
</section>

<section class='card'>
<h2>실적 발표 빠른 확인</h2>
<ul>
<li><a target='_blank' rel='noopener' href='https://www.nasdaq.com/market-activity/earnings'>미국 Earnings Calendar (Nasdaq)</a></li>
<li><a target='_blank' rel='noopener' href='https://dart.fss.or.kr/'>국내 DART 공시</a></li>
<li><a target='_blank' rel='noopener' href='https://kind.krx.co.kr/'>KRX KIND 공시/IPO</a></li>
</ul>
</section>

{warn_html}
</div></body></html>"""

    out.write_text(html, encoding='utf-8')
    print(out)


if __name__ == '__main__':
    build()
