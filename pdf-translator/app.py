import os
import re
import time
import uuid
import html
from pathlib import Path

import fitz  # PyMuPDF
from deep_translator import GoogleTranslator
from flask import Flask, render_template, request, send_file, redirect, url_for, flash

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
ASSET_DIR = OUTPUT_DIR / "assets"

for d in [UPLOAD_DIR, OUTPUT_DIR, ASSET_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("PDF_TRANSLATOR_SECRET", "local-dev-secret")


def normalize_text(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def should_translate(text: str) -> bool:
    if not text:
        return False
    if re.fullmatch(r"[\W_]+", text):
        return False
    alpha_count = sum(ch.isalpha() for ch in text)
    return alpha_count >= 2 or len(text) > 6


def translate_pdf_to_html(pdf_path: Path, source_lang: str, target_lang: str) -> Path:
    run_id = uuid.uuid4().hex[:10]
    run_asset_dir = ASSET_DIR / run_id
    run_asset_dir.mkdir(parents=True, exist_ok=True)

    translator = GoogleTranslator(source=source_lang, target=target_lang)
    cache = {}

    doc = fitz.open(str(pdf_path))
    pages = []

    for i, page in enumerate(doc, start=1):
        raw = page.get_text("text")
        paras = [normalize_text(x) for x in re.split(r"\n\s*\n+", raw) if normalize_text(x)]

        translated_paras = []
        for para in paras:
            if not should_translate(para):
                continue
            if re.match(r"^\d+\s*\|", para):
                # 보통 페이지 헤더 형태는 스킵
                continue

            if para in cache:
                translated = cache[para]
            else:
                try:
                    translated = translator.translate(para)
                except Exception:
                    translated = para
                cache[para] = translated
                time.sleep(0.05)

            translated_paras.append(translated)

        # 이미지 추출
        img_rel_paths = []
        for j, info in enumerate(page.get_images(full=True), start=1):
            xref = info[0]
            pix = fitz.Pixmap(doc, xref)
            if pix.n - pix.alpha >= 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            name = f"p{i:02d}_img{j:02d}.png"
            out_path = run_asset_dir / name
            pix.save(str(out_path))
            img_rel_paths.append(f"assets/{run_id}/{name}")

        pages.append((translated_paras, img_rel_paths))

    title = f"Translated PDF ({pdf_path.name})"

    html_parts = []
    html_parts.append('<!doctype html><html lang="ko"><head><meta charset="utf-8"/>')
    html_parts.append('<meta name="viewport" content="width=device-width, initial-scale=1"/>')
    html_parts.append(f"<title>{html.escape(title)}</title>")
    html_parts.append('''
<style>
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;background:#0b0f17;color:#edf2ff;line-height:1.7}
.wrap{max-width:980px;margin:0 auto;padding:24px 16px 60px}
header{position:sticky;top:0;background:rgba(11,15,23,.92);backdrop-filter:blur(6px);padding:10px 0;border-bottom:1px solid #222a3d;margin-bottom:16px}
h1{font-size:24px;margin:0}
.sub{color:#a7b3d1;margin-top:4px;font-size:13px}
.page{background:#12192a;border:1px solid #28324c;border-radius:12px;padding:16px;margin:12px 0}
.page h2{margin:0 0 10px;font-size:17px;color:#9cc0ff}
p{margin:0 0 10px;font-size:15px;white-space:pre-wrap}
.fig{margin:10px 0 16px;background:#0f1627;border:1px solid #2b3859;border-radius:10px;padding:8px}
.fig img{width:100%;height:auto;border-radius:6px;background:white}
.figcap{font-size:12px;color:#9eb1da;margin-top:5px}
small{color:#90a0c5}
</style>
</head><body><div class="wrap">''')
    html_parts.append(f'<header><h1>{html.escape(title)}</h1><div class="sub">자동 번역 결과 · source={source_lang}, target={target_lang}</div></header>')
    html_parts.append('<small>※ 자동 번역 초안입니다. 중요한 수치/용어는 원문 PDF와 교차 확인하세요.</small>')

    for i, (paras, img_paths) in enumerate(pages, start=1):
        html_parts.append(f'<section class="page"><h2>페이지 {i}</h2>')
        for para in paras:
            html_parts.append(f"<p>{html.escape(para)}</p>")
        for k, ip in enumerate(img_paths, start=1):
            html_parts.append('<figure class="fig">')
            html_parts.append(f'<img src="{ip}" alt="페이지 {i} 이미지 {k}" loading="lazy"/>')
            html_parts.append(f'<figcaption class="figcap">원문 이미지 · p.{i}-{k}</figcaption>')
            html_parts.append('</figure>')
        html_parts.append('</section>')

    html_parts.append('</div></body></html>')

    out_html = OUTPUT_DIR / f"translated_{run_id}.html"
    out_html.write_text("".join(html_parts), encoding="utf-8")
    return out_html


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/translate", methods=["POST"])
def translate():
    if "pdf" not in request.files:
        flash("PDF 파일을 업로드해 주세요.")
        return redirect(url_for("index"))

    file = request.files["pdf"]
    if not file.filename.lower().endswith(".pdf"):
        flash("PDF 파일만 업로드할 수 있어요.")
        return redirect(url_for("index"))

    source_lang = request.form.get("source_lang", "en")
    target_lang = request.form.get("target_lang", "ko")

    temp_name = f"{uuid.uuid4().hex}.pdf"
    pdf_path = UPLOAD_DIR / temp_name
    file.save(str(pdf_path))

    try:
        out_html = translate_pdf_to_html(pdf_path, source_lang, target_lang)
    except Exception as e:
        flash(f"번역 중 오류가 발생했어요: {e}")
        return redirect(url_for("index"))

    return redirect(url_for("result", name=out_html.name))


@app.route("/result/<name>", methods=["GET"])
def result(name):
    file_path = OUTPUT_DIR / name
    if not file_path.exists():
        flash("결과 파일을 찾을 수 없습니다.")
        return redirect(url_for("index"))
    return send_file(str(file_path))


@app.route('/outputs/assets/<run_id>/<filename>')
def output_asset(run_id, filename):
    asset_file = ASSET_DIR / run_id / filename
    if not asset_file.exists():
        return "Not Found", 404
    return send_file(str(asset_file))


# HTML 내부 상대 경로를 위해 간단한 static-like route
@app.route('/assets/<run_id>/<filename>')
def asset_alias(run_id, filename):
    return output_asset(run_id, filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
