#!/usr/bin/env python3
from pathlib import Path
import re, html, json, argparse

TEMPLATE = Path('/Users/hyeonsik/.openclaw/workspace/templates/lecture_extra_high_template.html')

def _line_mode_sentences(raw: str):
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    endings = ('다', '요', '죠', '니다', '습니다', '됩니다', '했습니다', '있습니다', '하겠습니다', '보겠습니다')
    s, cur = [], ''
    for ln in lines:
        cur = (cur + ' ' + ln).strip() if cur else ln
        end_mark = cur.endswith(('.', '!', '?')) or any(cur.endswith(e) for e in endings)
        if end_mark:
            if not cur.endswith(('.', '!', '?')):
                cur += '.'
            s.append(cur)
            cur = ''
    if cur:
        if not cur.endswith(('.', '!', '?')):
            cur += '.'
        s.append(cur)
    return s


def to_paragraphs(text: str):
    words = len(re.findall(r'[가-힣]{2,}', text))

    # 전사 원문이 줄 단위(문장 조각)로 들어온 경우를 우선 처리
    line_count = len([ln for ln in text.splitlines() if ln.strip()])
    if line_count >= 30:
        s = _line_mode_sentences(text)
    else:
        flat = re.sub(r'\s+', ' ', text.strip())
        s = [x.strip() for x in re.split(r'(?<=[\.\!\?])\s+|(?<=다)\s+', flat) if x.strip()]
        if len(s) < 20:
            s = [x.strip() for x in re.split(r'(?<=[\.\!\?])\s+|\s+그리고\s+|\s+다음은\s+', flat) if x.strip()]

    # 너무 짧은 문장 조각 병합
    merged = []
    for x in s:
        if merged and len(x) < 18:
            merged[-1] = (merged[-1].rstrip(' .') + ' ' + x).strip()
        else:
            merged.append(x)

    paras = [' '.join(merged[i:i+3]) for i in range(0, len(merged), 3)]
    return paras, words

def build(src: Path, out: Path, heading: str, notes_key: str, quiz_data: list):
    template = TEMPLATE.read_text(encoding='utf-8')
    text = src.read_text(encoding='utf-8')
    paras, words = to_paragraphs(text)
    paras_html = '\n'.join(f'<p class="para">{html.escape(p)}</p>' for p in paras)
    minutes = max(1, round(words / 300))
    meta = f'예상 학습시간 {minutes}분 · 문단 {len(paras)}개 · 자동 학습도구 포함(검색/하이라이트/셀프퀴즈/메모저장)'

    doc = (template
      .replace('{{TITLE}}', heading)
      .replace('{{HEADING}}', heading)
      .replace('{{META}}', meta)
      .replace('{{PARAGRAPHS}}', paras_html)
      .replace('{{NOTES_KEY}}', notes_key)
      .replace('{{QUIZ_DATA}}', json.dumps(quiz_data, ensure_ascii=False)))
    out.write_text(doc, encoding='utf-8')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--heading', required=True)
    ap.add_argument('--notes-key', required=True)
    ap.add_argument('--quiz-json', default='[]', help='JSON array string')
    args = ap.parse_args()
    build(Path(args.src), Path(args.out), args.heading, args.notes_key, json.loads(args.quiz_json))
    print(args.out)
