"""
setup_stockbit.py — Script untuk setup dan verifikasi koneksi Stockbit.

Jalankan SETELAH mengisi STOCKBIT_TOKEN di .env:
    python setup_stockbit.py

Script ini akan:
1. Verifikasi token valid
2. Cari endpoint broker summary yang aktif
3. Test ambil data BBRI sebagai sample
4. Simpan endpoint yang ditemukan ke .env
"""

import json
import os
import sys
import io
import time
import requests
from datetime import datetime

# Fix encoding Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Load .env
from dotenv import load_dotenv
load_dotenv()

STOCKBIT_BASE = "https://exodus.stockbit.com"
TOKEN = os.getenv("STOCKBIT_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Origin": "https://stockbit.com",
    "Referer": "https://stockbit.com/",
    "x-requested-with": "XMLHttpRequest",
}

# Daftar endpoint yang akan dicoba
CANDIDATE_ENDPOINTS = [
    "/broker/summary/BBRI",
    "/broker/summary/BBRI?limit=50",
    "/v1/broker/summary/BBRI",
    "/v1/broker/summary?symbol=BBRI&limit=50",
    "/v2/broker/summary/BBRI",
    "/v2/broker/summary?symbol=BBRI",
    "/marketdata/v2/broker-summary/BBRI",
    "/marketdata/broker-summary/BBRI",
    "/stock/broker-summary/BBRI",
    "/stock/broker/summary?ticker=BBRI",
    "/stockbit/v2/broker/BBRI/summary",
    "/trade/broker-summary/BBRI",
    "/trade/v1/broker-summary?symbol=BBRI",
    "/idx/broker-summary?ticker=BBRI",
    "/api/broker/summary/BBRI",
    "/api/v1/broker-summary/BBRI",
]


def print_sep(char="-", n=60):
    print(char * n)


def check_token():
    print("\n[1] Cek token...")
    if not TOKEN or TOKEN == "YOUR_STOCKBIT_TOKEN_HERE":
        print("   [ERROR] STOCKBIT_TOKEN belum diisi!")
        print("   Buka .env dan isi dengan token dari stockbit.com")
        print("   Cara ambil: F12 -> Network -> request ke exodus.stockbit.com -> Header 'Authorization: Bearer eyJ...'")
        return False

    if not TOKEN.startswith("eyJ"):
        print(f"   [WARNING] Token tidak dimulai dengan 'eyJ'. Apakah ini JWT yang benar?")
        print(f"   Token (10 char pertama): {TOKEN[:10]}...")
    else:
        print(f"   Token OK (eyJ... {len(TOKEN)} karakter)")

    # Cek expiry dari JWT payload
    try:
        import base64
        parts = TOKEN.split(".")
        if len(parts) == 3:
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = json.loads(base64.b64decode(payload))
            if "exp" in decoded:
                exp_dt = datetime.fromtimestamp(decoded["exp"])
                now = datetime.now()
                if exp_dt < now:
                    print(f"   [ERROR] Token sudah EXPIRED sejak {exp_dt.strftime('%Y-%m-%d %H:%M')}")
                    print("   Silakan ambil token baru dari stockbit.com")
                    return False
                else:
                    hours_left = (exp_dt - now).total_seconds() / 3600
                    print(f"   Token berlaku hingga: {exp_dt.strftime('%Y-%m-%d %H:%M')} ({hours_left:.1f} jam lagi)")
    except Exception:
        print("   (Tidak bisa decode JWT, lanjut...)")

    return True


def find_working_endpoint():
    print("\n[2] Mencari endpoint broker summary yang aktif...")
    print(f"    Testing {len(CANDIDATE_ENDPOINTS)} endpoint ke {STOCKBIT_BASE}...")
    print()

    found_endpoints = []

    for ep in CANDIDATE_ENDPOINTS:
        url = STOCKBIT_BASE + ep
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            status = resp.status_code

            if status == 401:
                print(f"   [401] Token ditolak! Token expired atau salah.")
                return None
            elif status == 200:
                try:
                    data = resp.json()
                    text_preview = json.dumps(data)[:120]
                    print(f"   [200] {ep}")
                    print(f"         {text_preview}")

                    # Cek apakah ada data broker
                    broker_data = extract_brokers(data)
                    if broker_data:
                        print(f"         => {len(broker_data)} broker rows DITEMUKAN!")
                        found_endpoints.append((ep, broker_data))
                    else:
                        print(f"         => 200 OK tapi tidak ada data broker")
                except Exception:
                    print(f"   [200] {ep} => non-JSON response")
            elif status == 404:
                print(f"   [404] {ep}")
            elif status == 403:
                print(f"   [403] {ep} => Forbidden")
            elif status == 429:
                print(f"   [429] Rate limited! Tunggu 10 detik...")
                time.sleep(10)
            else:
                print(f"   [{status}] {ep}")

        except requests.RequestException as e:
            print(f"   [ERR] {ep}: {e}")

        time.sleep(0.3)  # Jangan spam

    return found_endpoints


def extract_brokers(data):
    rows = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in ["data", "result", "brokers", "broker_summary", "items", "records", "list"]:
            if key in data and isinstance(data[key], list):
                rows = data[key]
                break
        if not rows and "data" in data and isinstance(data["data"], dict):
            inner = data["data"]
            for key in ["brokers", "broker_summary", "items", "records", "list"]:
                if key in inner and isinstance(inner[key], list):
                    rows = inner[key]
                    break
    return [r for r in rows if isinstance(r, dict) and len(r) > 1]


def show_sample_data(endpoint, broker_data):
    print("\n[3] Sample data broker (5 baris pertama):")
    print_sep()
    for i, row in enumerate(broker_data[:5], 1):
        print(f"   {i}. {json.dumps(row, ensure_ascii=False)}")
    print_sep()

    # Tunjukkan key yang ada
    if broker_data:
        keys = list(broker_data[0].keys())
        print(f"\n   Keys yang tersedia: {keys}")

        # Coba identifikasi field yang relevan
        sample = broker_data[0]
        for key in keys:
            val = sample[key]
            if isinstance(val, (int, float)) and val != 0:
                print(f"   {key}: {val}")
            elif isinstance(val, str) and val:
                print(f"   {key}: '{val}'")


def save_endpoint_to_env(endpoint):
    """Simpan endpoint yang berhasil ke .env."""
    env_path = ".env"

    if not os.path.exists(env_path):
        print("\n   .env tidak ditemukan, lewati penyimpanan endpoint.")
        return

    with open(env_path, "r") as f:
        content = f.read()

    entry = f"\nSTOCKBIT_BROKER_ENDPOINT={endpoint}\n"
    if "STOCKBIT_BROKER_ENDPOINT" in content:
        import re
        content = re.sub(r"STOCKBIT_BROKER_ENDPOINT=.*", f"STOCKBIT_BROKER_ENDPOINT={endpoint}", content)
    else:
        content += entry

    with open(env_path, "w") as f:
        f.write(content)

    print(f"\n   Endpoint disimpan ke .env: STOCKBIT_BROKER_ENDPOINT={endpoint}")


def main():
    print_sep("=")
    print("  SETUP STOCKBIT — IDX Bandarmology Bot")
    print_sep("=")

    # Step 1: Cek token
    if not check_token():
        print("\n[!] Setup gagal. Isi STOCKBIT_TOKEN dulu di .env lalu jalankan ulang.")
        sys.exit(1)

    # Step 2: Cari endpoint
    found = find_working_endpoint()

    if not found:
        print("\n[!] Tidak ada endpoint yang berhasil.")
        print()
        print("Kemungkinan penyebab:")
        print("  1. Token expired -> ambil token baru dari stockbit.com")
        print("  2. Endpoint Stockbit berubah -> inspect Network di browser:")
        print("     - Buka stockbit.com/BBRI")
        print("     - F12 -> Network -> filter 'XHR'")
        print("     - Cari request yang return data broker")
        print("     - Copy URL endpoint tersebut")
        print()
        print("Hubungi developer untuk update CANDIDATE_ENDPOINTS di setup_stockbit.py")
        sys.exit(1)

    # Step 3: Tampilkan hasil
    best_endpoint, broker_data = found[0]
    print(f"\n[OK] Endpoint aktif ditemukan: {best_endpoint}")
    show_sample_data(best_endpoint, broker_data)

    # Step 4: Update config stockbit_scraper.py
    save_endpoint_to_env(best_endpoint)

    print("\n")
    print_sep("=")
    print("  Setup BERHASIL!")
    print(f"  Endpoint: {best_endpoint}")
    print(f"  Sample data: {len(broker_data)} broker rows untuk BBRI")
    print()
    print("  Selanjutnya:")
    print("  > python test_local.py   (test dengan LQ45)")
    print_sep("=")


if __name__ == "__main__":
    main()
