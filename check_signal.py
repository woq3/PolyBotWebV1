"""
================================================================================
 Pine Script v5  ->  Python  ->  GitHub Actions Cron
 Indicator : cRSI + Stoch RSI | Multi-Bar Win Report (Max WinRate)
 Alert     : Telegram (primary) + LINE Notify (optional)
 Exchange  : Bybit v5 Public API (no auth needed)
================================================================================

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
TIMEFRAME         = os.environ.get('TIMEFRAME', '15')
TIMEFRAME_MINUTES = int(os.environ.get('TIMEFRAME_MINUTES', '15'))
OHLCV_LIMIT       = int(os.environ.get('OHLCV_LIMIT', '250'))

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID   = os.environ.get('TELEGRAM_CHAT_ID', '')

# --- LINE Notify (optional) ---
LINE_NOTIFY_TOKEN  = os.environ.get('LINE_NOTIFY_TOKEN', '')

# --- Notification channel: 'telegram' | 'line' | 'both' ---
NOTIFY_CHANNEL     = os.environ.get('NOTIFY_CHANNEL', 'telegram')

# --- Dry run (ทดสอบโดยไม่ส่งแจ้งเตือนจริง) ---
DRY_RUN            = os.environ.get('DRY_RUN', 'false').lower() == 'true'

# --- Timezone offset (ชม.) สำหรับแสดงเวลาในข้อความ (default 7 = Bangkok) ---
DISPLAY_TZ_OFFSET_HOURS = int(os.environ.get('TZ_OFFSET_HOURS', '7'))


# ============================================================
#  Pine Script Parameters (จากต้นฉบับ ห้ามแก้)
# ============================================================
DOMCYCLE     = 14
VIBRATION    = 10
LEVELING     = 7.0
CYCLICMEMORY = DOMCYCLE * 2      # = 28
CYCLELEN     = DOMCYCLE // 2     # = 7  (Pine int() truncates toward zero)

SMOOTHK     = 3
SMOOTHD     = 3
LENGTH_RSI  = 15
LENGTH_STOCH = 12

STOCH_LOW   = 10
STOCH_HIGH  = 90


# ============================================================
#  Helper Functions  (Pine Script equivalents)
# ============================================================

def is_nan(v):
    """ตรวจว่าค่าเป็น NaN หรือ None"""
    if v is None:
        return True
    if isinstance(v, float):
        return math.isnan(v)
    return False


def nz(value, default=0.0):
    """
    Pine Script nz(x, default):
      - ถ้า x ไม่ใช่ NaN/None  คืน x
      - ถ้า x เป็น NaN/None     คืน default
    """
    if is_nan(value):
        return default
    return value


def calc_rma(values, length):
    """
    Wilder's RMA (Modified Moving Average)  - ตรงกับ Pine ta.rma()
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

    # SMA seed
    window = values[start_idx - length + 1 : start_idx + 1]
    rma[start_idx] = sum(window) / length

    # Recursive formula (bar-by-bar, ห้าม vectorize)
    alpha = 1.0 / length
    for i in range(start_idx + 1, n):
        v = values[i]
        if is_nan(v):
            rma[i] = rma[i - 1]
        else:
            rma[i] = alpha * v + (1.0 - alpha) * rma[i - 1]
    return rma


def calc_sma(values, length):
    """Simple Moving Average  - ตรงกับ Pine ta.sma()"""
    n = len(values)
    sma = [float('nan')] * n
    for i in range(length - 1, n):
        window = values[i - length + 1 : i + 1]
        if any(is_nan(v) for v in window):
            continue
        sma[i] = sum(window) / length
    return sma


def calc_rsi(src, length):
    """
    Standard RSI ใช้ Wilder's smoothing  - ตรงกับ Pine ta.rsi()
       change = src - src[1]
       up   = rma(max(change, 0),   length)
       down = rma(max(-change, 0),  length)
       rsi  = down==0 ? 100 : up==0 ? 0 : 100 - 100/(1 + up/down)
    """
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
    """
    Stochastic  - ตรงกับ Pine ta.stoch(source, source, source, length)
       = 100 * (source - lowest(source, length))
              / (highest(source, length) - lowest(source, length))
    """
    n = len(source)
    stoch = [float('nan')] * n
    for i in range(length - 1, n):
        window = source[i - length + 1 : i + 1]
        valid  = [v for v in window if not is_nan(v)]
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
    """
    คำนวณ cRSI / db / ub / Stoch RSI / สัญญาณซื้อ-ขาย ทุก bar

    closes : list ราคาปิดเรียงเวลาจากอดีต -> ปัจจุบัน
    return : dict ของ list ทุก indicator + สัญญาณ
    """
    src = closes
    n = len(src)

    # -------- cRSI Parameters --------
    torque     = 2.0 / (VIBRATION + 1)               # = 0.1818...
    phasingLag = int((VIBRATION - 1) / 2)            # = 4   (Pine int())
    aperc      = LEVELING / 100.0                    # = 0.07

    # -------- [1] RSI สำหรับ cRSI (cyclelen=7) --------
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
    # var float crsi = 0.0
    # crsi := torque * (2 * rsi - rsi[phasingLag]) + (1 - torque) * nz(crsi[1])
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
        # หา lmax / lmin ในหน้าต่าง cyclicmemory
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

        # db: scan จาก lmin ขึ้นไป หา testvalue แรกที่ below/cyclicmemory >= aperc
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

        # ub: scan จาก lmax ลงลง หา testvalue แรกที่ above/cyclicmemory >= aperc
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
    # rsi1 = ta.rsi(src, lengthRSI=15)
    # k    = ta.sma(ta.stoch(rsi1, rsi1, rsi1, lengthStoch=12), smoothK=3)
    # d    = ta.sma(k, smoothD=3)
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

        # ta.crossover(k, d)
        if k_now > d_now and k_prev <= d_prev:
            last_crossup[i] = k_now
        # ta.crossunder(k, d)
        if k_now < d_now and k_prev >= d_prev:
            last_crossdown[i] = k_now

    # -------- [6] Buy / Sell Signals --------
    # buy_signal  = crossover(crsi, db)  AND last_stoch_k_crossup   < stoch_low  AND k < stoch_low
    # sell_signal = crossunder(crsi, ub) AND last_stoch_k_crossdown > stoch_high AND k > stoch_high
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
    """
    ดึง OHLCV จาก Bybit v5 public kline endpoint (ไม่ต้องใช้ API key)

    Returns: list ของ [timestamp_ms, open, high, low, close, volume]
             เรียงจากอดีต -> ปัจจุบัน (oldest first)
    """
    url = 'https://api.bybit.com/v5/market/kline'
    params = {
        'category': 'linear',
        'symbol':   symbol,
        'interval': str(interval),
        'limit':    str(limit),
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (GitHub-Actions-SignalBot)',
        'Accept':     'application/json',
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if data.get('retCode') != 0:
        raise Exception(f"Bybit API error: {data.get('retMsg', 'Unknown')}")

    klines = data['result']['list']
    if not klines:
        raise Exception('Bybit API returned empty kline list')

    # Bybit ส่งกลับ newest-first -> reverse เป็น oldest-first
    klines.reverse()

    ohlcv = []
    for kl in klines:
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
    """
    หา index ของแท่งเทียนที่ปิดตัวลงล่าสุด
    (แท่งสุดท้ายใน OHLCV อาจเป็นแท่งที่กำลัง form อยู่ -> ใช้แท่งก่อนหน้า)
    """
    now_ms          = int(time.time() * 1000)
    last_bar_open   = ohlcv[-1][0]
    last_bar_close  = last_bar_open + timeframe_minutes * 60 * 1000

    # buffer 5 วินาที เผื่อ exchange ยังไม่ update ข้อมูล
    if now_ms >= last_bar_close + 5000:
        return len(ohlcv) - 1
    return len(ohlcv) - 2


# ============================================================
#  Notifications  (Telegram + LINE Notify)
# ============================================================

def send_telegram(message):
    """ส่งข้อความเข้า Telegram ผ่าน Bot API"""
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
    """ส่งข้อความเข้า LINE Notify"""
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
    """ส่งแจ้งเตือนตาม channel ที่กำหนดใน NOTIFY_CHANNEL"""
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
    print(f'[INFO] DRY_RUN={DRY_RUN}  NOTIFY_CHANNEL={NOTIFY_CHANNEL}')

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

    # เตรียมข้อมูลเวลา (แสดงเป็นเวลาท้องถิ่น)
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
        # Telegram HTML format (LINE Notify จะ strip HTML tags อัตโนมัติ)
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
            f"LastCrossDown: {nz(result['last_crossdown'][idx], 0):.4f}"
        )
        notify(msg)

    # 5) สรุปผลลัพธ์ สำหรับ GitHub Actions log
    print()
    print('=' * 50)
    print(f'  Signal Result: {signal_type or "NONE"}')
    print('=' * 50)
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
    print('=' * 50)

    return {
        'signal':      signal_type or 'NONE',
        'buy_signal':  buy,
        'sell_signal': sell,
    }


# ============================================================
#  CLI Entry Point
# ============================================================
def main():
    """CLI entry สำหรับรันใน GitHub Actions (หรือ local)"""
    try:
        result = run_signal_check()
        # exit 0 เสมอเมื่อรันสำเร็จ (แม้ไม่มีสัญญาณ) เพื่อไม่ให้ GitHub Actions fail
        sys.exit(0)
    except Exception as e:
        print(f'[FATAL] {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
