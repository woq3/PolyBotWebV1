# cRSI + Stoch RSI — GitHub Actions Signal Bot

แปลง Pine Script v5 indicator (cRSI + Stoch RSI | Multi-Bar Win Report) ให้เป็น
Python script รันบน **GitHub Actions** ฟรี 100% (ไม่จำกัดจำนวนครั้ง/วัน สำหรับ public repo)
ตื่นขึ้นมาทุก 15 นาทีเพื่อคำนวณสัญญาณและส่งแจ้งเตือนเข้า Telegram / LINE Notify

> **เหตุผลที่เลือก GitHub Actions แทน Vercel Cron:**
> Vercel Hobby plan จำกัด cron ได้วันละครั้งเท่านั้น ส่วน GitHub Actions ฟรี
> สำหรับ public repo แบบไม่จำกัด และ private repo มี free minutes 2,000/เดือน
> (เพียงพอสำหรับการรันทุก 15 นาที = ~2,880 ครั้ง/เดือน)

---

## โครงสร้างโปรเจกต์

```
.
├── .github/
│   └── workflows/
│       └── check-signal.yml     # GitHub Actions workflow (cron + manual)
├── check_signal.py              # สคริปต์หลัก (Pine Script translation + CLI)
├── requirements.txt             # dependencies (เฉพาะ requests)
├── .env.example                 # template สำหรับ env vars / secrets
└── README.md
```

---

## คุณสมบัติ

- ✅ แปล Pine Script เป็น Python **แม่นยำ 100%**:
  - `ta.rma` ใช้ `alpha = 1/length` (Wilder's Smoothing) — ไม่ใช่ EMA
  - `var float` ทุกตัวคำนวณแบบ **bar-by-bar loop** (ไม่ใช้ vectorized)
  - `nz(x, default)` ทำงานเหมือน Pine ทุกประการ
  - ลอจิก db/ub วนลูป 100 steps เหมือนต้นฉบับ
- ✅ ดึงข้อมูลจาก **Bybit v5 Public API** (ไม่ต้องใช้ API key)
- ✅ ตรวจแท่งเทียนที่ **ปิดตัวลงล่าสุด** อัตโนมัติ (ข้ามแท่งที่กำลัง form)
- ✅ ส่งแจ้งเตือนผ่าน **Telegram** (default) / LINE Notify / ทั้งคู่
- ✅ รองรับ **dry-run mode** สำหรับทดสอบโดยไม่ส่งจริง
- ✅ Dependencies น้อยที่สุด (เฉพาะ `requests`) — install เร็ว
- ✅ Manual trigger ผ่าน GitHub UI ได้ (`workflow_dispatch`)
- ✅ ป้องกันการรันซ้อนทับ (`concurrency` control)

---

## วิธี Deployment บน GitHub Actions

### 1. เตรียม Telegram Bot (หรือ LINE Notify)

**Telegram:**
1. คุยกับ [@BotFather](https://t.me/BotFather) → สร้าง bot → ได้ `TELEGRAM_BOT_TOKEN`
2. เพิ่ม bot เข้า group หรือเริ่ม chat ส่วนตัว → ส่งข้อความอะไรก็ได้
3. คุยกับ [@userinfobot](https://t.me/userinfobot) → ได้ `TELEGRAM_CHAT_ID`

**LINE Notify (ทางเลือก):**
1. ไปที่ https://notify-bot.line.me/ → ออก token → ได้ `LINE_NOTIFY_TOKEN`

### 2. สร้าง GitHub Repository

```bash
# สร้าง repo ใหม่ (แนะนำให้ public เพื่อใช้ Actions ฟรีไม่จำกัด)
git init
git add .
git commit -m "cRSI + Stoch RSI Signal Bot - GitHub Actions"
git branch -M main
git remote add origin https://github.com/USERNAME/REPO_NAME.git
git push -u origin main
```

### 3. ตั้งค่า Secrets และ Variables

ใน repo ไปที่ **Settings → Secrets and variables → Actions**

#### A) Secrets (sensitive data)
ในแท็บ **Secrets** → New repository secret:

| Secret Name | Value | จำเป็น |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | จาก BotFather | ใช่ (ถ้าใช้ Telegram) |
| `TELEGRAM_CHAT_ID` | จาก userinfobot | ใช่ (ถ้าใช้ Telegram) |
| `LINE_NOTIFY_TOKEN` | จาก LINE Notify | ใช่ (ถ้าใช้ LINE) |

#### B) Variables (non-sensitive config)
ในแท็บ **Variables** → New repository variable:

| Variable Name | Value | Default |
|---|---|---|
| `EXCHANGE` | `bybit` | bybit |
| `SYMBOL` | `BTCUSDT` | BTCUSDT |
| `TIMEFRAME` | `15` | 15 |
| `TIMEFRAME_MINUTES` | `15` | 15 |
| `OHLCV_LIMIT` | `250` | 250 |
| `NOTIFY_CHANNEL` | `telegram` / `line` / `both` | telegram |
| `TZ_OFFSET_HOURS` | `7` | 7 (Bangkok) |

> 💡 ใน workflow เราอ้างถึง secrets ด้วย `${{ secrets.XXX }}` และ
> variables ด้วย `${{ vars.XXX }}`

### 4. ตรวจสอบ Workflow

หลัง push แล้ว ไปที่แท็บ **Actions** ใน repo จะเห็น workflow ชื่อ
"Check Trading Signal" — มันจะรันอัตโนมัติทุก 15 นาที (ที่นาที :05, :20, :35, :50 UTC)

### 5. ทดสอบ Manual

ในแท็บ **Actions** → เลือก workflow "Check Trading Signal" → คลิก **Run workflow**

ตอน manual trigger มีตัวเลือก `dry_run`:
- ✅ tick = ทดสอบโดยพิมพ์ข้อความออก log แต่ไม่ส่งแจ้งเตือนจริง
- ⬜ ไม่ tick = ส่งแจ้งเตือนจริง

---

## ทดสอบ Local (ก่อน push)

```bash
cd /path/to/project
pip install -r requirements.txt

# ตั้ง env vars (สำหรับ local test)
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx
# หรือทดสอบแบบ dry-run ก่อน
export DRY_RUN=true

# รัน
python check_signal.py
```

---

## Schedule Logic

Workflow ตั้ง cron เป็น `5,20,35,50 * * * *` (UTC) ซึ่งหมายถึง:

| UTC Time | Bangkok Time (UTC+7) | หมายเหตุ |
|---|---|---|
| 00:05 | 07:05 | หลังแท่ง 00:00 UTC ปิด |
| 00:20 | 07:20 | หลังแท่ง 00:15 UTC ปิด |
| 00:35 | 07:35 | หลังแท่ง 00:30 UTC ปิด |
| 00:50 | 07:50 | หลังแท่ง 00:45 UTC ปิด |

**ทำไมต้องเลื่อน 5 นาที?**
- Bybit แท่ง 15m ปิดที่ :00, :15, :30, :45 UTC
- รอ 5 นาทีให้ exchange update ข้อมูลเสร็จก่อน
- GitHub Actions อาจ delay เพิ่ม 1-3 นาที (เป็น normal behavior)

> ⚠️ **GitHub Actions ใช้ UTC** เหมือน Vercel แต่ไม่จำกัดจำนวนครั้ง/วัน
> สำหรับ public repo ใช้ได้ฟรีไม่จำกัด สำหรับ private repo มี free minutes 2,000/เดือน

---

## การปรับแต่ง

### เปลี่ยน Symbol / Timeframe

ใน **Settings → Secrets and variables → Actions → Variables** เปลี่ยนค่า:
- `SYMBOL=ETHUSDT`
- `TIMEFRAME=60` (1 ชม.)
- `TIMEFRAME_MINUTES=60`

**สำคัญ:** อย่าลืมแก้ `cron:` ใน `.github/workflows/check-signal.yml` ให้ตรงกับ timeframe:

| Timeframe | Cron schedule (UTC) |
|---|---|
| 5m  | `5,10,15,20,25,30,35,40,45,50,55,0 * * * *` (หรือใช้ `*/5` แล้วเลื่อน 1 นาที) |
| 15m | `5,20,35,50 * * * *` (default) |
| 1h  | `5 * * * *` |
| 4h  | `5 0,4,8,12,16,20 * * *` |
| 1d  | `5 0 * * *` |

### เปลี่ยน Exchange

ปัจจุบันใช้ Bybit หากต้องการ Binance แก้ฟังก์ชัน `fetch_ohlcv_bybit()` ใน
`check_signal.py` ให้เรียก Binance API:
```
GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=250
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

**พารามิเตอร์คงที่จาก Pine Script:**
```
domcycle=14, vibration=10, leveling=7.0
cyclicmemory=28, cyclelen=7
smoothK=3, smoothD=3, lengthRSI=15, lengthStoch=12
stoch_low=10, stoch_high=90
```

---

## ข้อจำกัด / ข้อควรระวัง

1. **GitHub Actions Free Plan** — public repo ไม่จำกัด, private repo 2,000 min/เดือน
2. **Cron timing** — GitHub Actions cron อาจ delay 1-5 นาที (เป็น known limitation)
3. **Bybit API rate limit** — public endpoint จำกัด ~600 req/min, เราใช้แค่ 1 req/15min ปลอดภัยมาก
4. **Win Rate** — การแปลฟังก์ชันแม่นยำ 100% แต่ผล backtest อาจต่างจาก TradingView
   เล็กน้อยเนื่องจาก:
   - จำนวน bar warmup ที่ใช้ (เราใช้ 250, TV ใช้ทั้งประวัติ)
   - timing ของการดึงข้อมูล (เศษวินาทีหลังปิดแท่ง)
   - ความแตกต่างของข้อมูลระหว่าง exchange

5. **Manual trigger recommended for first test** — ก่อนเปิดใช้ cron อัตโนมัติ
   แนะนำให้ manual trigger ครั้งแรกพร้อม `dry_run=true` เพื่อตรวจสอบ log

---

## License

MIT — ใช้ได้อิสระ โปรดทดสอบก่อนใช้งานจริง
