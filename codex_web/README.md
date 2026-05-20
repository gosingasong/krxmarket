# KRX Market Notebook

GitHub Pages에 올리는 개인용 시장 데이터 노트입니다. `0_krx_alert_bot_v8.py`는 사용하지 않고, `codex_web` 안의 독립 fetcher가 공개 데이터를 수집해 날짜별 JSON을 생성합니다.

## 포함 데이터

- `investor_flow`: 전일 KRX 기관합계/외국인 매수금액 랭킹
- `ipo`: 오늘 거래일 / 다음 거래일 신규상장 예정 종목
- `krx_alert`: 다음 거래일 투자경고 해제/지정/재지정 시뮬레이션
- `us_market`: 미국 주요 지수/섹터와 거래대금 상위 종목
- `nxt_market`: NXT 누적 거래대금
- `liquidity`: 예탁금, 신용, KOSPI/KOSDAQ KRX+NXT 거래대금

업종쏠림지수처럼 Excel/COM을 쓰는 리포트는 제외했습니다.

## 구조

```text
codex_web/
  update_reports.py
  requirements.txt
  state/                         # 투자경고 후보 상태 파일
  src/codex_web/
    reports.py
    sources/                     # KRX, IPO, US, NXT, liquidity 독립 fetcher
  docs/                          # GitHub Pages 배포 대상
    index.html
    app.js
    styles.css
    data/
      index.json
      YYYY-MM-DD/
        investor_flow.json
        ipo.json
        krx_alert.json
        us_market.json
        nxt_market.json
        liquidity.json
        manifest.json
```

## 실행

Python 3.10 이상을 권장합니다.

```powershell
python -m pip install -r codex_web/requirements.txt
python codex_web/update_reports.py --reports default --verbose
```

특정 날짜:

```powershell
python codex_web/update_reports.py --date 2026-05-20 --reports default
```

수급 전체 행 저장:

```powershell
python codex_web/update_reports.py --reports investor_flow --flow-limit 0
```

## 로컬 미리보기

```powershell
cd codex_web/docs
python -m http.server 8010
```

브라우저에서 엽니다.

```text
http://127.0.0.1:8010/
```

## GitHub Pages

새 repo:

```text
https://github.com/gosingasong/krxmarket
```

권장 방식은 GitHub Actions 배포입니다.

1. `codex_web` 폴더를 repo에 올립니다.
2. `codex_web/github-actions/update_reports.example.yml`을 repo 루트의 `.github/workflows/update_reports.yml`로 복사합니다.
3. GitHub repo의 `Settings > Pages`에서 `Source`를 `GitHub Actions`로 설정합니다.
4. `Actions > Update Codex Web Data > Run workflow`로 수동 실행합니다.

성공하면 Pages 주소는 보통 아래 중 하나입니다.

```text
https://gosingasong.github.io/krxmarket/
```

또는 repo 이름을 `gosingasong.github.io`로 쓰면:

```text
https://gosingasong.github.io/
```

## 메모장

웹 화면의 메모장은 서버에 저장하지 않고 브라우저 `localStorage`에 저장합니다. 고정 메모는 날짜가 바뀌어도 유지되고, 일일 메모는 날짜별로 따로 저장됩니다. 같은 브라우저/기기에서는 유지되지만, 다른 PC나 휴대폰으로 자동 동기화되지는 않습니다.

## 배포 메모

- GitHub Actions 스케줄은 기존 텔레그램 봇 시간에 맞춰 나눠져 있습니다: 미국장 06:59, IPO 15:20, 전일 수급용 데이터 18:01, 유동성/NXT 20:10, 다음 거래일 Risk Watch 20:25 KST.
- KRX/KIND/Finviz가 GitHub Actions 서버 요청을 막으면, 로컬 PC에서 `update_reports.py`를 작업 스케줄러로 실행한 뒤 `docs/data`와 `state`를 push하는 방식으로 바꾸면 됩니다.
- 투자경고 분석은 이미지에서 잘라 보여주던 개수 제한을 쓰지 않고, 필터를 통과한 전체 데이터를 JSON으로 저장합니다.
- `update_reports.py`는 기본적으로 `docs/data/YYYY-MM-DD` 폴더 중 60일보다 오래된 데이터를 삭제하되, 최신 20개 날짜 폴더는 항상 보존합니다. 필요하면 `--prune-days`, `--prune-keep-min`으로 조정합니다.
- GitHub Actions는 보고서 생성 실패 시 `docs/data/workflow_status.json`에 실패 상태를 기록해 배포하고, 웹 화면의 일일 메모 아래 알림 창에 표시합니다.
