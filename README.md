# 창고 수요예측 파이프라인 (Warehouse Demand Forecasting)

창고 입출고 데이터로부터 **화주(shipper)에게 제공할 주간 수요예측 정보**를 생성하는
재실행 가능한 파이프라인입니다. 일별 데이터를 주간으로 집계해 **향후 4주**를 예측하며,
**매주 1회** 실행하는 것을 전제로 설계되었습니다.

대상 데이터: ESSENCORE HK 센터의 입고/출고 데이터 (2023-06 ~ 2026-06, 156주).
반도체·메모리 유통 특성상 수요가 매우 **간헐적(intermittent)** 이라, 간헐수요 전용
기법(Croston 계열)이 핵심입니다.

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

### 대량 / 소량 출고

각 시계열의 **비영 주간 출고량 80퍼센타일 이상**을 그 대상의 **대량(大)** 으로 정의(상대 기준).

- **대량 출고 확률**: 대량 발생 주를 이진화 후 TSB 확률평활로 주간 발생확률 `p`를 추정 →
  4주 내 최소 1회 발생확률 `1−(1−p)⁴`. SKU·고객·채널별 제공(창고 공간·인력 사전계획용).
- **소량(정상) 출고 예측치**: 스파이크를 대량 임계값에서 winsorize 후 산출한 정상 수요의
  주간 기대치 → 고객별 4주 예측.

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
app.py                 Streamlit 웹 UI (파일 업로드 → 실행 → 리포트)
scripts/run_weekly.py  주간 실행 CLI
tests/test_core.py     핵심 로직 단위 테스트
config.yaml            설정값
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
