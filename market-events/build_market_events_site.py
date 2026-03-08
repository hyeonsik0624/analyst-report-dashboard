#!/usr/bin/env python3
from __future__ import annotations
import re
import ssl
import json
import urllib.request
from datetime import datetime, timezone, timedelta, time
from pathlib import Path

KST = timezone(timedelta(hours=9))
UTC = timezone.utc

NASDAQ_EARNINGS_API = "https://api.nasdaq.com/api/calendar/earnings?date={date}"
NASDAQ_ECON_API = "https://api.nasdaq.com/api/calendar/economicevents?date={date}"

# YYYY-MM-DD 형식이면 주간 목록에 자동 포함
MANUAL_EVENTS = [
    {"date": "TBD", "title": "한미 정상회담", "tag": "정책", "note": "확정 시 외교/방산/환율 민감도 확대"},
]


def fetch_text(url: str) -> str:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def fetch_json(url: str) -> dict:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
        },
    )
    with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))


def parse_market_cap(s: str) -> int:
    if not s:
        return 0
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return int(float(s))
    except Exception:
        return 0


def weekday_kr(d):
    return ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]


def gmt_to_kst_label(base_date, gmt_str: str) -> tuple:
    s = (gmt_str or "").strip()
    if not re.match(r"^\d{1,2}:\d{2}$", s):
        return base_date, "시간 미정"
    hh, mm = map(int, s.split(':'))
    dt_utc = datetime.combine(base_date, time(hh, mm), tzinfo=UTC)
    dt_kst = dt_utc.astimezone(KST)
    return dt_kst.date(), dt_kst.strftime('%H:%M KST')


def earnings_time_label(raw: str) -> str:
    x = (raw or '').strip().lower()
    return {
        'time-before-market': '장전',
        'time-after-hours': '장후',
        'time-during-market': '장중',
    }.get(x, '시간 미정')


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
    earnings_by_day = {}
    weekly_events = []

    # 이번 주 미국 실적 발표(시총 큰 순) + 미국 핵심 매크로 이벤트 수집
    for i in range(7):
        d = today + timedelta(days=i)
        ds = d.strftime('%Y-%m-%d')

        # earnings
        try:
            obj = fetch_json(NASDAQ_EARNINGS_API.format(date=ds))
            rows = (obj.get('data') or {}).get('rows') or []
            rows_sorted = sorted(rows, key=lambda r: parse_market_cap(r.get('marketCap', '')), reverse=True)
            earnings_by_day[d] = rows_sorted[:6]
        except Exception as e:
            errs.append(f"실적 일정 수집 실패({ds}): {e}")
            earnings_by_day[d] = []

        # macro events
        try:
            eobj = fetch_json(NASDAQ_ECON_API.format(date=ds))
            erows = (eobj.get('data') or {}).get('rows') or []
            for r in erows:
                country = (r.get('country') or '').lower()
                name = (r.get('eventName') or '')
                low = name.lower()
                event_date, tlabel = gmt_to_kst_label(d, r.get('gmt', ''))
                if country not in ('united states', 'us', 'usa'):
                    continue
                if ('consumer price' in low) or (re.search(r'\bcpi\b', low)):
                    weekly_events.append((event_date, f"미국 {name}", "매크로", tlabel))
                elif ('producer price' in low) or (re.search(r'\bppi\b', low)):
                    weekly_events.append((event_date, f"미국 {name}", "매크로", tlabel))
                elif ('jolts' in low) or ('job openings' in low):
                    weekly_events.append((event_date, f"미국 {name}", "고용", tlabel))
                elif ('interest rate decision' in low) or ('fomc' in low) or ('fed' in low and 'rate' in low):
                    weekly_events.append((event_date, f"미국 {name}", "연준", tlabel))
        except Exception as e:
            errs.append(f"경제지표 수집 실패({ds}): {e}")

    # manual dated events
    for ev in MANUAL_EVENTS:
        ds = ev.get("date", "")
        if re.match(r"^20\d{2}-\d{2}-\d{2}$", ds):
            d = datetime.strptime(ds, "%Y-%m-%d").date()
            if today <= d <= week_end:
                weekly_events.append((d, ev["title"], ev.get("tag", "중요"), "시간 미정"))

    weekly_events.sort(key=lambda x: x[0])

    # top 3 points
    top_points = []
    if any(x[2] == "매크로" for x in weekly_events):
        top_points.append("미국 물가지표(CPI/PPI) 발표 주간")
    if any(x[2] == "연준" for x in weekly_events):
        top_points.append("연준(FOMC) 이벤트 체크 필요")
    if any(x[2] == "고용" for x in weekly_events):
        top_points.append("미국 고용(JOLTS) 지표 체크")
    top_points.append("미국 주요 기업 실적 발표 일정(장전/장후) 확인")
    while len(top_points) < 3:
        top_points.append("국내 공시(DART/KIND) 및 수급 변화 점검")
    top_points = top_points[:3]

    # '진짜 중요한 것'만: 중복 제거 + 핵심 이벤트명 압축
    important_tags = {"매크로", "연준", "정책", "고용"}
    raw_important = [(d, t, g, tm) for d, t, g, tm in weekly_events if g in important_tags]
    if not raw_important:
        raw_important = weekly_events[:5]

    def normalize_event_name(name: str) -> str:
        low = name.lower()
        if 'core cpi' in low:
            return '미국 Core CPI'
        if 'cpi' in low:
            return '미국 CPI'
        if 'core ppi' in low:
            return '미국 Core PPI'
        if 'ppi' in low:
            return '미국 PPI'
        if 'fomc' in low or 'interest rate decision' in low:
            return 'FOMC 금리결정'
        if 'jolts' in low or 'job openings' in low:
            return '미국 JOLTS 구인건수'
        return name

    seen = set()
    important_events = []
    for d, t, g, tm in sorted(raw_important, key=lambda x: x[0]):
        label = normalize_event_name(t)
        key = (d.isoformat(), label, g, tm)
        if key in seen:
            continue
        seen.add(key)
        important_events.append((d, label, g, tm))

    # FOMC가 연속 2일로 잡히면 1일차/결정일로 표시
    for i in range(len(important_events) - 1):
        d1, t1, g1, tm1 = important_events[i]
        d2, t2, g2, tm2 = important_events[i + 1]
        if g1 == '연준' and g2 == '연준' and t1 == 'FOMC 금리결정' and t2 == 'FOMC 금리결정' and (d2 - d1).days == 1:
            important_events[i] = (d1, 'FOMC 회의(1일차)', g1, tm1)
            important_events[i + 1] = (d2, 'FOMC 금리결정/기자회견', g2, tm2)

    # 너무 길면 상위 6개만
    important_events = important_events[:6]

    highlight_items = []
    for d, t, g, tm in important_events:
        highlight_items.append(
            f"<li class='highlight-item'><div class='hl-date'>{d.strftime('%m/%d')}({weekday_kr(d)})</div><div class='hl-main'>{t}<div class='hl-time'>{tm}</div></div><span class='tag'>{g}</span></li>"
        )
    highlights_html = ''.join(highlight_items) if highlight_items else "<li class='meta'>이번 주 확정된 초중요 이벤트 없음</li>"

    top_html = ''.join(f"<li>{p}</li>" for p in top_points)

    earnings_html_parts = []
    for i in range(7):
        d = today + timedelta(days=i)
        rows = earnings_by_day.get(d, [])
        if not rows:
            continue
        top = rows[:3]
        lis = ''.join(
            f"<li><strong>{r.get('symbol','')}</strong> {r.get('name','')} <span class='meta'>(예상EPS {r.get('epsForecast','-')} · {earnings_time_label(r.get('time',''))})</span></li>"
            for r in top
        )
        earnings_html_parts.append(f"<li><strong>{d.strftime('%m/%d')}({weekday_kr(d)})</strong><ul>{lis}</ul></li>")
    earnings_week_html = ''.join(earnings_html_parts) or "<li class='meta'>이번 주 수집된 미국 실적 일정 없음</li>"

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
.highlights{{list-style:none;padding-left:0}}
.highlights li{{margin:0}}
.tag{{background:#263a7a;border:1px solid #4f6fcb;color:#d8e4ff;padding:2px 8px;border-radius:999px;font-size:.76rem;white-space:nowrap}}
.highlight-item{{display:grid;grid-template-columns:62px 1fr auto;gap:10px;align-items:center;padding:10px 12px;margin:8px 0;border:1px solid #2f437f;border-radius:12px;background:linear-gradient(90deg, rgba(255,230,70,.16) 0 6px, rgba(255,255,255,.02) 6px 100%)}}
.hl-date{{font-weight:800;color:#ffe66b}}
.hl-main{{font-weight:600}}
.hl-time{{margin-top:3px;color:#9fb0e8;font-size:.84rem;font-weight:500}}
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
<ul class='highlights'>{highlights_html}</ul>
</section>

<section class='card'>
<h2>이번 주 미국 실적발표(시총 상위)</h2>
<ul>{earnings_week_html}</ul>
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
