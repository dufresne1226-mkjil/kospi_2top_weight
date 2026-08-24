# 코스피 시총 비중 트래커

삼성전자와 SK하이닉스가 코스피 전체 시가총액에서 차지하는 비중을
매 거래일 종가 기준으로 자동 적재하고, 차트를 GitHub Pages로 배포한다.

**라이브 차트:** (배포 후 URL 기입) `https://<user>.github.io/<repo>/`

## 구조

```
build.py                 일일 적재 + docs/index.html 데이터 갱신
refresh_universe.py      상장주식수·신규상장·ETF 목록 갱신 (주 1회)
docs/index.html          차트 (GitHub Pages가 서빙)
data/daily_weights.csv   결과 — date,kospi,total_jo,samsung_pct,hynix_pct,sum_pct,n_stocks,method
data/*.json              차트 주입용·집계용 원본
.github/workflows/
  daily.yml              평일 16:42 KST 경량 적재 → 커밋 → Pages 배포
  weekly.yml             토 07:28 KST 유니버스 갱신 + 금요일 전종목 재계산(앵커)
```

## 자동화

| 워크플로우 | 시각(KST) | 하는 일 |
|---|---|---|
| daily | 평일 16:42 | 삼전·하닉만 실측, 분모는 앵커×지수변동률로 환산 (빠름) |
| weekly | 토 07:28 | 전종목 실측으로 분모(앵커) 재설정 + 상장주식수 갱신 |

`daily` 는 매일 한 줄 덧붙이며 오차가 조금씩 쌓일 수 있으므로, `weekly` 가
주 1회 전종목 실측으로 앵커를 다시 박아 오차를 리셋한다. 각 행의 `method`
컬럼(`full`/`fast`)으로 어느 값이 실측인지 구분된다.

## 산출 방식

코스피 상장 종목(ETF 제외)의 `상장주식수 × 종가` 합산이 분모, 삼전·하닉
보통주 시총이 분자. 우선주는 분자에서 제외. 데이터 출처는 네이버 금융
일별시세 API(`api.finance.naver.com`, 키 불필요).

## 안전장치

- **멱등** — 같은 날짜가 이미 있으면 아무것도 안 함.
- **휴장 자동 판별** — 그날 코스피 시세가 없으면 종료. 공휴일 달력 불필요.
- **수집률 가드** — `--full` 에서 종목 수집률 90% 미만이면 기록 안 하고 종료.
- **원자적 쓰기** — `.tmp` 에 쓴 뒤 `os.replace`.
- 워크플로우는 데이터·페이지 커밋이 자기 자신을 재트리거하지 않도록
  `paths-ignore: [data/**, docs/**]` 처리.

## 수동 실행

```bash
python3 build.py                       # 오늘 경량
python3 build.py 20260821              # 특정일 경량
python3 build.py 20260821 --full --force   # 전종목 실측
python3 refresh_universe.py
```

## 로컬 crontab 은?

이 저장소로 옮기기 전에는 `/work/djchoi/Claude_ground/kospi_weight/` 에서
로컬 crontab 으로 돌렸다. GitHub Actions 로 이관한 뒤에는 로컬 crontab 을
비활성화해 이중 적재를 막는다.
