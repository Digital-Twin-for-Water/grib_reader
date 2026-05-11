# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

Extracts hourly time-series data from KMA (Korea Meteorological Administration) DFS (동네예보) GRIB files at specific lat/lon locations. Supports single-point and multi-point extraction. The core library is `read_grib_timeseries.py`; the Jupyter notebook `grib_multipoint_timeseries.ipynb` demonstrates multi-point batch extraction.

## Running the code

**Single-point extraction (script):**
```bash
python read_grib_timeseries.py
```
Edit `TARGET_LAT`, `TARGET_LON`, `DATA_DIR` at the bottom of the script before running.

**Multi-point extraction (notebook):**
```bash
jupyter notebook grib_multipoint_timeseries.ipynb
```

**Install dependencies:**
```bash
pip install -r requirements.txt

# read_grib_xarray 사용 시 (cfgrib은 conda-forge 필수)
conda install -c conda-forge eccodes cfgrib
pip install xarray
```

## Architecture

All reader functions live in `read_grib_timeseries.py` and return `pd.DataFrame`:

| Function | Backend | When to use |
|---|---|---|
| `read_kma_grib_merged` | pygrib + KMAGridConverter | **권장 진입점.** 폴더의 VSRT·SHRT 파일을 자동 감지해 hourly 시계열 하나로 병합. |
| `read_kma_grib` | pygrib + KMAGridConverter | VSRT 또는 SHRT 단독 읽기. `read_kma_grib_merged` 내부에서 호출. |
| `read_grib_pygrib` | pygrib | 변수·레벨 필터링, 비-DFS GRIB 파일. |
| `read_grib_xarray` | xarray + cfgrib | 범용 GRIB2; 동일 환경에 eccodes·cfgrib 필요. |

**`KMAGridConverter`** — KMA Lambert Conformal Conic 투영 파라미터(표준위도 30°/60°, 원점 38°N/126°E, 5 km 격자)를 캡슐화. `latlon_to_grid` / `grid_to_latlon` 메서드를 직접 호출해 좌표 변환에 사용할 수 있다.

### DFS 파일명 규칙

```
DFS_VSRT_GRD_GRB6_PCP.202605102000_202605110520
         ^^^^          ^^^^^^^^^^^^  ^^^^^^^^^^^^
         종류           base_time     end_time
         (VSRT/SHRT)   (YYYYMMDDHHmm)
```

`_parse_base_time(fname)` 이 `PCP.` 과 `_` 사이의 12자리(`YYYYMMDDHHmm`)를 파싱한다.

### 타임스탬프 계산 방식

KMA VSRT GRIB 파일은 메타데이터의 시간 정보가 잘못되어 있어, 두 파일 유형 모두 GRIB 메타데이터 대신 파일명과 GRIB endStep을 조합해 타임스탬프를 계산한다.

| 파일 유형 | 타임스탬프 공식 | 비고 |
|---|---|---|
| **VSRT** | `base_time + (msg_idx + 1) × 10min` | 메시지 순서(0, 1, 2 …) 기반 10분 순차 할당 |
| **SHRT** | `base_time + 1h + endStep(h)` | endStep은 GRIB에서 읽음 (예: 6, 7, …, 79) |

**예시 (base_time = 2026-05-10 20:00):**
- VSRT msg[0] → 20:10, msg[1] → 20:20, …, msg[5] → 21:00
- SHRT endStep=6 → 03:00+1d, endStep=7 → 04:00+1d, …

### VSRT 10분 → 1시간 합산 (`_to_hourly`)

`resample('1h', closed='right', label='right')` + `sum` 적용:

```
H:10, H:20, H:30, H:40, H:50, (H+1):00  →  합산  →  레이블 (H+1):00
```

### VSRT + SHRT 병합 (`read_kma_grib_merged`)

1. VSRT 읽기 → `_to_hourly`로 1시간 합산
2. SHRT 읽기 → **연속 valid_time 간격 > 1h인 시점 이후 제거** (3시간 간격 구간 tail 삭제)
3. VSRT valid_time과 겹치는 SHRT 행 제거 (VSRT 우선)
4. 이어 붙여 valid_time 오름차순 정렬

## Notebook 구조 (`grib_multipoint_timeseries.ipynb`)

| 섹션 | 내용 |
|---|---|
| 1) 설정 | `DATA_FOLDER`, `VSRT_GLOB`, `SHRT_GLOB`, `POINTS_CSV` 지정. `load_points_csv`로 지점 목록 로드. |
| 2) 파일 확인 | 폴더 내 VSRT·SHRT 파일 목록 출력. |
| 3) 개별 데이터 확인 | `read_kma_grib`으로 VSRT(원본 10분 + 1시간 합산)·SHRT를 지점별 DataFrame으로 확인. CSV 저장 전 품질 검토용. |
| 4) 병합 + CSV 저장 | `read_kma_grib_merged`로 VSRT·SHRT 병합 후 `OUTPUT_CSV`에 저장. |

## Data files

- `forecast_rainfall/` — 테스트용 샘플 GRIB 파일.
- `kr_rf_obs_st.csv` / `kr_rf_obs_st_sample.csv` — KMA 강수 관측소 목록. 열 이름: `X`(경도), `Y`(위도), `name`. `load_points_csv`가 자동 감지.
- `multipoint_rainfall_timeseries.csv` — 노트북 섹션 4 출력 CSV.
- `requirements.txt` — pip 의존성 목록.

## Common pitfalls

- **VSRT GRIB 메타데이터 오류**: VSRT 파일의 시간 관련 GRIB 키(`forecastTime`, `validDate`)가 잘못되어 있다. `read_kma_grib`은 이를 무시하고 파일명 base_time + 메시지 순서로 타임스탬프를 직접 계산한다.
- **SHRT 3시간 간격 구간**: KMA SHRT는 약 72시간 이후 3시간 간격으로 전환된다. `read_kma_grib_merged`는 이 구간을 자동으로 제거한다 (개별 `read_kma_grib` 호출 시에는 제거하지 않음).
- **`kr_rf_obs_st.csv` 열 이름**: `X`/`Y`가 경도/위도 순서 (일반적인 lat/lon과 반대). `load_points_csv`가 이를 처리하므로 직접 읽을 때 주의.
- **격자 인덱스 범위 초과**: `read_kma_grib`은 변환된 격자 인덱스가 배열 shape을 벗어나면 nearest-neighbour 검색으로 자동 대체한다.
- **cfgrib 설치**: `read_grib_xarray`는 conda-forge로 설치한 eccodes·cfgrib 필요. `pip install cfgrib`만으로는 동작하지 않을 수 있다. DFS 파일에는 `read_kma_grib`을 권장.
