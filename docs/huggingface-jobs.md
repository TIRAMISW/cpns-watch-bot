# Deploy CPNS Watch ke Hugging Face

Catatan penting: Hugging Face Jobs mendukung schedule/cron, tetapi dokumentasi resmi terbaru menyebut Jobs hanya tersedia untuk akun Pro, Team, atau Enterprise. Jadi ini bukan jalur cron gratis yang paling aman. Untuk gratis, gunakan GitHub Actions di `README.md`.

Hugging Face masih berguna kalau kamu ingin:

- membuat Space UI sederhana untuk tombol "cek sekarang";
- menyimpan model atau dataset pendukung;
- menjalankan scheduled Jobs kalau akun HF kamu sudah Pro/Team/Enterprise.

## Opsi A: Space UI Gratis

Buat Space Python/Gradio yang menjalankan `run_cpns_watch.py` saat tombol diklik. Simpan hasil penting ke GitHub, Telegram, Discord, atau dataset terpisah karena disk Space default tidak permanen.

## Opsi B: Scheduled Jobs Jika Akun Mendukung

1. Login Hugging Face CLI:

```bash
pip install -U "huggingface_hub[cli]"
hf auth login
```

2. Schedule job harian jam 07:15 WIB. Karena cron memakai UTC, gunakan `15 0 * * *`.

```bash
hf jobs scheduled uv run "15 0 * * *" python run_cpns_watch.py --notify
```

Untuk deployment yang benar-benar tahan restart, tetap simpan hasil keluar dari runtime HF, misalnya ke GitHub atau Telegram/Discord.

## Jalankan Manual

```bash
hf jobs uv run python run_cpns_watch.py
```

## Secrets

Kalau ingin notifikasi, tambahkan secret atau environment variable berikut di job/space:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `DISCORD_WEBHOOK_URL`

## Rekomendasi

Pakai GitHub Actions sebagai cron gratis utama. Pakai Hugging Face nanti kalau kamu butuh halaman UI publik atau akunmu sudah mendukung scheduled Jobs.
