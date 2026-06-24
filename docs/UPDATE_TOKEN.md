# Cara Update Token Stockbit

Lakukan ini setiap kali ada notif di Telegram:
> ⚠️ Token Stockbit EXPIRED! Data broker hari ini tidak berhasil diambil.

---

## Langkah-langkah

### 1. Ambil Token Baru dari Browser

1. Buka [stockbit.com](https://stockbit.com) → Login
2. Tekan **F12** → pilih tab **Network**
3. Ketik `exodus` di kolom filter/search
4. Klik salah satu request yang muncul (misal ke `exodus.stockbit.com/...`)
5. Pilih tab **Headers** → cari baris `Authorization`
6. Copy nilai token — bentuknya: `Bearer eyJhbGci...` (panjang, ratusan karakter)
7. **Ambil bagian setelah kata `Bearer ` saja** (jangan ikut kata Bearer-nya)

---

### 2. Update Token di VM

Buka terminal/SSH ke VM, lalu jalankan:

```bash
nano /home/anugrahdwikiar/bandarflow-bot/.env
```

Cari baris:
```
STOCKBIT_TOKEN=eyJhbGci...
```

Ganti nilai lama dengan token baru. Tekan **Ctrl+X** → **Y** → **Enter** untuk simpan.

---

### 3. Verifikasi (Opsional)

Jalankan test cepat untuk memastikan token baru valid:

```bash
cd /home/anugrahdwikiar/bandarflow-bot
./venv/bin/python -c "from scraper.stockbit_scraper import get_broker_summary; print(get_broker_summary('BBCA'))"
```

Kalau muncul data broker → token berhasil. Kalau muncul `[]` atau error 401 → ulangi langkah 1.

---

> Token Stockbit expire setiap ~24 jam. Update harus dilakukan setiap hari sebelum jam 18.30 WIB.
