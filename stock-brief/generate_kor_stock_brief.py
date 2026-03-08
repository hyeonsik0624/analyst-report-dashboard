#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import List

KST = timezone(timedelta(hours=9))

FEEDS = [
    {"name": "매일경제 증권", "url": "https://www.mk.co.kr/rss/30100041/"},
    {"name": "뉴스1 경제", "url": "https://www.news1.kr/rss/economy.xml"},
    {"name": "뉴시스 속보", "url": "https://www.newsis.com/RSS/sokbo.xml"},
]

SECTIONS = {
    "지수/수급": ["코스피", "코스닥", "선물", "옵션", "외국인", "기관", "수급", "공매도", "프로그램매매"],
    "반도체/AI": ["반도체", "삼성전자", "SK하이닉스", "HBM", "엔비디아", "AI"],
    "2차전지/소재": ["2차전지", "배터리", "양극재", "음극재", "리튬", "에코프로", "포스코퓨처엠"],
    "자동차/조선/방산": ["현대차", "기아", "조선", "LNG선", "방산", "한화에어로", "K-방산"],
    "바이오/헬스케어": ["바이오", "헬스케어", "신약", "임상", "제약"],
    "정책/매크로": ["금리", "인플레이션", "물가", "환율", "한국은행", "연준", "FOMC", "수출", "관세", "예산", "정책"],
    "원자재/에너지": ["유가", "천연가스", "원자재", "구리", "금", "OPEC"],
    "일정/공시": ["실적", "가이던스", "공시", "IPO", "유상증자", "자사주", "배당"],
}


@dataclass
class Item:
    title: str
    link: str
    source: str
    published: datetime | None


def fetch(url: str, timeout: int = 12) -> bytes:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 OpenClaw Stock Brief"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def parse_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    # try RFC822
    try:
        dt = parsedate_to_datetime(text)
        if dt is not None:
            return dt.astimezone(KST)
    except Exception:
        pass
    # try ISO8601
    text2 = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except Exception:
        return None


def parse_rss(xml_bytes: bytes, source: str) -> List[Item]:
    items: List[Item] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items

    # RSS
    for it in root.findall('.//item'):
        title = (it.findtext('title') or '').strip()
        link = (it.findtext('link') or '').strip()
        pub = parse_dt(it.findtext('pubDate') or it.findtext('published') or it.findtext('dc:date'))
        if title and link:
            items.append(Item(title=title, link=link, source=source, published=pub))

    # Atom
    if not items:
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        for e in root.findall('.//a:entry', ns):
            title = (e.findtext('a:title', default='', namespaces=ns) or '').strip()
            link = ''
            link_el = e.find('a:link', ns)
            if link_el is not None:
                link = (link_el.attrib.get('href') or '').strip()
            pub = parse_dt(
                e.findtext('a:updated', default=None, namespaces=ns)
                or e.findtext('a:published', default=None, namespaces=ns)
            )
            if title and link:
                items.append(Item(title=title, link=link, source=source, published=pub))

    return items


def normalize_title(t: str) -> str:
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'\[[^\]]+\]', '', t)
    return t.strip().lower()


def categorize(title: str) -> list[str]:
    matched = []
    low = title.lower()
    for sec, kws in SECTIONS.items():
        if any(k.lower() in low for k in kws):
            matched.append(sec)
    return matched or ["기타 중요뉴스"]


def build_html(items: List[Item], out: Path):
    now = datetime.now(KST)
    since = now - timedelta(hours=18)

    unique = {}
    for x in items:
        key = normalize_title(x.title)
        if key not in unique:
            unique[key] = x
    dedup = sorted(unique.values(), key=lambda x: x.published or datetime(1970, 1, 1, tzinfo=KST), reverse=True)

    fresh = [x for x in dedup if (x.published is None or x.published >= since)]

    grouped = defaultdict(list)
    for x in fresh:
        for sec in categorize(x.title):
            grouped[sec].append(x)

    # cap each section
    for sec in list(grouped.keys()):
        grouped[sec] = grouped[sec][:10]

    section_order = list(SECTIONS.keys()) + ["기타 중요뉴스"]

    def fmt_dt(d: datetime | None) -> str:
        if not d:
            return "시간정보없음"
        return d.strftime('%m-%d %H:%M')

    sections_html = []
    total = 0
    for sec in section_order:
        arr = grouped.get(sec, [])
        if not arr:
            continue
        total += len(arr)
        lis = '\n'.join(
            f"<li><a href='{html.escape(i.link)}' target='_blank' rel='noopener'>{html.escape(i.title)}</a>"
            f" <span class='meta'>({html.escape(i.source)} · {fmt_dt(i.published)})</span></li>"
            for i in arr
        )
        sections_html.append(f"<section class='card'><h2>{sec}</h2><ul>{lis}</ul></section>")

    if not sections_html:
        sections_html = ["<section class='card'><h2>뉴스 없음</h2><p>최근 18시간 내 수집된 기사 없음.</p></section>"]

    html_doc = f"""<!doctype html>
<html lang='ko'>
<head>
<meta charset='utf-8'/>
<meta name='viewport' content='width=device-width, initial-scale=1'/>
<title>한국 주식 프리마켓 브리프</title>
<style>
:root {{ --bg:#0b1020; --card:#121a31; --text:#ecf1ff; --muted:#9db0ea; --accent:#7aa2ff; }}
body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px}}
.top{{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:flex-end}}
.badge{{background:rgba(122,162,255,.16);border:1px solid #3852a8;color:#bdd0ff;padding:4px 8px;border-radius:999px;font-size:.82rem}}
.card{{background:var(--card);border:1px solid #2c3f7a;border-radius:14px;padding:14px 16px;margin:12px 0}}
h1{{margin:.2rem 0 .4rem 0}} h2{{margin:.1rem 0 .6rem 0;font-size:1.05rem}}
ul{{margin:0;padding-left:18px}} li{{margin:7px 0;line-height:1.45}}
a{{color:#d9e5ff;text-decoration:none}} a:hover{{text-decoration:underline}}
.meta{{color:var(--muted);font-size:.88rem}}
.small{{font-size:.92rem;color:var(--muted)}}
hr{{border:none;border-top:1px solid #2c3f7a;margin:14px 0}}
</style>
</head>
<body>
<div class='wrap'>
  <div class='top'>
    <div>
      <h1>한국 주식 프리마켓 브리프</h1>
      <div class='small'>장 시작 전 체크용 자동 뉴스 큐레이션 (최근 18시간)</div>
    </div>
    <div class='badge'>업데이트: {now.strftime('%Y-%m-%d %H:%M KST')}</div>
  </div>

  <section class='card'>
    <strong>요약</strong>
    <div class='small'>총 {total}건 · 중복 제거 후 주요 섹터별 정리</div>
    <hr/>
    <div class='small'>※ 투자 판단은 본인 책임. 이 페이지는 정보 수집/정리 보조 도구입니다.</div>
  </section>

  {''.join(sections_html)}
</div>
</body>
</html>
"""

    out.write_text(html_doc, encoding='utf-8')


def main():
    out = Path('/Users/hyeonsik/.openclaw/workspace/stock-brief/index.html')
    items: List[Item] = []

    for f in FEEDS:
        try:
            x = fetch(f['url'])
            items.extend(parse_rss(x, f['name']))
        except Exception as e:
            print(f"[WARN] {f['name']} fetch failed: {e}", file=sys.stderr)

    build_html(items, out)
    print(out)


if __name__ == '__main__':
    main()
