# 📚 Kitobxon Club — Telegram Bot

Kitobxon Club Telegram boti kitobxonlar uchun elektron kitoblar (PDF/EPUB), janrlar, audio kitoblar, mutolaa reytinglari va viktorinalarni o'z ichiga olgan zamonaviy bot hisoblanadi.

---

## 🚀 Serverga o'rnatish va ishga tushirish (Linux / Ubuntu VPS)

### 1. Repozitoriyni klonlash yoki serverga yuklash
```bash
git clone <Sizning-Github-Repo-Manzilingiz>
cd "Kitobxon Club"
```

### 2. Python muhitini o'rnatish
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. `.env` faylini sozlash
`.env.example` faylidan nusxa olib `.env` yarating:
```bash
cp .env.example .env
nano .env
```
Kerakli qiymatlarni kiriting:
```ini
BOT_TOKEN=8860313727:AAE_YmmXzWcXwGF-DKvuK7yC2Op67YLt-HM
ADMIN_ID=6956456422
DB_PATH=data/kitobxon.db
```

### 4. 24/7 rejimda ishga tushirish (Systemd Service)
Bot server qayta yuklanganda (reboot) ham avtomatik ishlab turishi uchun:

```bash
sudo cp kitobxon_bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kitobxon_bot
sudo systemctl start kitobxon_bot
```

Holatni tekshirish:
```bash
sudo systemctl status kitobxon_bot
```

Loglarni kuzatish:
```bash
journalctl -u kitobxon_bot -f
```
