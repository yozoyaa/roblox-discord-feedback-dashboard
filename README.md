# Roblox Discord Feedback Dashboard

Web app Flask untuk mengelola feedback/rating dari Discord, lalu menjalankan pipeline analisis sentimen (Naive Bayes + TF-IDF).

## Setup singkat
1. Buat venv lalu aktifkan:
   - Windows: `python -m venv .venv && .venv\Scripts\activate`
   - Linux/macOS: `python3 -m venv .venv && source .venv/bin/activate`
2. Install dependency: `pip install -r requirements.txt`
3. Jalankan aplikasi: `python -m src.app`

## Alur cepat
- Crawling -> Validation -> Labeling -> Split Data -> Preprocessing -> TF-IDF
- Semua output disimpan per sesi di `data/sessions/<sid>/outputs`.
