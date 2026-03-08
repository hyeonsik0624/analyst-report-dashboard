#!/usr/bin/env python3
from pathlib import Path
import re, html, json, argparse

TEMPLATE = Path('/Users/hyeonsik/.openclaw/workspace/templates/lecture_extra_high_template.html')

def to_paragraphs(text: str):
    text = re.sub(r'\s+', ' ', text.strip())
    s = [x.strip() for x in re.split(r'(?<=[\.\!\?])\s+|(?<=다)\s+', text) if x.strip()]
    if len(s) < 20:
        s = [x.strip() for x in re.split(r'(?<=[\.\!\?])\s+|\s+그리고\s+|\s+다음은\s+', text) if x.strip()]
    return [' '.join(s[i:i+4]) for i in range(0, len(s), 4)], len(re.findall(r'[가-힣]{2,}', text))

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
