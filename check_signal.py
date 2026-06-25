"""
================================================================================
 Pine Script v5  ->  Python  ->  GitHub Actions Cron
 Indicator : cRSI + Stoch RSI | Multi-Bar Win Report (Max WinRate)
 Alert     : Telegram (primary) + LINE Notify (optional)
 Exchange  : Bybit v5 Public API (no auth needed)
================================================================================

 Parameters (จาก TradingView settings screenshot — ค่าล่าสุด):
   Dominant Cycle Length : 13   (domcycle)
   Vibration             : 10
   Leveling              : 10.0
   SmoothK               : 3
   SmoothD               : 3
   RSI Length            : 15   (lengthRSI)
   Stochastic Length     : 10   (lengthStoch)
   Stoch Buy Zone (low)  : 15   (stoch_low)
   Stoch Sell Zone (high): 85   (stoch_high)

 Win/Loss Logic: ทบไม้ (Martingale Recovery)
   BUY  ชนะถ้า มีแท่งเขียว (close > open) อย่างน้อย 1 แท่งใน N แท่งถัดไป
   SELL ชนะถ้า มีแท่งแดง (close < open) อย่างน้อย 1 แท่งใน N แท่งถัดไป
   ชนะเร็ว → barsHeld น้อย / ชนะช้า → barsHeld มาก / แพ้ → barsHeld = N

 การแปลฟังก์ชัน Pine Script -> Python (สำคัญมาก):
   1. ta.rma(src, length)  ->  alpha = 1/length  (Wilder's Smoothing)
      ** ห้ามใช้ alpha = 2/(length+1) ซึ่งเป็นของ ta.ema **
   2. ตัวแปร var float ทั้งหมด (crsi, db, ub, last_stoch_k_crossup,
      last_stoch_k_crossdown) คำนวณแบบ bar-by-bar loop เรียงตามเวลา
      ** ห้ามใช้ vectorized operation **
   3. nz(x, default) = x ถ้าไม่ใช่ NaN, มิฉะนั้นคืน default
   4. ดึงข้อมูลขั้นต่ำ 200 แท่งเพื่อให้ค่า warmup เสถียร
================================================================================
"""

# ============================================================
#  Imports
# ============================================================
import os
import sys
import json
import math
import time
import requests
from datetime import datetime, timezone, timedelta


# ============================================================
#  Configuration (จาก Environment Variables)
# ============================================================
# --- Exchange ---
EXCHANGE          = os.environ.get('EXCHANGE', 'bybit')
SYMBOL            = os.environ.get('SYMBOL', 'BTCUSDT')
TIMEFRAME         = os.environ.get('TIMEFRAME', '5')           # Bybit interval '5' = 5m
env_tf_minutes = os.environ.get('TIMEFRAME_MINUTES', '').strip()
TIMEFRAME_MINUTES = int(env_tf_minutes) if env_tf_minutes else 5
OHLCV_LIMIT       = int(os.environ.get('OHLCV_LIMIT', '250'))   # >= 200 for warmup

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID   = os.environ.get('TELEGRAM_CHAT_ID', '')

# --- LINE Notify (optional) ---
LINE_NOTIFY_TOKEN  = os.environ.get('LINE_NOTIFY_TOKEN', '')

# --- Notification channel: 'telegram' | 'line' | 'both' ---
NOTIFY_CHANNEL     = os.environ.get('NOTIFY_CHANNEL', 'telegram')

# --- Dry run (ทดสอบโดยไม่ส่งแจ้งเตือนจริง) ---
DRY_RUN            = os.environ.get('DRY_RUN', 'false').lower() == 'true'

# --- Timezone offset (ชม.) สำหรับแสดงเวลา (default 7 = Bangkok) ---
DISPLAY_TZ_OFFSET_HOURS = int(os.environ.get('TZ_OFFSET_HOURS', '7'))

# --- Win/Loss: จำนวนแท่งสูงสุดที่ยอมให้ "ทบไม้" ---
MAX_RECOVERY_BARS  = int(os.environ.get('MAX_RECOVERY_BARS', '3'))


# ============================================================
#  Pine Script Parameters (จากรูป — ห้ามแก้)
# ============================================================
DOMCYCLE     = 13
VIBRATION    = 10
LEVELING     = 10.0
CYCLICMEMORY = DOMCYCLE * 2      # = 26
CYCLELEN     = DOMCYCLE // 2     # = 6  (Pine int() truncates toward zero)

SMOOTHK     = 3
SMOOTHD     = 3
LENGTH_RSI  = 15
LENGTH_STOCH = 10

STOCH_LOW   = 15
STOCH_HIGH  = 85


# ============================================================
#  Helper Functions  (Pine Script equivalents)
# ============================================================

def is_nan(v):
    if v is None:
        return True
    if isinstance(v, float):
        return math.isnan(v)
    return False


def nz(value, default=0.0):
    if is_nan(value):
        return default
    return value


def calc_rma(values, length):
    """
    Wilder's RMA  - ตรงกับ Pine ta.rma()
       alpha = 1 / length        (** ไม่ใช่ 2/(length+1) แบบ EMA **)
       seed  = SMA ของ `length` ค่าแรกที่ไม่ใช่ NaN ติดต่อกัน
       rma[i] = alpha * values[i] + (1 - alpha) * rma[i-1]
    คืน list ที่มี NaN ในช่วง warmup
    """
    n = len(values)
    rma = [float('nan')] * n

    count = 0
    start_idx = -1
    for i in range(n):
        if not is_nan(values[i]):
            count += 1
            if count == length:
                start_idx = i
                break
        else:
            count = 0

    if start_idx == -1:
        return rma

    window = values[start_idx - length + 1 : start_idx + 1]
    rma[start_idx] = sum(window) / length

    alpha = 1.0 / length
    for i in range(start_idx + 1, n):
        v = values[i]
        if is_nan(v):
            rma[i] = rma[i - 1]
        else:
            rma[i] = alpha * v + (1.0 - alpha) * rma[i - 1]
    return rma


def calc_sma(values, length):
    n = len(values)
    sma = [float('nan')] * n
    for i in range(length - 1, n):
        window = values[i - length + 1 : i + 1]
        if any(is_nan(v) for v in window):
            continue
        sma[i] = sum(window) / length
    return sma


def calc_rsi(src, length):
    """Standard RSI ใช้ Wilder's smoothing  - ตรงกับ Pine ta.rsi()"""
    n = len(src)
    change = [float('nan')] * n
    for i in range(1, n):
        change[i] = src[i] - src[i - 1]

    up_src   = [float('nan') if is_nan(c) else max(c, 0.0)  for c in change]
    down_src = [float('nan') if is_nan(c) else max(-c, 0.0) for c in change]

    up   = calc_rma(up_src,   length)
    down = calc_rma(down_src, length)

    rsi = [float('nan')] * n
    for i in range(n):
        u = up[i]
        d = down[i]
        if is_nan(u) or is_nan(d):
            rsi[i] = float('nan')
        elif d == 0:
            rsi[i] = 100.0
        elif u == 0:
            rsi[i] = 0.0
        else:
            rsi[i] = 100.0 - 100.0 / (1.0 + u / d)
    return rsi


def calc_stoch(source, length):
    """Stochastic  - ตรงกับ Pine ta.stoch(source, source, source, length)"""
    n = len(source)
    stoch = [float('nan')] * n
    for i in range(length - 1, n):
        window = source[i - length + 1 : i + 1]
        valid = [v for v in window if not is_nan(v)]
        if len(valid) < length:
            continue
        lowest  = min(valid)
        highest = max(valid)
        if highest == lowest:
            stoch[i] = 100.0
        else:
            stoch[i] = 100.0 * (source[i] - lowest) / (highest - lowest)
    return stoch


# ============================================================
#  Main Signal Computation  (bar-by-bar, ห้าม vectorize)
# ============================================================

def compute_signals(closes):
    src = closes
    n = len(src)

    torque     = 2.0 / (VIBRATION + 1)               # = 0.1818...
    phasingLag = int((VIBRATION - 1) / 2)            # = 4   (Pine int())
    aperc      = LEVELING / 100.0                    # = 0.10

    # -------- [1] RSI สำหรับ cRSI (cyclelen=6) --------
    change = [float('nan')] * n
    for i in range(1, n):
        change[i] = src[i] - src[i - 1]

    up_src   = [float('nan') if is_nan(c) else max(c, 0.0)  for c in change]
    down_src = [float('nan') if is_nan(c) else max(-c, 0.0) for c in change]

    up   = calc_rma(up_src,   CYCLELEN)
    down = calc_rma(down_src, CYCLELEN)

    rsi = [float('nan')] * n
    for i in range(n):
        u = up[i]
        d = down[i]
        if is_nan(u) or is_nan(d):
            rsi[i] = float('nan')
        elif d == 0:
            rsi[i] = 100.0
        elif u == 0:
            rsi[i] = 0.0
        else:
            rsi[i] = 100.0 - 100.0 / (1.0 + u / d)

    # -------- [2] cRSI (var float, bar-by-bar) --------
    crsi = [float('nan')] * n
    for i in range(n):
        rsi_now = rsi[i]
        rsi_lag = rsi[i - phasingLag] if (i - phasingLag) >= 0 else float('nan')

        if is_nan(rsi_now) or is_nan(rsi_lag):
            crsi[i] = float('nan')
        else:
            prev      = crsi[i - 1] if i > 0 else float('nan')
            prev_nz   = 0.0 if is_nan(prev) else prev
            crsi[i]   = torque * (2.0 * rsi_now - rsi_lag) + (1.0 - torque) * prev_nz

    # -------- [3] db & ub (var float, bar-by-bar) --------
    db = [0.0] * n
    ub = [0.0] * n

    for i in range(n):
        lmax = -999999.0
        lmin =  999999.0
        for j in range(CYCLICMEMORY):
            idx = i - j
            if idx < 0:
                break
            v = crsi[idx]
            v_for_max = v if not is_nan(v) else -999999.0
            v_for_min = v if not is_nan(v) else  999999.0
            if v_for_max > lmax:
                lmax = v_for_max
            if v_for_min < lmin:
                lmin = v_for_min

        if lmax == -999999.0 or lmin == 999999.0:
            if i > 0:
                db[i] = db[i - 1]
                ub[i] = ub[i - 1]
            continue

        mstep = (lmax - lmin) / 100.0

        # db
        db_found = False
        for step in range(101):
            testvalue = lmin + mstep * step
            below = 0
            for j in range(CYCLICMEMORY):
                idx = i - j
                if idx < 0:
                    break
                v = crsi[idx]
                if not is_nan(v) and v < testvalue:
                    below += 1
            if below / CYCLICMEMORY >= aperc:
                db[i] = testvalue
                db_found = True
                break
        if not db_found:
            db[i] = db[i - 1] if i > 0 else 0.0

        # ub
        ub_found = False
        for step in range(101):
            testvalue = lmax - mstep * step
            above = 0
            for j in range(CYCLICMEMORY):
                idx = i - j
                if idx < 0:
                    break
                v = crsi[idx]
                if not is_nan(v) and v >= testvalue:
                    above += 1
            if above / CYCLICMEMORY >= aperc:
                ub[i] = testvalue
                ub_found = True
                break
        if not ub_found:
            ub[i] = ub[i - 1] if i > 0 else 0.0

    # -------- [4] Stoch RSI --------
    rsi1      = calc_rsi(src, LENGTH_RSI)
    stoch_raw = calc_stoch(rsi1, LENGTH_STOCH)
    k         = calc_sma(stoch_raw, SMOOTHK)
    d         = calc_sma(k, SMOOTHD)

    # -------- [5] last_stoch_k_crossup / crossdown (var float) --------
    last_crossup   = [0.0] * n
    last_crossdown = [0.0] * n

    for i in range(n):
        if i > 0:
            last_crossup[i]   = last_crossup[i - 1]
            last_crossdown[i] = last_crossdown[i - 1]
        if i == 0:
            continue

        k_now, k_prev = k[i], k[i - 1]
        d_now, d_prev = d[i], d[i - 1]
        if any(is_nan(x) for x in (k_now, k_prev, d_now, d_prev)):
            continue

        if k_now > d_now and k_prev <= d_prev:
            last_crossup[i] = k_now
        if k_now < d_now and k_prev >= d_prev:
            last_crossdown[i] = k_now

    # -------- [6] Buy / Sell Signals --------
    buy_signals  = [False] * n
    sell_signals = [False] * n

    for i in range(1, n):
        crsi_now, crsi_prev = crsi[i], crsi[i - 1]
        db_now,   db_prev   = db[i],   db[i - 1]
        ub_now,   ub_prev   = ub[i],   ub[i - 1]
        k_now               = k[i]
        last_up             = last_crossup[i]
        last_down           = last_crossdown[i]

        if any(is_nan(x) for x in (crsi_now, crsi_prev, db_now, db_prev, k_now)):
            continue

        if (crsi_now > db_now) and (crsi_prev <= db_prev):
            if last_up < STOCH_LOW and k_now < STOCH_LOW:
                buy_signals[i] = True

        if (crsi_now < ub_now) and (crsi_prev >= ub_prev):
            if last_down > STOCH_HIGH and k_now > STOCH_HIGH:
                sell_signals[i] = True

    return {
        'crsi':           crsi,
        'db':             db,
        'ub':             ub,
        'k':              k,
        'd':              d,
        'rsi1':           rsi1,
        'buy_signals':    buy_signals,
        'sell_signals':   sell_signals,
        'last_crossup':   last_crossup,
        'last_crossdown': last_crossdown,
    }


# ============================================================
#  Data Fetching  (Bybit v5 Public API)
# ============================================================

def fetch_ohlcv_bybit(symbol=SYMBOL, interval=TIMEFRAME, limit=OHLCV_LIMIT):
    # ย้ายมาใช้ OKX API เพื่อหลบการบล็อก IP และกฎหมายพื้นที่ (451) ของ GitHub Actions
    url = 'https://www.okx.com/api/v5/market/candles'
    
    # แปลงกู่ตัวแปรคู่เหรียญให้เข้ากับรูปแบบของ OKX (เช่น BTCUSDT -> BTC-USDT-SWAP สำหรับสัญญาฟิวเจอร์ส หรือ BTC-USDT สำหรับสปอต)
    # แนะนำให้ใช้แบบ SWAP (ฟิวเจอร์ส) เพราะราคาจะตรงกับ Bybit ที่เราสแกนวินเรทไว้มากที่สุด
    clean_symbol = str(symbol).upper().replace('-', '').replace('_', '')
    if "USDT" in clean_symbol and not "-SWAP" in clean_symbol:
        base_currency = clean_symbol.replace("USDT", "")
        okx_symbol = f"{base_currency}-USDT-SWAP"
    else:
        okx_symbol = clean_symbol

    # แปลง interval (เช่น '5') ให้เข้ากับฟอร์แมตของ OKX (เช่น '5m', '1H', '4H')
    tf_str = str(interval).strip()
    if tf_str.isdigit():
        okx_interval = f"{tf_str}m"
        if tf_str == "60":
            okx_interval = "1H"
        elif tf_str == "240":
            okx_interval = "4H"
    else:
        okx_interval = tf_str

    params = {
        'instId':   okx_symbol,
        'bar':      okx_interval,
        'limit':    str(limit),
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    result_data = resp.json()

    if result_data.get('code') != '0':
        raise Exception(f"OKX API error: {result_data.get('msg', 'Unknown')}")

    klines = result_data.get('data', [])
    if not klines:
        raise Exception('OKX API returned empty kline list')

    # OKX ส่งข้อมูลจาก "ใหม่ไปเก่า" (แท่งปัจจุบันอยู่ดัชนี 0) 
    # โค้ดคำนวณต้องการเก่าไปใหม่ จึงต้องใช้ .reverse() เหมือน Bybit ดั้งเดิมครับ
    klines.reverse()

    ohlcv = []
    for kl in klines:
        # โครงสร้าง OKX: 0=ts, 1=o, 2=h, 3=l, 4=c, 5=vol
        ohlcv.append([
            int(kl[0]),     # timestamp (ms)
            float(kl[1]),   # open
            float(kl[2]),   # high
            float(kl[3]),   # low
            float(kl[4]),   # close
            float(kl[5]),   # volume
        ])
    return ohlcv


def get_last_closed_bar_index(ohlcv, timeframe_minutes=TIMEFRAME_MINUTES):
    """หา index ของแท่งเทียนที่ปิดตัวลงล่าสุด"""
    now_ms          = int(time.time() * 1000)
    last_bar_open   = ohlcv[-1][0]
    last_bar_close  = last_bar_open + timeframe_minutes * 60 * 1000

    if now_ms >= last_bar_close + 5000:
        return len(ohlcv) - 1
    return len(ohlcv) - 2


# ============================================================
#  Notifications  (Telegram + LINE Notify)
# ============================================================

def send_telegram(message):
    if DRY_RUN:
        print('[DRY-RUN] Telegram message:')
        print(message)
        return True
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print('[WARN] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ไม่ได้ตั้ง - ข้าม')
        return False

    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id':                  TELEGRAM_CHAT_ID,
        'text':                     message,
        'parse_mode':               'HTML',
        'disable_web_page_preview': True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print('[INFO] Telegram ส่งสำเร็จ')
            return True
        print(f'[ERROR] Telegram API {resp.status_code}: {resp.text}')
        return False
    except Exception as e:
        print(f'[ERROR] Telegram ส่งล้มเหลว: {e}')
        return False


def send_line_notify(message):
    if DRY_RUN:
        print('[DRY-RUN] LINE message:')
        print(message)
        return True
    if not LINE_NOTIFY_TOKEN:
        print('[WARN] LINE_NOTIFY_TOKEN ไม่ได้ตั้ง - ข้าม')
        return False

    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {LINE_NOTIFY_TOKEN}'}
    payload = {'message': message}
    try:
        resp = requests.post(url, headers=headers, data=payload, timeout=10)
        if resp.status_code == 200:
            print('[INFO] LINE Notify ส่งสำเร็จ')
            return True
        print(f'[ERROR] LINE API {resp.status_code}: {resp.text}')
        return False
    except Exception as e:
        print(f'[ERROR] LINE Notify ส่งล้มเหลว: {e}')
        return False


def notify(message):
    ch = NOTIFY_CHANNEL.lower()
    if ch == 'telegram':
        send_telegram(message)
    elif ch == 'line':
        send_line_notify(message)
    elif ch == 'both':
        send_telegram(message)
        send_line_notify(message)
    else:
        print(f'[WARN] NOTIFY_CHANNEL ไม่รู้จัก: {ch}')


# ============================================================
#  State Persistence (Dedupe)
# ============================================================

STATE_FILE = os.environ.get('STATE_FILE', 'last_signal.json')

def load_last_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_last_state(state):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception:
        pass


# ============================================================
#  Main Logic
# ============================================================

def run_signal_check():
    """
    Entry point หลัก:
      1. ดึง OHLCV จาก Bybit
      2. คำนวณสัญญาณ
      3. ตรวจแท่งปิดล่าสุด -> ส่งแจ้งเตือนถ้ามีสัญญาณ
    """
    print(f'[INFO] เริ่มตรวจสัญญาณ: {SYMBOL} {TIMEFRAME_MINUTES}m  (limit={OHLCV_LIMIT})')
    print(f'[INFO] DRY_RUN={DRY_RUN}  NOTIFY_CHANNEL={NOTIFY_CHANNEL}  MAX_RECOVERY_BARS={MAX_RECOVERY_BARS}')

    # 1) Fetch
    ohlcv = fetch_ohlcv_bybit()
    print(f'[INFO] ดึงข้อมูลได้ {len(ohlcv)} แท่ง')
    if len(ohlcv) < 200:
        raise Exception(f'ข้อมูลไม่พอ: ได้ {len(ohlcv)} แท่ง (ต้อง >= 200)')

    closes     = [bar[4] for bar in ohlcv]
    timestamps = [bar[0] for bar in ohlcv]

    # 2) Compute signals
    result = compute_signals(closes)

    # 3) หาแท่งปิดล่าสุด
    idx = get_last_closed_bar_index(ohlcv)
    print(f'[INFO] แท่งปิดล่าสุด: index={idx} / {len(ohlcv)}')

    buy  = result['buy_signals'][idx]
    sell = result['sell_signals'][idx]

    # เตรียมข้อมูลเวลา
    bar_time_ms  = timestamps[idx]
    bar_close    = closes[idx]
    tz_local     = timezone(timedelta(hours=DISPLAY_TZ_OFFSET_HOURS))
    bar_time_str = datetime.fromtimestamp(bar_time_ms / 1000, tz=timezone.utc) \
                     .astimezone(tz_local) \
                     .strftime('%Y-%m-%d %H:%M')

    # 4) ส่งแจ้งเตือนถ้ามีสัญญาณ
    signal_type = None
    emoji       = ''
    if buy:
        signal_type, emoji = 'BUY',  '[BUY]'
    elif sell:
        signal_type, emoji = 'SELL', '[SELL]'

    if signal_type:
        key = f"{SYMBOL}-{bar_time_ms}-{signal_type}"
        prev_state = load_last_state()
        if prev_state.get('last_key') == key:
            print(f'[INFO] ข้ามการแจ้งเตือน — เคย alert แล้ว: {key}')
        else:
            if signal_type == 'BUY':
                poly_direction = 'Up'
                poly_bet = 'Up'
            else:
                poly_direction = 'DOWN'
                poly_bet = 'Down'
            msg = (
                f"{emoji} <b>{signal_type} SIGNAL</b>\n"
                f"---------------------------\n"
                f"Symbol : <b>{SYMBOL}</b>\n"
                f"TF     : {TIMEFRAME_MINUTES}m\n"
                f"Bar    : {bar_time_str}\n"
                f"Close  : {bar_close:,.2f}\n"
                f"---------------------------\n"
                f"cRSI   : {nz(result['crsi'][idx], 0):.4f}\n"
                f"db     : {nz(result['db'][idx], 0):.4f}\n"
                f"ub     : {nz(result['ub'][idx], 0):.4f}\n"
                f"Stoch K: {nz(result['k'][idx], 0):.4f}\n"
                f"Stoch D: {nz(result['d'][idx], 0):.4f}\n"
                f"LastCrossUp  : {nz(result['last_crossup'][idx], 0):.4f}\n"
                f"LastCrossDown: {nz(result['last_crossdown'][idx], 0):.4f}\n"
                f"---------------------------\n"
                f"Polymarket BTC Up/Down 5m:\n"
                f"Predict next {MAX_RECOVERY_BARS} candles = {poly_direction}\n"
                f"Bet <b>{poly_bet}</b> on Polymarket"
            )
            notify(msg)
            save_last_state({'last_key': key, 'bar_time_ms': bar_time_ms, 'signal': signal_type})
    else:
        print(f'[INFO] ไม่มีสัญญาณในแท่งปิดล่าสุด (index={idx})')

    # 5) สรุปผลลัพธ์
    print()
    print('=' * 60)
    print(f'  Signal Result: {signal_type or "NONE"}')
    print('=' * 60)
    print(json.dumps({
        'symbol':          SYMBOL,
        'timeframe':       f'{TIMEFRAME_MINUTES}m',
        'bars_analyzed':   len(ohlcv),
        'last_closed_bar': {
            'index':         idx,
            'timestamp_ms':  bar_time_ms,
            'time_local':    bar_time_str,
            'close':         bar_close,
        },
        'signal':      signal_type or 'NONE',
        'buy_signal':  buy,
        'sell_signal': sell,
        'indicators': {
            'crsi':            round(nz(result['crsi'][idx], 0), 6),
            'db':              round(nz(result['db'][idx], 0), 6),
            'ub':              round(nz(result['ub'][idx], 0), 6),
            'k':               round(nz(result['k'][idx], 0), 6),
            'd':               round(nz(result['d'][idx], 0), 6),
            'last_crossup':    round(nz(result['last_crossup'][idx], 0), 6),
            'last_crossdown':  round(nz(result['last_crossdown'][idx], 0), 6),
        },
    }, indent=2))
    print('=' * 60)

    return {
        'signal':      signal_type or 'NONE',
        'buy_signal':  buy,
        'sell_signal': sell,
    }


# ============================================================
#   CLI Entry Point (เวอร์ชันเรียกใช้ระบบฟังก์ชัน notify ดั้งเดิม)
# ============================================================
def main():
    try:
        result = run_signal_check()
        sys.exit(0)
    except Exception as e:
        print(f'[FATAL] {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
