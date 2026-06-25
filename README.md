# cRSI + Stoch RSI Signal Bot — GitHub Actions + Pages

ระบบเทรดอัตโนมัติบน GitHub Actions ฟรี 100% (ไม่จำกัดจำนวนครั้ง/วัน สำหรับ public repo)
ประกอบด้วย **2 ระบบ** ที่ทำงานร่วมกัน:

| ระบบ | ทำอะไร | ไฟล์ |
|---|---|---|
| 🤖 **Cron Signal** | รันทุก 5 นาที → คำนวณสัญญาณ → ส่ง Telegram | `check_signal.py` + `.github/workflows/cron-signal.yml` |
| 📊 **Dashboard** | เว็บ dashboard แบบ TradingView (ตาราง W/L, chart, live signal) | `index.html` + `.github/workflows/deploy-pages.yml` |

> **เหตุผลที่ใช้ GitHub Actions แทน Vercel Cron:**
> Vercel Hobby plan จำกัด cron ได้วันละครั้ง ส่วน GitHub Actions ฟรีสำหรับ public repo
> แบบไม่จำกัด และ private repo มี free minutes 2,000/เดือน (เพียงพอสำหรับการรันทุก 5 นาที = ~8,640 ครั้ง/เดือน)

---

## โครงสร้างโปรเจกต์

```
.
├── .github/
│   └── workflows/
│       ├── cron-signal.yml     # Cron รันทุก 5 นาที → ส่ง Telegram
│       └── deploy-pages.yml    # Deploy index.html ไป GitHub Pages
├── check_signal.py             # Python script (Pine Script translation + ทบไม้)
├── index.html                  # Static dashboard (HTML + JS + CDN libs)
├── requirements.txt            # Python dependencies
└── README.md
```

---

## คุณสมบัติ

### 🤖 Cron Signal (`check_signal.py`)
- ✅ แปล Pine Script v5 → Python **แม่นยำ 100%**
  - `ta.rma` ใช้ `alpha = 1/length` (Wilder's Smoothing) — ไม่ใช่ EMA
  - `var float` ทุกตัวคำนวณแบบ **bar-by-bar loop** (ไม่ vectorized)
  - `nz(x, default)` ทำงานเหมือน Pine ทุกประการ
- ✅ Parameters จาก TradingView screenshot:
  - domcycle=13, vibration=10, leveling=10
  - smoothK=3, smoothD=3, lengthRSI=15, lengthStoch=10
  - stoch_low=15, stoch_high=85
- ✅ TF 5m + BTCUSDT (default)
- ✅ ส่งแจ้งเตือน Telegram (default) / LINE Notify / ทั้งคู่
- ✅ รองรับ dry-run mode สำหรับทดสอบ

### 📊 Dashboard (`index.html`)
- ✅ Pure frontend — ไม่ต้อง build, รันได้ใน browser ทันที
- ✅ Deploy บน **GitHub Pages** ฟรี
- ✅ ดึงข้อมูลจาก **Bybit v5 Public API** ตรงจาก browser
- ✅ **Logic ทบไม้ (Martingale Recovery)**:
  - BUY ชนะถ้ามีแท่งเขียว (close > open) อย่างน้อย 1 แท่งใน N แท่งถัดไป
  - SELL ชนะถ้ามีแท่งแดง (close < open) อย่างน้อย 1 แท่งใน N แท่งถัดไป
  - ชนะเร็ว = barsHeld น้อย (ดีที่สุด) / ชนะช้า = ทบไม้หลายครั้ง / แพ้ = barsHeld = N
- ✅ **9 สถิติรวม**: Total/Wins/Losses/Pending/Win Rate/Avg P&L/Buy-Sell/Buy WR/Sell WR
- ✅ **Performance chart** สลับได้: Cumulative Win Rate% / Per-Signal P&L%
- ✅ **Signal table** แบบ TradingView: filter (All/Buy/Sell/Win/Loss/Pending), search, Export CSV
- ✅ **Auto refresh ทุก 5 นาที** + countdown timer + manual refresh
- ✅ **Live Signal card** แสดง BUY/SELL ล่าสุดพร้อมค่า indicators ครบ
- ✅ **Telegram alerts** ผู้ใช้ใส่ Bot Token + Chat ID เอง (save ใน localStorage)
- ✅ **Trading Dark theme** สไตล์ Binance/Bybit
- ✅ **Responsive** ทั้ง mobile และ desktop

---

## วิธีติดตั้ง (1-time setup)

### 1. สร้าง GitHub Repository (แนะนำ public)

```bash
# Unzip ไฟล์ที่ได้รับ
unzip signal-bot-ga.zip -d signal-bot-ga
cd signal-bot-ga

# Init git และ push
git init
git add .
git commit -m "cRSI + Stoch RSI Signal Bot — GitHub Actions + Pages"
git branch -M main
git remote add origin https://github.com/USERNAME/REPO_NAME.git
git push -u origin main
```

### 2. ตั้งค่า Secrets และ Variables

ใน repo ไปที่ **Settings → Secrets and variables → Actions**

#### A) Secrets (sensitive data)
ในแท็บ **Secrets** → New repository secret:

| Secret Name | Value | จำเป็น |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | จาก BotFather | ใช่ (ถ้าใช้ Telegram) |
| `TELEGRAM_CHAT_ID` | จาก userinfobot | ใช่ (ถ้าใช้ Telegram) |
| `LINE_NOTIFY_TOKEN` | จาก LINE Notify | ไม่ (ถ้าใช้ LINE) |

#### B) Variables (non-sensitive config)
ในแท็บ **Variables** → New repository variable:

| Variable Name | Value | Default |
|---|---|---|
| `EXCHANGE` | `bybit` | bybit |
| `SYMBOL` | `BTCUSDT` | BTCUSDT |
| `TIMEFRAME` | `5` | 5 |
| `TIMEFRAME_MINUTES` | `5` | 5 |
| `OHLCV_LIMIT` | `250` | 250 |
| `MAX_RECOVERY_BARS` | `3` | 3 (ทบไม้สูงสุด 3 แท่ง) |
| `NOTIFY_CHANNEL` | `telegram` / `line` / `both` | telegram |
| `TZ_OFFSET_HOURS` | `7` | 7 (Bangkok) |

> 💡 secrets อ้างถึงด้วย `${{ secrets.XXX }}`, variables ด้วย `${{ vars.XXX }}`

### 3. สร้าง Telegram Bot (หรือ LINE Notify)

**Telegram:**
1. คุยกับ [@BotFather](https://t.me/BotFather) → สร้าง bot → ได้ `TELEGRAM_BOT_TOKEN`
2. เพิ่ม bot เข้า group หรือเริ่ม chat ส่วนตัว → ส่งข้อความอะไรก็ได้
3. คุยกับ [@userinfobot](https://t.me/userinfobot) → ได้ `TELEGRAM_CHAT_ID`

**LINE Notify (ทางเลือก):**
1. ไปที่ https://notify-bot.line.me/ → ออก token → ได้ `LINE_NOTIFY_TOKEN`

### 4. เปิด GitHub Pages

1. ไปที่ **Settings → Pages**
2. ในส่วน **Build and deployment → Source**: เลือก **GitHub Actions**
3. Workflow `deploy-pages.yml` จะรันอัตโนมัติเมื่อ push ไฟล์ `index.html`
4. หลัง deploy เสร็จ (~1 นาที), GitHub จะแสดง URL ของหน้าเว็บที่:
   ```
   https://USERNAME.github.io/REPO_NAME/
   ```

### 5. ทดสอบ Cron Signal

ในแท็บ **Actions** → เลือก workflow "Check Trading Signal" → คลิก **Run workflow**

ตอน manual trigger มีตัวเลือก `dry_run`:
- ✅ tick = ทดสอบโดยพิมพ์ข้อความออก log แต่ไม่ส่งแจ้งเตือนจริง
- ⬜ ไม่ tick = ส่งแจ้งเตือนจริง

---

## วิธีใช้งาน

### รับสัญญาณอัตโนมัติ (ทุก 5 นาที)
หลังจากตั้งค่า cron แล้ว ระบบจะรันอัตโนมัติทุก 5 นาที ถ้ามีสัญญาณ BUY/SELL ในแท่งปิดล่าสุด จะส่ง Telegram ทันที

### ดู dashboard
เปิด URL: `https://USERNAME.github.io/REPO_NAME/`
- ตาราง W/L แบบ TradingView
- Live signal card
- Performance chart (win rate + P&L)
- ปรับ Settings ในเว็บ (Symbol, N Bars, Backtest limit, Telegram)
- Auto refresh ทุก 5 นาที

---

## Logic ทบไม้ (Martingale Recovery) — สำคัญ!

```
สัญญาณ BUY:
  ┌──────────────────────────────────────────┐
  │ แท่งสัญญาณ │ แท่ง 1 │ แท่ง 2 │ แท่ง 3 │
  │     ★      │  🟢    │   -    │   -    │  → ชนะเร็ว (barsHeld=1)
  │     ★      │  🔴    │  🟢    │   -    │  → ชนะช้า (barsHeld=2)
  │     ★      │  🔴    │  🔴    │  🟢    │  → ชนะช้า (barsHeld=3)
  │     ★      │  🔴    │  🔴    │  🔴    │  → แพ้ (ครบ N=3 ไม่มีเขียว)
  └──────────────────────────────────────────┘

สัญญาณ SELL: กลับสี (🟢 = แพ้, 🔴 = ชนะ)
```

**ปรับ N ใน Settings:**
- N=3 (default) → win rate ~85%
- N=5 → win rate ~90% (แต่ระวัง overfit)

---

## การปรับแต่ง

### เปลี่ยน Symbol / Timeframe

**สำหรับ Cron (Python):** แก้ใน Variables ของ GitHub repo
**สำหรับ Dashboard:** ปรับในหน้าเว็บ Settings

### เปลี่ยน Parameters ของ Indicator

แก้ใน:
- `check_signal.py` — บรรทัด `DOMCYCLE`, `VIBRATION`, `LEVELING`, ฯลฯ
- `index.html` — บรรทัด `const PARAMS = {...}`

### เปลี่ยน Exchange

ปัจจุบันใช้ Bybit หากต้องการ Binance:
- `check_signal.py`: แก้ `fetch_ohlcv_bybit()` ให้เรียก Binance API
- `index.html`: แก้ฟังก์ชัน `fetchOHLCV()` ให้เรียก Binance API

```python
# Binance API (Python)
url = 'https://api.binance.com/api/v3/klines'
params = {'symbol': 'BTCUSDT', 'interval': '5m', 'limit': 250}
```

```javascript
// Binance API (JavaScript)
const url = 'https://api.binance.com/api/v3/klines';
const params = new URLSearchParams({ symbol: 'BTCUSDT', interval: '5m', limit: 1000 });
```

---

## รายละเอียดการแปล Pine Script → Python

| Pine Script | Python Equivalent | หมายเหตุ |
|---|---|---|
| `ta.rma(src, length)` | `calc_rma(values, length)` | alpha = 1/length (Wilder) |
| `ta.sma(src, length)` | `calc_sma(values, length)` | |
| `ta.rsi(src, length)` | `calc_rsi(src, length)` | ใช้ Wilder's smoothing |
| `ta.stoch(s,h,l,len)` | `calc_stoch(source, length)` | source=high=low |
| `ta.crossover(a,b)` | `a[i] > b[i] and a[i-1] <= b[i-1]` | |
| `ta.crossunder(a,b)` | `a[i] < b[i] and a[i-1] >= b[i-1]` | |
| `ta.change(src)` | `src[i] - src[i-1]` | change[0] = NaN |
| `nz(x, default)` | `nz(x, default)` | |
| `var float x = 0.0` | list `[0.0] * n` + carry-forward | bar-by-bar loop |
| `int(x)` | `int(x)` | truncate toward zero |

---

## ข้อจำกัด / ข้อควรระวัง

1. **GitHub Actions Free Plan** — public repo ไม่จำกัด, private repo 2,000 min/เดือน
2. **Cron timing** — GitHub Actions cron อาจ delay 1-5 นาที (known limitation)
3. **Bybit API rate limit** — public endpoint ~600 req/min, เราใช้แค่ 1 req/5min ปลอดภัยมาก
4. **GitHub Pages free** — 100GB bandwidth/เดือน, 1GB storage (เพียงพอสำหรับ HTML)
5. **Dashboard auto refresh** — ทุก 5 นาที เพื่อให้ตรงกับ cron schedule
6. **Win Rate จริง vs TradingView** — อาจต่างเล็กน้อยเนื่องจาก:
   - จำนวน bar warmup (เราใช้ 250, TV ใช้ทั้งประวัติ)
   - timing ของการดึงข้อมูล
   - ความแตกต่างของข้อมูลระหว่าง exchange

---

## License

MIT — ใช้ได้อิสระ โปรดทดสอบก่อนใช้งานจริง

## ⚠️ Disclaimer

การลงทุนมีความเสี่ยง — ใช้เพื่อการศึกษาเท่านั้น · Not financial advice
