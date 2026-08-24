#!/usr/bin/env python3
"""코스피 종목 유니버스(상장주식수·ETF 목록)를 다시 받아 저장한다.

상장주식수는 증자·자사주 소각으로 바뀌고 신규상장·상장폐지도 계속 생기므로,
주 1회 정도 갱신해 두어야 append_today.py 의 분모가 현실과 어긋나지 않는다.
기존 파일은 실패 시 보존되고, 정상 수집된 경우에만 원자적으로 교체된다.
"""
import re, json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
KST  = timezone(timedelta(hours=9))
H    = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def log(m): print(f'[{datetime.now(KST):%Y-%m-%d %H:%M:%S}] {m}', flush=True)

def get(url, enc='euc-kr'):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=H), timeout=30).read().decode(enc, 'replace')

def main():
    # ETF 목록
    raw = get('https://finance.naver.com/api/sise/etfItemList.nhn')
    etf = sorted({x['itemcode'] for x in json.loads(raw)['result']['etfItemList']})
    log(f'ETF {len(etf)}종목')

    # 전종목 시가총액 페이지
    h1 = get('https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1')
    maxpage = max(int(x) for x in re.findall(r'page=(\d+)', h1)) if 'page=' in h1 else 1
    stocks = {}
    for n in range(1, maxpage + 1):
        h = h1 if n == 1 else get(
            f'https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page={n}')
        for code, name, rest in re.findall(
                r'<a href="/item/main\.naver\?code=(\d{6})"[^>]*>([^<]+)</a>(.*?)</tr>', h, re.S):
            nums = re.findall(r'<td[^>]*>\s*([\d,]+)\s*</td>', rest)
            if len(nums) < 4: continue
            try:
                price = int(nums[0].replace(',', ''))
                mcap  = int(nums[2].replace(',', ''))    # 억원
                shrs  = int(nums[3].replace(',', ''))    # 천주
            except ValueError:
                continue
            # 정합성: 시총(억) ≈ 주식수(천주) × 주가 / 1e5
            if not (0.97 < (shrs * price / 1e5) / max(mcap, 1) < 1.03): continue
            stocks[code] = {'name': name.strip(), 'price': price,
                            'mcap_eok': mcap, 'shares': shrs * 1000}
        time.sleep(0.12)

    log(f'전종목 {len(stocks)} (ETF 제외 {len(stocks) - len(set(etf) & set(stocks))})')
    if len(stocks) < 1000 or '005930' not in stocks or '000660' not in stocks:
        log('수집 결과 이상 — 기존 파일 유지하고 중단'); return 1

    prev = {}
    p = f'{DATA}/universe.json'
    if os.path.exists(p): prev = json.load(open(p))
    added   = set(stocks) - set(prev)
    removed = set(prev) - set(stocks)
    changed = [c for c in set(stocks) & set(prev)
               if stocks[c]['shares'] != prev[c]['shares']]
    log(f'신규 {len(added)} · 제외 {len(removed)} · 주식수변동 {len(changed)}')
    for c in list(changed)[:10]:
        log(f"   {stocks[c]['name']}: {prev[c]['shares']:,} → {stocks[c]['shares']:,}")

    for path, obj in ((p, stocks), (f'{DATA}/etf.json', etf)):
        tmp = path + '.tmp'
        json.dump(obj, open(tmp, 'w'), ensure_ascii=False)
        os.replace(tmp, path)
    log('유니버스 갱신 완료')
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f'ERROR {type(e).__name__}: {e}')
        sys.exit(1)
