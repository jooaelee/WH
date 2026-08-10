# 창고 수요예측 파이프라인 (Warehouse Demand Forecasting)

창고 입출고 데이터로부터 **화주(shipper)에게 제공할 주간 수요예측 정보**를 생성하는
재실행 가능한 파이프라인입니다. 일별 데이터를 주간으로 집계해 **향후 4주**를 예측하며,
**매주 1회** 실행하는 것을 전제로 설계되었습니다.

대상 데이터: ESSENCORE HK 센터의 입고/출고 데이터 (2023-06 ~ 2026-06, 156주).
반도체·메모리 유통 특성상 수요가 매우 **간헐적(intermittent)** 이라, 간헐수요 전용
기법(Croston 계열)이 핵심입니다.

---

## 🖱️ 가장 쉬운 실행 방법 (더블클릭)

터미널/명령어 없이 실행하려면:

1. **Python 설치** (컴퓨터 1대당 최초 1회만): [python.org/downloads](https://www.python.org/downloads/) 에서
   설치파일을 받아 실행 — 설치 화면에서 **"Add python.exe to PATH"** 체크박스를 꼭 체크하세요.
2. 이 저장소를 내려받아 압축을 풉니다 (GitHub의 초록색 **Code → Download ZIP** 버튼).
3. 압축을 푼 폴더에서 아래 표에 맞는 파일을 더블클릭합니다.

| 파일 | 언제 사용 | 동작 |
|---|---|---|
| **`Run.bat`** (Windows) / **`Run_Mac.command`** (Mac) | **맨 처음 한 번은 반드시 이걸로** | 검은 창이 뜨고 설치 과정·오류가 그대로 보입니다 |
| **`Start.vbs`** (Windows 전용) | 최초 설치가 끝난 **다음부터** | 검은 창 없이 macOS 앱처럼 더블클릭 → 몇 초 후 브라우저만 뜹니다 |
| **`Stop.bat`** (Windows 전용) | `Start.vbs`로 조용히 실행 중인 걸 끌 때 | 창이 안 보이므로 이 파일로 종료합니다 |

macOS에서 "확인되지 않은 개발자" 경고가 뜨면, 파일에서 마우스 우클릭 → **열기** → **열기**로
확인하세요.

**처음 사용하실 때 순서**: `Run.bat` 더블클릭 → 검은 창에서 설치 진행 확인 → 브라우저가 열리고
정상 작동하는지 확인 → 창을 닫아 종료 → **다음부터는 `Start.vbs`** 를 쓰시면 검은 창 없이 바로
열립니다 (다른 분이 쓰시던 macOS `.app`과 동일한 느낌입니다).

> 참고: 이 방식은 Python을 최초 1회 설치해야 합니다. Python 설치 자체가 필요 없는 완전
> 독립 실행파일(.exe)이 필요하시면 별도로 요청해주세요 (검증에 시간이 더 필요합니다).

**Windows에서 더블클릭해도 실행이 안 될 때:**
- 파일명에 한글이 들어간 예전 버전(`실행하기.bat`)을 갖고 계시다면, 압축 해제 과정에서
  한글 파일명이 깨져 실행 자체가 안 될 수 있습니다. 저장소를 다시 내려받아 영문 파일명인
  **`Run.bat`** 을 사용해주세요.
- `Run.bat`을 더블클릭했는데 창이 뜨자마자 사라지거나 "내부 또는 외부 명령이 아닙니다" 오류가
  뜨면, 압축이 제대로 풀리지 않았을 가능성이 큽니다 — 압축 프로그램(반디집 등)으로 다시 풀어보세요.
- Python 설치 후에도 안 되면, 예전에 `python`이라고만 쳤을 때 **Microsoft Store**가 열린 적이
  있는지 확인하세요. 그런 경우 진짜 Python이 아니라 스토어로 연결하는 빈 껍데기만 설치된
  것입니다 — 설정 → 앱 → 고급 앱 설정 → 앱 실행 별칭에서 `python.exe`/`python3.exe`를 끄고,
  [python.org](https://www.python.org/downloads/)에서 정식 설치 프로그램으로 다시 설치하세요.

---

## 무엇을 하는가

요청하신 기능을 그대로 파이프라인 단계로 구현했습니다.

| 단계 | 요구사항 | 구현 |
|---|---|---|
| 1 | 파일 입력(입고/출고/재고현황) | `data_loader` — CP949 인코딩·공백·`YYYYMMDD` 정리, 주간 집계. 재고 파일이 없으면 입고−출고 누적으로 **재고 추정** |
| 2 | SKU 특성 분석·라벨링 + 예측 대상 선정 | `classification` — Syntetos–Boylan(ADI·CV²)로 **교체형/지속형** 라벨링, **물량 상위 20%**(SKU·고객) 대상 선정 |
| 3 | 라벨별 다른 알고리즘 | `models` — **교체형 → Croston·SBA·TSB**, **지속형 → SES·Holt·MA·Seasonal-Naive** |
| 4 | 정확도 평가·피처 조정 (약 10회) | `tuning`+`backtest` — 시계열마다 **최대 10개 후보**를 rolling-origin 백테스트(RMSSE)로 평가해 최적 선택 |
| 5 | 새 데이터 입력 시 모델 고도화 | `registry` — 시계열별 챔피언 모델·정확도 이력 저장, **champion–challenger**로 새 데이터에서 점진 개선 |
| 6 | 리포트 생성 | `report` — **대량 출고 확률**(SKU·고객·채널) + **소량 출고 예측치**(고객별)를 CSV + HTML 대시보드로 |

---

## 웹 UI (파일 업로드 → 실행)

파일을 직접 올려서 실행하고 리포트를 바로 보고 싶다면 Streamlit 앱을 쓰세요.

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 **출고·입고(및 선택적 재고) CSV를 업로드**하고, 사이드바에서 기준일·예측
구간·대량 임계 등을 조정한 뒤 **[예측 실행]** 을 누르면 리포트가 화면에 표시되고 모든
결과를 내려받을 수 있습니다. CP949/UTF-8 인코딩을 자동 처리합니다. 같은 **작업
디렉터리**로 매주 실행하면 모델 상태(레지스트리)가 유지되어 정확도가 누적 개선(고도화)됩니다.

## CLI 실행 (자동화/배치)

```bash
pip install -r requirements.txt

# 데이터가 있는 디렉터리를 --data-dir 로 지정 (기본 파일명은 config.yaml 참조)
python scripts/run_weekly.py --config config.yaml --data-dir /path/to/data

# as-of(기준일) 고정 실행 — 미지정 시 데이터의 최신일 사용
python scripts/run_weekly.py --config config.yaml --data-dir /path/to/data --as-of 2026-06-11
```

산출물은 `outputs/` 에 생성됩니다:

| 파일 | 내용 |
|---|---|
| `report.html` | 화주용 시각화 대시보드 (라이트/다크 테마, 단일 파일) |
| `forecast_4weeks.csv` | 대상 시계열별 4주 예측치(주별) + 선택 모델·정확도 |
| `large_shipment_probability.csv` | 대량 출고 확률 (SKU·고객·채널 및 교차) |
| `small_volume_forecast_by_customer.csv` | 고객별 소량(정상) 출고 예측치 |
| `sku_classification.csv` | 전 시계열 특성·라벨·대상 여부 |
| `registry.json` | 모델 레지스트리·정확도 이력 (고도화 상태) |

`outputs/sample/` 에 실제 데이터로 실행한 예시 산출물이 포함되어 있습니다.

### 정확도 검증 (out-of-sample holdout)

파이프라인 내부의 RMSSE/MASE는 모델 선택에도 쓰이는 지표라 실제 미래 성능보다 낙관적으로 보일 수
있습니다. 최근 N주를 가리고 그 이전 데이터만으로 예측한 뒤 실제 값과 비교하는 진짜 out-of-sample
검증은 다음으로 실행합니다.

```bash
python scripts/validate_holdout.py --config config.yaml --data-dir /path/to/data --holdout-weeks 4
```

결과는 `outputs/holdout_validation/accuracy.csv`(RMSSE/sMAPE)와 `large_calibration.csv`(대량출고
확률 캘리브레이션)로 저장됩니다. `outputs/holdout_validation/`에 실제 데이터 실행 예시가 포함되어
있습니다 (2,019개 시계열 평가, 나이브 대비 87.7% 우수).

### 매주 자동 실행 (cron 예시)

```cron
0 6 * * 1  cd /repo && python scripts/run_weekly.py --config config.yaml --data-dir /data
```

---

## 방법론

### 교체형 vs 지속형 (라벨링)

각 주간 시계열의 **ADI**(평균 수요간격)와 **CV²**(비영 수요의 변동계수 제곱)를 계산합니다.

- **지속형(continuous)**: `ADI < 1.32` **그리고** 최근 52주 중 40% 이상 활성 → 규칙적 수요.
  시계열 모델(SES/Holt/MA) 적용.
- **교체형(intermittent)**: 그 외(간헐·lumpy·erratic) → Croston 계열 적용.

> 본 데이터는 대부분 SKU가 드물게 출고되어 **거의 전량이 교체형**입니다. 규칙적으로
> 출고되는 일부 출고채널(DHL·TAIUN 등)만 지속형으로 분류되어 시계열 모델이 적용됩니다.

### 간헐수요 모델 (교체형)

- **Croston**: 수요 크기(z)와 수요간격(p)을 각각 지수평활 → 주당 예측률 `z/p`.
- **SBA**(Syntetos–Boylan): Croston의 양의 편향을 `(1−α/2)`로 보정 — 간헐수요 권장 기본값.
- **TSB**(Teunter–Syntetos–Babai): 매 주 **수요 발생확률 p**를 갱신 → 단종성 품목에 강건하고,
  이 발생확률을 **대량 출고 확률** 산출에 재사용.

### 정확도 평가·모델 선택 (약 10회 탐색)

시계열마다 최대 10개 후보 설정(예: SBA α∈{0.05,0.1,0.15,0.2,0.3}, TSB (α,β) 조합, Croston α)을
**rolling-origin 백테스트**로 평가합니다. 4주 누적 수요를 대상으로 **RMSSE**(나이브 대비 스케일)를
최소화하는 설정을 선택합니다. 간헐수요에서는 개별 시점 sMAPE가 포화(2.0)되므로, 헤드라인
지표로는 **나이브 대비 우수 비율(RMSSE<1)** 을 함께 제시합니다.

### 고도화 (새 데이터 반영)

매 실행마다 최신 데이터로 재평가하되, 직전 실행에서 선택된 모델을 **챔피언**으로 함께
경쟁시킵니다. 도전 모델이 챔피언을 **2% 이상** 능가할 때만 교체하여 안정적으로 개선합니다.
시계열별 정확도 이력(`accuracy_history`)이 누적되어 주 단위 성능 추이를 추적합니다.

### 대량 / 소량 출고 (기본: 출고채널 기준)

`split_mode: channel` (기본) — **출고채널 성격**으로 구분합니다.

- **소량 = 특송(DHL·FedEx·UPS)** — 소포성 출고. 본 데이터에서 **주문건수의 ~37%지만 물량은 0.3%**.
- **대량 = 비특송(TAIUN·TAIUN_AIR·CUSTOMER_PICK_UP 등 화물·픽업)** — 소건이지만 물량의 대부분.

산출:
- **대량 출고 확률**: 비특송 채널 출고 발생 주를 이진화 → TSB 확률평활로 주간 발생확률 `p` →
  4주 내 최소 1회 발생확률 `1−(1−p)⁴`. **SKU·고객·비특송 채널별** 제공(창고 공간·인력 사전계획용).
- **소량 출고 예측치**: 특송 채널로 나가는 출고량의 주간 기대치 → **고객별** 4주 예측(특송비·포장 계획용).

특송 채널 목록은 `express_channels`로 조정합니다. `split_mode: quantile`로 두면 이전 방식
(각 대상의 비영 주간 출고량 `large_quantile` 퍼센타일 이상을 대량으로 보는 상대 기준)도 사용 가능합니다.

---

## 구조

```
demand_forecast/
  config.py          설정 (config.yaml 로 오버라이드)
  data_loader.py     입력 적재·정리·주간 집계·재고 추정
  classification.py  ADI/CV² 라벨링 + 상위 20% 대상 선정
  models/
    intermittent.py  Croston · SBA · TSB       (교체형)
    timeseries.py    SES · Holt · MA · S-Naive  (지속형)
    factory.py       라벨별 후보 모델 집합
  backtest.py        rolling-origin 백테스트 + 지표(RMSSE/MASE/sMAPE)
  tuning.py          시계열별 ~10회 탐색·최적 선택·챔피언 경쟁
  forecast.py        4주 예측 + 대량확률 + 소량예측 산출
  registry.py        모델·정확도 이력 영속화 (고도화)
  report.py          CSV + HTML 대시보드 생성
  pipeline.py        전체 오케스트레이션
app.py                       Streamlit 웹 UI (파일 업로드 → 실행 → 리포트)
scripts/run_weekly.py        주간 실행 CLI
scripts/validate_holdout.py  Out-of-sample 정확도 검증 (홀드아웃)
tests/test_core.py           핵심 로직 단위 테스트
config.yaml                  설정값
```

## 테스트

```bash
python tests/test_core.py         # 또는: python -m pytest tests/ -q
```

## 입력 데이터 스키마 (요약)

- **출고(Outbound)**: `Out Date`, `Customer`, `Item Code`, `DCM_NM`(출고채널), `Out Type`,
  `Quantity` … 고객 수요는 `Out Type = Sales` 만 사용.
- **입고(Inbound)**: `Inbound Date`, `Item Code`, `Quantity` … 재고 추정·리드 신호에 사용.
- **재고현황(선택)**: 미제공 시 입고−출고 누적으로 주간 마감재고를 추정.
