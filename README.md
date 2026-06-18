# CPNS Watch Bot

Bot kecil untuk memantau info CPNS/CASN Indonesia dari sumber resmi seperti BKN, SSCASN, dan KemenPANRB. Output utamanya adalah laporan Markdown di `reports/latest.md`; opsional bisa kirim ringkasan ke Telegram atau Discord.

## Jalankan Lokal

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python run_cpns_watch.py
```

Untuk kirim notifikasi:

```powershell
$env:TELEGRAM_BOT_TOKEN="isi_token_bot"
$env:TELEGRAM_CHAT_ID="isi_chat_id"
python run_cpns_watch.py --notify
```

Atau pakai Discord:

```powershell
$env:DISCORD_WEBHOOK_URL="isi_webhook_discord"
python run_cpns_watch.py --notify
```

## Deploy Gratis Paling Praktis: GitHub Actions

1. Buat repository GitHub baru.
2. Upload semua file proyek ini.
3. Buka `Settings > Actions > General`, pastikan workflow boleh `Read and write permissions`.
4. Buka tab `Actions`, jalankan workflow `CPNS Watch` secara manual sekali.
5. Setelah itu workflow akan jalan tiap hari jam 08:00 WIB.

Kalau mau notifikasi, isi `Settings > Secrets and variables > Actions > New repository secret`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- atau email SMTP:
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_USERNAME`
- `EMAIL_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`
- `EMAIL_USE_TLS`
- atau `DISCORD_WEBHOOK_URL`

Untuk Gmail, biasanya `EMAIL_USERNAME` adalah alamat Gmail dan `EMAIL_PASSWORD` adalah App Password, bukan password login utama.

## Hugging Face

Hugging Face Spaces bisa gratis untuk app kecil, tetapi storage default-nya tidak permanen. Hugging Face Jobs mendukung schedule/cron, tetapi pada dokumentasi resmi terbaru Jobs tersedia untuk akun Pro, Team, atau Enterprise. Jadi untuk cron gratis, gunakan GitHub Actions dulu. Catatan HF ada di `docs/huggingface-jobs.md`.

## Sumber Resmi yang Dipantau

- BKN Berita
- BKN Pengumuman
- KemenPANRB CPNS
- KemenPANRB Berita Terkini
- SSCASN Portal
- SSCASN Formasi
- SSCASN FAQ
- SSCASN Buku Petunjuk

## Catatan Aman

Bot ini hanya memantau dan memberi laporan. Untuk apply CPNS, tetap lakukan sendiri di portal resmi SSCASN dan jangan kirim NIK, password, atau dokumen ke link yang tidak jelas.
