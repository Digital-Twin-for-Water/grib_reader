# grib_reader

기상청 동네예보(DFS) GRIB 파일에서 특정 위치(위·경도)의 시계열 데이터를 추출하는 Python 라이브러리입니다.

## 개요

기상청이 배포하는 동네예보 초단기예보(VSRT)·단기예보(SHRT) GRIB 파일을 읽어,
지정한 관측소(위·경도) 좌표에 가장 가까운 격자점의 값을 hourly 시계열로 추출합니다.
단일 지점 추출과 다중 지점 일괄 추출을 모두 지원합니다.

## 파일 구성

```
grib_reader/
├── read_grib_timeseries.py          # 핵심 라이브러리
├── extract_rainfall_forecast.py     # 다중 지점 추출 CLI 스크립트
├── grib_multipoint_timeseries.ipynb # 다중 지점 추출 탐색용 노트북
├── kr_rf_obs_st.csv                 # KMA 강수 관측소 목록 (전체)
├── kr_rf_obs_st_sample.csv          # KMA 강수 관측소 목록 (샘플)
├── kr_rf_forecast.csv               # 추출 결과 예시
├── requirements.txt                 # pip 의존성
└── forecast_rainfall/               # 샘플 GRIB 파일 폴더
```

## 설치 (의존 패키지)

```bash
# 기본 (read_kma_grib, read_grib_pygrib)
pip install -r requirements.txt

# xarray 방식 추가 사용 시 (conda-forge 필수)
conda install -c conda-forge eccodes cfgrib
pip install xarray
```

> **참고:** `cfgrib`은 `pip install cfgrib`만으로 설치가 되지 않는 경우가 있습니다.
> conda 환경에서 `conda install -c conda-forge eccodes cfgrib` 사용을 권장합니다.

---

## 다중 지점 일괄 추출

### CLI 스크립트 (권장)

`extract_rainfall_forecast.py`는 VSRT·SHRT 파일을 자동 감지해 병합하고, 모든 지점의 hourly 시계열을 CSV 한 파일로 저장합니다.

```bash
# 기본값으로 실행 (forecast_rainfall/ 폴더, kr_rf_obs_st.csv → kr_rf_forecast.csv)
python extract_rainfall_forecast.py

# 경로 직접 지정
python extract_rainfall_forecast.py \
  --data-folder forecast_rainfall \
  --points-csv kr_rf_obs_st_sample.csv \
  --output output.csv

# 파일 패턴 변경 (기본: *VSRT*PCP*, *SHRT*PCP*)
python extract_rainfall_forecast.py \
  --vsrt-glob "*VSRT*PCP*" \
  --shrt-glob "*SHRT*PCP*"
```

**CLI 인자:**

| 인자 | 기본값 | 설명 |
|---|---|---|
| `--data-folder` | `forecast_rainfall` | GRIB 파일이 있는 폴더 |
| `--points-csv` | `kr_rf_obs_st.csv` | 지점 목록 CSV |
| `--output` | `kr_rf_forecast.csv` | 출력 CSV 경로 |
| `--vsrt-glob` | `*VSRT*PCP*` | VSRT 파일 검색 패턴 |
| `--shrt-glob` | `*SHRT*PCP*` | SHRT 파일 검색 패턴 |

**지점 목록 CSV 형식** (UTF-8 또는 CP949):

```csv
name,lat,lon,code
서울시청,37.5665,126.9780,108
부산,35.1796,129.0756,159
```

열 이름은 유연하게 인식합니다: `name`/`point_name`, `lat`/`y`/`latitude`, `lon`/`x`/`longitude`, `code`(선택).

**출력 CSV 컬럼:**

| 컬럼 | 설명 |
|---|---|
| `point_name` | 지점 이름 |
| `point_code` | 지점 코드 (없으면 빈 문자열) |
| `base_time` | 예보 발표 시각 |
| `forecast_hour` | 발표 시각 기준 예보 시간 수 |
| `valid_time` | 유효 시각 |
| `variable` | 변수 종류 (예: `PCP`) |
| `value` | 격자 값 |
| `forecast_type` | 데이터 출처 (`VSRT` / `SHRT`) |

### 탐색용 노트북

데이터 품질 확인이나 단계별 탐색이 필요할 때 사용합니다.

```bash
jupyter notebook grib_multipoint_timeseries.ipynb
```

---

## 라이브러리 직접 사용

### `read_kma_grib_merged` — VSRT + SHRT 병합 (권장 진입점)

```python
from read_grib_timeseries import read_kma_grib_merged
from pathlib import Path

df = read_kma_grib_merged(
    Path("forecast_rainfall"),
    target_lat=37.5665,
    target_lon=126.9780,
    vsrt_glob="*VSRT*PCP*",
    shrt_glob="*SHRT*PCP*",
)
print(df)
```

VSRT(초단기) 10분 데이터를 1시간 합산 후 SHRT(단기)와 이어 붙입니다. 겹치는 시각은 VSRT 우선.

---

### `read_kma_grib` — VSRT 또는 SHRT 단독 읽기

```python
from read_grib_timeseries import read_kma_grib

file_list = ["forecast_rainfall/DFS_SHRT_GRD_GRB5_PCP.202605102000"]
df = read_kma_grib(file_list, target_lat=37.5665, target_lon=126.9780)
print(df)
```

반환 컬럼: `base_time`, `forecast_hour`, `valid_time`, `variable`, `value`, `units`

---

### `read_grib_pygrib` — pygrib 범용

변수·레벨 필터링 등 세밀한 제어가 필요할 때 사용합니다.

```python
from read_grib_timeseries import read_grib_pygrib

df = read_grib_pygrib(file_list, target_lat=37.5665, target_lon=126.9780,
                      variable_name='Total precipitation')
```

---

### `read_grib_xarray` — xarray + cfgrib

범용 GRIB2 파일 읽기. `eccodes`와 `cfgrib`가 설치된 환경에서 사용합니다.

```python
from read_grib_timeseries import read_grib_xarray

df = read_grib_xarray(file_list, target_lat=37.5665, target_lon=126.9780)
```

---

### `KMAGridConverter` — 격자 좌표 변환기

위경도 ↔ 기상청 동네예보 Lambert Conformal Conic 격자 좌표를 직접 변환합니다.

```python
from read_grib_timeseries import KMAGridConverter

conv = KMAGridConverter()
x, y = conv.latlon_to_grid(37.5665, 126.9780)   # 위경도 → 격자
lat, lon = conv.grid_to_latlon(x, y)             # 격자 → 위경도
```

---

## GRIB 파일명 규칙

```
DFS_VSRT_GRD_GRB6_PCP.202605102000_202605110520
    ^^^^          ^^^^^^^^^^^^  ^^^^^^^^^^^^
    종류           base_time     end_time
    (VSRT/SHRT)   (YYYYMMDDHHmm)
```

| 구성 | 설명 |
|---|---|
| `VSRT` / `SHRT` | 초단기예보 / 단기예보 |
| `GRD` | 격자 데이터 |
| `GRB5` / `GRB6` | GRIB 버전 |
| `PCP` | 변수 (강수량) |
| `YYYYMMDDHHmm` | 발표 시각 |

---

## 라이선스

[LICENSE](LICENSE) 파일을 확인하세요.
