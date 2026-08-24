#!/usr/bin/env python3
"""GitHub Actions 일일 빌드.

오늘(또는 지정일) 종가로 삼성전자·SK하이닉스의 코스피 시총 비중 한 줄을 추가하고
docs/index.html 의 차트 데이터를 갱신한다.

- 평일 실행(기본): 삼전·하닉만 실측하고 분모는 최근 앵커 × 지수변동률로 환산. 빠름.
- --full: 전종목 실측으로 분모를 새로 잡는다(앵커). 주말 1회.

멱등하다. 같은 날짜가 이미 있으면(그리고 --force 아니면) 아무것도 하지 않는다.
휴장이면 해당일 코스피 시세가 없으므로 역시 아무것도 하지 않는다.

경로는 모두 이 파일 기준 상대경로라, 저장소를 어디에 두든 동작한다.

사용법:
    python3 build.py                 # 오늘, 경량
    python3 build.py 20260821        # 특정일, 경량
    python3 build.py --full          # 오늘, 전종목 실측
    python3 build.py 20260821 --full --force
"""
import json, re, csv, sys, os, time
import urllib.request
import concurrent.futures as cf
from datetime import datetime, timezone, timedelta

BASE  = os.path.dirname(os.path.abspath(__file__))
DATA  = os.path.join(BASE, 'data')
DOCS  = os.path.join(BASE, 'docs')
KST   = timezone(timedelta(hours=9))
H     = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.naver.com/'}


def log(msg):
    print(f'[{datetime.now(KST):%Y-%m-%d %H:%M:%S}] {msg}', flush=True)


def fetch(url, timeout=30, tries=3):
    last = None
    for _ in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=H), timeout=timeout).read()
        except Exception as e:
            last = e
            time.sleep(1)
    raise last


def sise(symbol, start, end):
    u = (f'https://api.finance.naver.com/siseJson.naver?symbol={symbol}'
         f'&requestType=1&startTime={start}&endTime={end}&timeframe=day')
    txt = fetch(u).decode('utf-8', 'replace').replace("'", '"')
    rows = json.loads(re.sub(r',\s*\]', ']', txt.strip()))
    return {str(r[0]): r[4] for r in rows[1:]
            if r and str(r[0]).isdigit() and isinstance(r[4], (int, float))}


def main():
    args  = [a for a in sys.argv[1:] if not a.startswith('--')]
    force = '--force' in sys.argv
    full  = '--full'  in sys.argv
    day   = args[0] if args else datetime.now(KST).strftime('%Y%m%d')
    iso   = f'{day[:4]}-{day[4:6]}-{day[6:]}'

    rows = json.load(open(f'{DATA}/daily_weights.json'))
    byd  = {r['date']: r for r in rows}
    if iso in byd and not force:
        log(f'{iso} 이미 존재 — 종료'); return 0

    kospi = sise('KOSPI', day, day)
    if day not in kospi:
        log(f'{iso} 코스피 시세 없음 (휴장 또는 미마감) — 종료'); return 0
    kv = kospi[day]

    universe = json.load(open(f'{DATA}/universe.json'))
    SH_S = universe['005930']['shares']
    SH_H = universe['000660']['shares']

    if full:
        etf   = set(json.load(open(f'{DATA}/etf.json')))
        codes = [c for c in universe if c not in etf]
        log(f'{iso} 코스피 {kv:,.2f} — 전종목 {len(codes)}개 수집')

        def one(code):
            try:    return code, sise(code, day, day).get(day)
            except Exception: return code, None

        px, fails = {}, 0
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for code, p in ex.map(one, codes):
                if p is None: fails += 1
                else: px[code] = p
        log(f'수집 {len(px)}종목 / 미수집 {fails}종목')
        if len(px) < len(codes) * 0.9:
            log('수집률 90% 미만 — 중단'); return 1
        if '005930' not in px or '000660' not in px:
            log('삼전/하닉 시세 없음 — 중단'); return 1

        total = sum(universe[c]['shares'] * p for c, p in px.items())
        sec, hyn = SH_S * px['005930'], SH_H * px['000660']
        n_stocks, method = len(px), 'full'
    else:
        anchor = next((r for r in reversed([byd[k] for k in sorted(byd)])
                       if r.get('method', 'full') == 'full' and r['date'] < iso), None)
        if anchor is None:
            log('앵커(전종목 실측일)를 찾지 못함 — --full 로 실행 필요'); return 1
        ad = anchor['date'].replace('-', '')
        ak = sise('KOSPI', ad, ad).get(ad)
        if not ak:
            log(f'앵커일 {anchor["date"]} 지수 조회 실패 — 중단'); return 1

        ps = sise('005930', day, day).get(day)
        ph = sise('000660', day, day).get(day)
        if not ps or not ph:
            log('삼전/하닉 시세 없음 — 중단'); return 1

        total = anchor['total_jo'] * 1e12 * (kv / ak)
        sec, hyn = SH_S * ps, SH_H * ph
        n_stocks, method = anchor['n_stocks'], 'fast'
        log(f'{iso} 코스피 {kv:,.2f} — 경량 (앵커 {anchor["date"]}, '
            f'삼전 {ps:,} / 하닉 {ph:,})')

    byd[iso] = {
        'date': iso, 'kospi': round(kv, 2),
        'total_jo': round(total / 1e12, 1),
        'samsung_pct': round(sec / total * 100, 3),
        'hynix_pct':   round(hyn / total * 100, 3),
        'sum_pct':     round((sec + hyn) / total * 100, 3),
        'n_stocks': n_stocks, 'method': method,
    }
    r = byd[iso]
    log(f"삼전 {r['samsung_pct']:.2f}%  하닉 {r['hynix_pct']:.2f}%  "
        f"합계 {r['sum_pct']:.2f}%  총시총 {r['total_jo']:,.0f}조")

    out = [byd[k] for k in sorted(byd)]

    def save(path, writer):
        tmp = path + '.tmp'
        with open(tmp, 'w', newline='') as f: writer(f)
        os.replace(tmp, path)

    save(f'{DATA}/daily_weights.json', lambda f: json.dump(out, f))
    def _csv(f):
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    save(f'{DATA}/daily_weights.csv', _csv)
    cd = {'d': [x['date'] for x in out], 's': [x['samsung_pct'] for x in out],
          'h': [x['hynix_pct'] for x in out], 'm': [x['sum_pct'] for x in out],
          'k': [x['kospi'] for x in out], 't': [x['total_jo'] for x in out]}
    save(f'{DATA}/chartdata.json', lambda f: json.dump(cd, f, separators=(',', ':')))

    log(f'데이터 저장 완료 — 총 {len(out)}거래일 ({out[0]["date"]} ~ {out[-1]["date"]})')
    render(cd)
    return 0


def render(cd):
    """docs/index.html 의 데이터 부분(const D = {...};)만 교체한다."""
    page = os.path.join(DOCS, 'index.html')
    if not os.path.exists(page):
        log('docs/index.html 없음 — 렌더 건너뜀'); return
    h = open(page).read()
    h2 = re.sub(r'const D = \{.*?\};\nconst N',
                'const D = ' + json.dumps(cd, separators=(',', ':')) + ';\nconst N',
                h, count=1, flags=re.S)
    if h2 != h:
        tmp = page + '.tmp'
        open(tmp, 'w').write(h2)
        os.replace(tmp, page)
        log('docs/index.html 데이터 갱신 완료')
    else:
        log('docs/index.html 치환 실패 — 형식 확인 필요 (const D 패턴 불일치)')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        log(f'ERROR {type(e).__name__}: {e}')
        sys.exit(1)
