# PDF Translator (MVP)

간단한 로컬 PDF 번역기입니다.

## 기능
- PDF 업로드
- 원문 언어 / 번역 언어 선택
- 페이지별 텍스트 번역
- 원문 이미지(그래프 등) 포함 HTML 결과 생성
- 결과 파일 다운로드

## 실행
```bash
cd pdf-translator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

브라우저에서 `http://127.0.0.1:8080` 접속

## 주의
- 번역은 GoogleTranslator(deep-translator) 기반 자동 번역입니다.
- 레이아웃 100% 동일한 PDF 재조판이 아니라, 읽기 좋은 HTML 결과를 우선 제공하는 MVP입니다.
- 큰 PDF는 번역 시간이 걸릴 수 있습니다.
