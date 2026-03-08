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

# 필요 시 직접 추가/수정하는 중요 일정 (예: 한미정상회담, 대형 IPO, 기업 실적)
MANUAL_EVENTS = [
    {"date": "미정", "title": "한미 정상회담", "impact": "HIGH", "note": "확정 시 외교/방산/환율 민감도 확대 가능"},
    {"date": "매일", "title": "미국 주요 기업 실적 캘린더 확인", "impact": "HIGH", "note": "장 전/장 후 발표 시 국내 반도체·AI·2차전지 연동 체크"},
    {"date": "매일", "title": "국내 공시/실적 발표 확인(DART/KRX)", "impact": "HIGH", "note": "갭상승·갭하락 리스크 관리"},
]


def fetch_text(url: str) -> str:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_us_dates(text: str):
    # e.g., January 15, 2026
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"\b({months})\s+(\d{{1,2}}),\s*(20\d{{2}})\b")
    out = []
    for m in pat.finditer(text):
        s = m.group(0)
        try:
            d = datetime.strptime(s, "%B %d, %Y")
            out.append(d)
        except Exception:
            pass
    # dedup + sort
    uniq = sorted({d for d in out})
    return uniq


def parse_fomc_ranges(text: str):
    # e.g., January 27-28 or June 16-17
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    pat = re.compile(rf"\b({months})\s+(\d{{1,2}})(?:-(\d{{1,2}}))?\b")
    now = datetime.now()
    cur_year = now.year
    events = []
    for yr in [cur_year, cur_year + 1]:
        # 해당 연도 근처 텍스트만 쓰는 게 이상적이지만 단순 패턴으로 처리
        for m in pat.finditer(text):
            month, d1, d2 = m.group(1), m.group(2), m.group(3)
            try:
                start = datetime.strptime(f"{month} {int(d1)} {yr}", "%B %d %Y")
            except Exception:
                continue
            if start.year < cur_year - 1:
                continue
            label = f"{month} {d1}" + (f"-{d2}" if d2 else "")
            events.append((start, label))
    # dedup by label+date
    seen = set(); dedup=[]
    for d,l in sorted(events, key=lambda x:x[0]):
        k=(d,l)
        if k in seen: continue
        seen.add(k); dedup.append((d,l))
    # 가까운 미래 10개
    today = datetime.now().date()
    dedup = [x for x in dedup if x[0].date() >= today]
    return dedup[:10]


def build():
    now = datetime.now(KST)
    out = Path('/Users/hyeonsik/.openclaw/workspace/sites/market-events/index.html')

    cpi_dates = []
    ppi_dates = []
    fomc_dates = []
    errs = []

    try:
        cpi_dates = parse_us_dates(fetch_text(SOURCES['cpi']))
    except Exception as e:
        errs.append(f"CPI 수집 실패: {e}")
    try:
        ppi_dates = parse_us_dates(fetch_text(SOURCES['ppi']))
    except Exception as e:
        errs.append(f"PPI 수집 실패: {e}")
    try:
        fomc_dates = parse_fomc_ranges(fetch_text(SOURCES['fomc']))
    except Exception as e:
        errs.append(f"FOMC 수집 실패: {e}")

    today = datetime.now().date()
    cpi_upcoming = [d for d in cpi_dates if d.date() >= today][:8]
    ppi_upcoming = [d for d in ppi_dates if d.date() >= today][:8]

    def usfmt(d: datetime):
        return d.strftime('%Y-%m-%d')

    cpi_html = ''.join(f"<li>{usfmt(d)} <span class='tag'>CPI</span></li>" for d in cpi_upcoming) or "<li>수집된 일정 없음</li>"
    ppi_html = ''.join(f"<li>{usfmt(d)} <span class='tag'>PPI</span></li>" for d in ppi_upcoming) or "<li>수집된 일정 없음</li>"
    fomc_html = ''.join(f"<li>{d.strftime('%Y-%m-%d')} <span class='tag'>FOMC</span> ({label})</li>" for d,label in fomc_dates) or "<li>수집된 일정 없음</li>"

    manual_html = ''.join(
        f"<li><strong>{e['date']}</strong> · {e['title']} <span class='impact {e['impact'].lower()}'>{e['impact']}</span><br><span class='meta'>{e['note']}</span></li>"
        for e in MANUAL_EVENTS
    )

    warn_html = ''
    if errs:
        warn_html = "<section class='card warn'><h2>수집 경고</h2><ul>" + ''.join(f"<li>{x}</li>" for x in errs) + "</ul></section>"

    html = f"""<!doctype html>
<html lang='ko'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>핵심 일정 대시보드</title>
<style>
body{{margin:0;background:#0b1020;color:#edf2ff;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}}
.wrap{{max-width:1000px;margin:0 auto;padding:22px}}
.card{{background:#121a31;border:1px solid #2c3f7a;border-radius:14px;padding:14px 16px;margin:12px 0}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} @media(max-width:860px){{.grid{{grid-template-columns:1fr}}}}
h1,h2{{margin:.2rem 0 .6rem 0}} ul{{margin:0;padding-left:18px}} li{{margin:7px 0;line-height:1.45}}
.tag{{background:#334b99;border:1px solid #5673d4;color:#d8e4ff;padding:2px 7px;border-radius:999px;font-size:.78rem}}
.meta{{color:#9fb0e8;font-size:.9rem}} .impact{{padding:2px 6px;border-radius:6px;font-size:.75rem}}
.impact.high{{background:#5d1f2b;color:#ffd3d9;border:1px solid #a03f54}}
.warn{{border-color:#7d5f1f}}
a{{color:#d7e5ff}}
</style>
</head>
<body><div class='wrap'>
<h1>핵심 일정 대시보드</h1>
<div class='meta'>업데이트: {now.strftime('%Y-%m-%d %H:%M KST')} · 매매 전 체크용</div>

<section class='card'>
<h2>초중요 일정(직접 관리)</h2>
<ul>{manual_html}</ul>
<div class='meta'>※ 한미정상회담/대형 정책이벤트는 확정시 date를 실제 날짜로 갱신</div>
</section>

<div class='grid'>
  <section class='card'><h2>미국 물가 지표</h2><ul>{cpi_html}{ppi_html}</ul></section>
  <section class='card'><h2>연준 FOMC</h2><ul>{fomc_html}</ul></section>
</div>

<section class='card'>
<h2>실적발표/공시 바로가기</h2>
<ul>
<li><a target='_blank' rel='noopener' href='https://www.nasdaq.com/market-activity/earnings'>미국 Earnings Calendar (Nasdaq)</a></li>
<li><a target='_blank' rel='noopener' href='https://www.sec.gov/edgar/searchedgar/companysearch'>미국 SEC EDGAR 공시</a></li>
<li><a target='_blank' rel='noopener' href='https://dart.fss.or.kr/'>국내 DART 공시</a></li>
<li><a target='_blank' rel='noopener' href='https://kind.krx.co.kr/'>KRX KIND 공시/IPO</a></li>
<li><a target='_blank' rel='noopener' href='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'>FOMC 공식 캘린더</a></li>
<li><a target='_blank' rel='noopener' href='https://www.bls.gov/schedule/news_release/cpi.htm'>BLS CPI 일정</a></li>
<li><a target='_blank' rel='noopener' href='https://www.bls.gov/schedule/news_release/ppi.htm'>BLS PPI 일정</a></li>
</ul>
</section>

{warn_html}
</div></body></html>"""

    out.write_text(html, encoding='utf-8')
    print(out)


if __name__ == '__main__':
    build()
