# KKP Sentiment Dashboard

Web application untuk proyek KKP:  
**Analisis Sentimen Ulasan Game Roblox Cabin Indo menggunakan Naive Bayes dan ekstraksi fitur TF-IDF (implementasi manual).**

## Features (WIP)
- Dashboard statistik (jumlah data, vocabulary, distribusi kategori)
- Import/Crawling data (via UI)
- Preprocessing teks
- TF-IDF manual
- Naive Bayes manual
- Evaluasi (accuracy, precision, recall, f1)

## Tech
- Python + Flask (UI/Server)
- HTML/CSS/JS (Bootstrap untuk tampilan)

## Setup (Local)
```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/app.py
