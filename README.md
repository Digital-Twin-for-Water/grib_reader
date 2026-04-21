# grib_reader

기상청 동네예보(DFS) GRIB 파일에서 특정 위치(위·경도)의 시계열 데이터를 추출하는 Python 라이브러리입니다.

## 개요

기상청이 배포하는 동네예보 단기예보 GRIB 격자 파일(`DFS_SHRT_GRD_GRB*_PCP.*` 등)을 읽어,
지정한 관측소(위·경도) 좌표에 가장 가까운 격자점의 값을 시계열 형태로 추출합니다.
단일 지점 추출과 다중 지점 일괄 추출을 모두 지원합니다.

## 파일 구성

```
grib_reader/
├── read_grib_timeseries.py          # 핵심 라이브러리
├── grib_multipoint_timeseries.ipynb # 다중 지점 추출 예제 노트북
├── points_input.csv                 # 지점 목록 예시 (위·경도)
├── multipoint_rainfall_timeseries.csv  # 추출 결과 예시
└── forecast_rainfall1/              # 샘플 GRIB 파일 폴더
```

## 주요 기능

### 1. `read_kma_grib` — 기상청 DFS 전용 (권장)

기상청 Lambert Conformal Conic 투영 격자를 직접 사용하므로, 위경도 변환 오차가 없고 속도가 가장 빠릅니다.

```python
from read_grib_timeseries import read_kma_grib

file_list = ['forecast_rainfall1/DFS_SHRT_GRD_GRB4_PCP.202406212000']
df = read_kma_grib(file_list, target_lat=37.5665, target_lon=126.9780)
print(df)
```

반환 컬럼:

| 컬럼 | 설명 |
|---|---|
| `base_time` | 예보 발표 시각 (파일명에서 파싱) |
| `forecast_hour` | 예보 시간 (발표 시각 기준 시간 수) |
| `valid_time` | 유효 시각 (`base_time + forecast_hour`) |
| `variable` | 변수 종류 (예: `PCP`, `TMP`) |
| `value` | 격자 값 |
| `units` | 단위 |

---

### 2. `read_grib_xarray` — xarray + cfgrib

범용 GRIB2 파일 읽기. `eccodes`와 `cfgrib`가 설치된 환경에서 사용합니다.

```python
from read_grib_timeseries import read_grib_xarray

df = read_grib_xarray(file_list, target_lat=37.5665, target_lon=126.9780)
```

---

### 3. `read_grib_pygrib` — pygrib 범용

변수·레벨 필터링 등 세밀한 제어가 필요할 때 사용합니다.

```python
from read_grib_timeseries import read_grib_pygrib

df = read_grib_pygrib(file_list, target_lat=37.5665, target_lon=126.9780,
                      variable_name='Total precipitation')
```

---

### 4. `KMAGridConverter` — 격자 좌표 변환기

위경도 ↔ 기상청 동네예보 격자 좌표를 직접 변환합니다.

```python
from read_grib_timeseries import KMAGridConverter

conv = KMAGridConverter()
x, y = conv.latlon_to_grid(37.5665, 126.9780)   # 위경도 → 격자
lat, lon = conv.grid_to_latlon(x, y)             # 격자 → 위경도
```

---

### 5. `plot_timeseries` — 시계열 시각화

```python
from read_grib_timeseries import plot_timeseries

fig = plot_timeseries(df, time_col='valid_time', value_col='value',
                      title='서울 강수량', ylabel='강수량', units='mm',
                      save_path='rainfall.png')
```

---

## 다중 지점 일괄 추출 (`grib_multipoint_timeseries.ipynb`)

`points_input.csv`에 지점 목록을 작성하면, 노트북이 모든 지점에 대해 시계열을 추출하고 CSV로 저장합니다.

**`points_input.csv` 형식** (`UTF-8`):

```csv
point_name,lat,lon
서울시청,37.5665,126.9780
부산,35.1796,129.0756
```

노트북 실행 결과는 `multipoint_rainfall_timeseries.csv`에 저장됩니다.

---

## 설치 (의존 패키지)

```bash
# 기본 (read_kma_grib, read_grib_pygrib)
pip install pygrib numpy pandas matplotlib

# xarray 방식 추가 사용 시
conda install -c conda-forge eccodes cfgrib
pip install xarray
```

> **참고:** `cfgrib`은 `pip install cfgrib`만으로 설치가 되지 않는 경우가 있습니다.  
> conda 환경에서 `conda install -c conda-forge eccodes cfgrib` 사용을 권장합니다.

---

## GRIB 파일명 규칙

기상청 동네예보 GRIB 파일명 예시:

```
DFS_SHRT_GRD_GRB4_PCP.202406212000
│   │    │   │    │   └── 발표 시각 (YYYYMMDDhhmm)
│   │    │   │    └────── 변수 (PCP: 강수량, TMP: 기온 등)
│   │    │   └─────────── GRIB 버전 (GRB4: v4, GRB5: v5)
│   │    └─────────────── 격자 데이터 (GRD)
│   └──────────────────── 단기예보 (SHRT)
└──────────────────────── 동네예보 (DFS)
```

---

## 라이선스

[LICENSE](LICENSE) 파일을 확인하세요.
