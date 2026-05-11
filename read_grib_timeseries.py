# ============================================================
# GRB(GRIB) 파일에서 특정 위치(lat, lon) 시계열 데이터 추출
# ============================================================
#
# 필요 라이브러리 설치:
#   pip install pygrib numpy pandas matplotlib
#
# 파일명 예시: DFS_SHRT_GRD_GRB5_PCP.202406212000
#   - DFS: 동네예보
#   - SHRT: 단기예보 / VSRT: 초단기예보
#   - GRD: 격자
#   - GRB5/GRB6: GRIB2 포맷 (기상청 버전)
#   - PCP: 강수량 (Precipitation)
# ============================================================

import re
import os
import contextlib
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# 내부 유틸리티
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _silence_stderr(enabled: bool = True):
    """C 확장(pygrib/eccodes)이 stderr로 출력하는 로그를 임시로 숨긴다."""
    if not enabled:
        yield
        return
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_fd = os.dup(2)
    try:
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)
        os.close(devnull_fd)


def _pygrib_get(grb, key, default=None):
    """pygrib 키 접근 시 RuntimeError를 안전하게 처리한다."""
    try:
        return grb[key]
    except (RuntimeError, KeyError, TypeError, IndexError, AttributeError):
        return default


def _pygrib_forecast_hour(grb) -> int:
    """GRIB 메시지에서 예보 시간(정수, 단위=시간)을 추출한다.
    forecastTime → endStep → stepRange 순으로 시도한다."""
    for key in ("forecastTime", "endStep"):
        v = _pygrib_get(grb, key)
        if v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                continue
    sr = _pygrib_get(grb, "stepRange")
    if sr is not None:
        if isinstance(sr, bytes):
            sr = sr.decode("ascii", errors="ignore")
        if isinstance(sr, str):
            parts = [p.strip() for p in sr.split("-") if p.strip()]
            if parts:
                try:
                    return int(parts[-1])
                except ValueError:
                    pass
    return 0


def _pygrib_valid_time(grb):
    """pygrib validDate를 반환한다. 실패 시 None."""
    try:
        return grb.validDate
    except (RuntimeError, AttributeError, TypeError, ValueError):
        pass
    for key in ("validityDateTime", "validDateTime"):
        v = _pygrib_get(grb, key)
        if v is not None:
            return v
    return None


def _pygrib_units(grb) -> str:
    """GRIB 메시지에서 units 문자열을 반환한다. 실패 시 빈 문자열."""
    try:
        u = grb.units
        if u is not None:
            return u
    except (RuntimeError, AttributeError, TypeError, ValueError):
        pass
    u = _pygrib_get(grb, "units", "")
    return u if u is not None else ""


_BASE_TIME_RE = re.compile(r'PCP\.(\d{12})')


def _parse_base_time(fname: str) -> datetime | None:
    """파일명에서 base_time을 파싱한다.

    'PCP.'와 '_'(또는 파일명 끝) 사이의 12자리 YYYYMMDDHHmm을 사용한다.
    예) DFS_VSRT_GRD_GRB6_PCP.202605102000_202605110520 → 2026-05-10 20:00
    """
    m = _BASE_TIME_RE.search(fname)
    if m:
        try:
            return datetime.strptime(m.group(1), '%Y%m%d%H%M')
        except ValueError:
            pass
    parts = fname.split('.')
    if len(parts) >= 2:
        try:
            return datetime.strptime(parts[-1][:10], '%Y%m%d%H')
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# 방법 1: xarray + cfgrib  (범용 GRIB2, cfgrib 환경 필요)
# ---------------------------------------------------------------------------

def read_grib_xarray(file_paths, target_lat, target_lon):
    """xarray + cfgrib을 이용한 GRIB 파일 읽기.

    Parameters
    ----------
    file_paths : list of str
        GRIB 파일 경로 리스트
    target_lat : float
        추출할 위도
    target_lon : float
        추출할 경도

    Returns
    -------
    pd.DataFrame
    """
    import xarray as xr

    try:
        import cfgrib  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "cfgrib이 설치되어 있지 않아 engine='cfgrib'으로 GRIB을 열 수 없습니다.\n"
            "  conda install -c conda-forge eccodes cfgrib\n"
            "기상청 DFS 격자 강수(파일명 예: DFS_*_PCP.*)는 read_kma_grib() 사용을 권장합니다."
        ) from exc

    try:
        engines = xr.backends.plugins.list_engines()
    except Exception:
        engines = {}
    if engines and "cfgrib" not in engines:
        raise ValueError(
            "xarray가 cfgrib 엔진을 인식하지 않습니다.\n"
            "동일 conda/venv에서 eccodes·cfgrib를 설치한 뒤 커널을 재시작하세요."
        )

    results = []
    actual_lat = actual_lon = None

    for fpath in sorted(file_paths):
        ds = xr.open_dataset(fpath, engine='cfgrib')

        if fpath == sorted(file_paths)[0]:
            print("=" * 60)
            print("[데이터셋 정보]")
            print(ds)
            print("=" * 60)

        ds_point = ds.sel(latitude=target_lat, longitude=target_lon, method='nearest')
        actual_lat = float(ds_point.latitude)
        actual_lon = float(ds_point.longitude)

        record = {'file': Path(fpath).name, 'actual_lat': actual_lat, 'actual_lon': actual_lon}
        if 'time' in ds_point.coords:
            record['time'] = pd.Timestamp(ds_point.time.values)
        if 'valid_time' in ds_point.coords:
            record['valid_time'] = pd.Timestamp(ds_point.valid_time.values)
        if 'step' in ds_point.coords:
            record['step'] = ds_point.step.values
        for var_name in ds.data_vars:
            record[var_name] = float(ds_point[var_name].values)

        results.append(record)
        ds.close()

    df = pd.DataFrame(results)
    print(f"\n✅ {len(df)}개 시간 데이터 추출 완료 ({actual_lat:.4f}°N, {actual_lon:.4f}°E)")
    return df


# ---------------------------------------------------------------------------
# 방법 2: pygrib  (변수·레벨 필터링, 비-DFS GRIB 파일용)
# ---------------------------------------------------------------------------

def read_grib_pygrib(file_paths, target_lat, target_lon, variable_name=None):
    """pygrib을 이용한 GRIB 파일 읽기.

    Parameters
    ----------
    file_paths : list of str
    target_lat : float
    target_lon : float
    variable_name : str, optional
        None이면 모든 메시지 읽기

    Returns
    -------
    pd.DataFrame
    """
    import pygrib

    results = []

    for fpath in sorted(file_paths):
        grbs = pygrib.open(fpath)

        if fpath == sorted(file_paths)[0]:
            print("=" * 60)
            print("[GRIB 메시지 목록]")
            for grb in grbs:
                print(f"  {grb.messagenumber}: {grb.name} (level={grb.level}, date={grb.validDate})")
            grbs.seek(0)
            print("=" * 60)

        messages = grbs.select(name=variable_name) if variable_name else grbs.select()

        for grb in messages:
            lats, lons = grb.latlons()
            data = grb.values
            dist = np.sqrt((lats - target_lat) ** 2 + (lons - target_lon) ** 2)
            idx = np.unravel_index(dist.argmin(), dist.shape)

            results.append({
                'file': Path(fpath).name,
                'variable': grb.name,
                'level': grb.level,
                'valid_date': grb.validDate,
                'forecast_time': grb.forecastTime,
                'actual_lat': float(lats[idx]),
                'actual_lon': float(lons[idx]),
                'value': float(data[idx]),
                'units': grb.units,
            })

        grbs.close()

    df = pd.DataFrame(results)
    print(f"\n✅ {len(df)}개 레코드 추출 완료")
    return df


# ---------------------------------------------------------------------------
# 방법 3: 기상청 DFS 격자 전용  (Lambert Conformal + 파일명 기반 타임스탬프)
# ---------------------------------------------------------------------------

class KMAGridConverter:
    """기상청 동네예보 격자 ↔ 위경도 변환기 (Lambert Conformal Conic 투영법)."""

    RE    = 6371.00877  # 지구 반경 (km)
    GRID  = 5.0         # 격자 간격 (km)
    SLAT1 = 30.0        # 표준 위도 1 (°)
    SLAT2 = 60.0        # 표준 위도 2 (°)
    OLON  = 126.0       # 기준점 경도 (°)
    OLAT  = 38.0        # 기준점 위도 (°)
    XO    = 43          # 기준점 격자 X (GRB5 기준)
    YO    = 136         # 기준점 격자 Y (GRB5 기준)

    def __init__(self):
        self._init_params()

    def _init_params(self):
        PI = np.pi
        DEGRAD = PI / 180.0
        re = self.RE / self.GRID
        slat1, slat2 = self.SLAT1 * DEGRAD, self.SLAT2 * DEGRAD
        olon, olat   = self.OLON * DEGRAD,  self.OLAT * DEGRAD

        sn = np.log(np.cos(slat1) / np.cos(slat2)) / np.log(
            np.tan(PI * 0.25 + slat2 * 0.5) / np.tan(PI * 0.25 + slat1 * 0.5)
        )
        sf = np.power(np.tan(PI * 0.25 + slat1 * 0.5), sn) * np.cos(slat1) / sn
        ro = re * sf / np.power(np.tan(PI * 0.25 + olat * 0.5), sn)

        self.sn, self.sf, self.ro, self.re, self.olon = sn, sf, ro, re, olon

    def latlon_to_grid(self, lat: float, lon: float) -> tuple[int, int]:
        """위경도 → 격자 좌표 (x, y)."""
        PI = np.pi
        DEGRAD = PI / 180.0
        ra = self.re * self.sf / np.power(np.tan(PI * 0.25 + lat * DEGRAD * 0.5), self.sn)
        theta = lon * DEGRAD - self.olon
        if theta > PI:
            theta -= 2.0 * PI
        if theta < -PI:
            theta += 2.0 * PI
        theta *= self.sn
        return int(ra * np.sin(theta) + self.XO + 0.5), int(self.ro - ra * np.cos(theta) + self.YO + 0.5)

    def grid_to_latlon(self, x: int, y: int) -> tuple[float, float]:
        """격자 좌표 (x, y) → 위경도."""
        PI = np.pi
        RADDEG = 180.0 / PI
        xn = x - self.XO
        yn = self.ro - y + self.YO
        ra = np.sqrt(xn * xn + yn * yn)
        if self.sn < 0:
            ra = -ra
        alat = 2.0 * np.arctan(np.power(self.re * self.sf / ra, 1.0 / self.sn)) - PI * 0.5
        if abs(xn) <= 1e-6:
            theta = 0.0
        elif abs(yn) <= 1e-6:
            theta = PI * 0.5 * (1 if xn > 0 else -1)
        else:
            theta = np.arctan2(xn, yn)
        return alat * RADDEG, (theta / self.sn + self.olon) * RADDEG


def read_kma_grib(
    file_paths,
    target_lat: float,
    target_lon: float,
    quiet_eccodes: bool = True,
) -> pd.DataFrame:
    """기상청 DFS GRIB 파일에서 단일 지점의 시계열을 추출한다.

    타임스탬프는 GRIB 메타데이터를 사용하지 않고 파일명과 메시지 순서로 계산한다:

    - VSRT: ``valid_time = base_time + (msg_idx + 1) × 10min``
      (GRIB 메타데이터가 잘못되어 있어 파일명 기준 순차 할당)
    - SHRT: ``valid_time = base_time + 1h + endStep``
      (endStep은 GRIB에서 읽으며 시간 단위)

    Parameters
    ----------
    file_paths : list of str
        기상청 GRIB 파일 경로 리스트
    target_lat : float
        추출할 위도
    target_lon : float
        추출할 경도
    quiet_eccodes : bool
        True이면 eccodes/pygrib의 stderr 출력을 숨긴다.

    Returns
    -------
    pd.DataFrame
        columns: base_time, forecast_hour, valid_time, variable, value, units
    """
    import pygrib

    converter = KMAGridConverter()
    grid_x, grid_y = converter.latlon_to_grid(target_lat, target_lon)
    actual_lat, actual_lon = converter.grid_to_latlon(grid_x, grid_y)

    print(f"📍 요청 위치: ({target_lat:.4f}°N, {target_lon:.4f}°E)")
    print(f"📍 격자 좌표: (x={grid_x}, y={grid_y})")
    print(f"📍 실제 위치: ({actual_lat:.4f}°N, {actual_lon:.4f}°E)")
    print()

    results = []

    for fpath in sorted(file_paths):
        fname = Path(fpath).name
        base_time = _parse_base_time(fname)
        is_vsrt = 'VSRT' in fname.upper()
        var_type = fname.split('.')[0].split('_')[-1] if '.' in fname else 'UNKNOWN'

        with _silence_stderr(enabled=quiet_eccodes):
            grbs = pygrib.open(fpath)

            for msg_idx, grb in enumerate(grbs):
                data = grb.values

                if grid_y < data.shape[0] and grid_x < data.shape[1]:
                    value = float(data[grid_y, grid_x])
                else:
                    lats, lons = grb.latlons()
                    dist = np.sqrt((lats - target_lat) ** 2 + (lons - target_lon) ** 2)
                    idx = np.unravel_index(dist.argmin(), dist.shape)
                    value = float(data[idx])

                if is_vsrt and base_time is not None:
                    # VSRT: GRIB 메타데이터 무시, 파일명 base_time 기준 10분 순차 할당
                    step_min = (msg_idx + 1) * 10
                    valid_time = base_time + timedelta(minutes=step_min)
                    forecast_hour = round(step_min / 60, 6)
                else:
                    # SHRT: valid_time = base_time + 1h + endStep(h)
                    forecast_hour = 1 + _pygrib_forecast_hour(grb)
                    valid_time = (
                        base_time + timedelta(hours=forecast_hour)
                        if base_time is not None else pd.NaT
                    )

                results.append({
                    'base_time':     base_time,
                    'forecast_hour': forecast_hour,
                    'valid_time':    valid_time,
                    'variable':      var_type,
                    'value':         value,
                    'units':         _pygrib_units(grb),
                })

            grbs.close()

    df = pd.DataFrame(results).sort_values('valid_time').reset_index(drop=True)
    print(f"✅ {len(df)}개 시계열 데이터 추출 완료")
    return df


# ---------------------------------------------------------------------------
# VSRT + SHRT 병합 유틸리티
# ---------------------------------------------------------------------------

def _to_hourly(
    df: pd.DataFrame,
    time_col: str = 'valid_time',
    value_col: str = 'value',
) -> pd.DataFrame:
    """Sub-hourly 데이터를 1시간 합산으로 변환한다.

    이미 1시간 이상 간격이면 원본을 그대로 반환한다.
    ``closed='right', label='right'`` 적용:
    예) H:10, H:20, H:30, H:40, H:50, (H+1):00 → 합산 → 레이블 (H+1):00
    """
    df = df.copy()
    df[time_col] = pd.to_datetime(df[time_col])

    if len(df) < 2:
        return df

    if df[time_col].diff().dropna().min() >= pd.Timedelta('1h'):
        return df

    agg = {}
    for col in df.columns:
        if col == time_col:
            continue
        if col == value_col:
            agg[col] = 'sum'
        elif col == 'forecast_hour':
            agg[col] = 'last'   # 버킷 마지막 스텝(= 정시)을 대표값으로
        else:
            agg[col] = 'first'

    df_h = (
        df.set_index(time_col)
        .resample('1h', label='right', closed='right')
        .agg(agg)
        .reset_index()
    )
    return df_h.dropna(subset=[value_col]).reset_index(drop=True)


def read_kma_grib_merged(
    folder,
    target_lat: float,
    target_lon: float,
    vsrt_glob: str = '*VSRT*',
    shrt_glob: str = '*SHRT*',
    quiet_eccodes: bool = True,
) -> pd.DataFrame:
    """VSRT + SHRT GRIB 파일을 읽어 hourly 시계열 하나로 합친다.

    처리 순서:
    1. VSRT 읽기 → 10분 데이터를 ``_to_hourly``로 1시간 합산
    2. SHRT 읽기 → 3시간 간격 구간(tail) 제거 후 VSRT 우선으로 중복 제거
    3. 두 시계열을 이어 valid_time 오름차순 정렬

    Parameters
    ----------
    folder : str or Path
    target_lat, target_lon : float
    vsrt_glob, shrt_glob : str
        파일 검색 패턴 (기본: ``'*VSRT*'``, ``'*SHRT*'``)
    quiet_eccodes : bool

    Returns
    -------
    pd.DataFrame
        columns: base_time, forecast_hour, valid_time, variable, value, units, forecast_type
    """
    folder = Path(folder)
    vsrt_files = sorted(str(p) for p in folder.glob(vsrt_glob) if p.is_file())
    shrt_files = sorted(str(p) for p in folder.glob(shrt_glob) if p.is_file())

    if not vsrt_files and not shrt_files:
        raise FileNotFoundError(
            f"'{folder}' 에서 VSRT/SHRT 파일을 찾을 수 없습니다.\n"
            f"  VSRT 패턴: {vsrt_glob}\n  SHRT 패턴: {shrt_glob}"
        )

    frames: list[pd.DataFrame] = []

    if vsrt_files:
        print(f"[VSRT] {len(vsrt_files)}개 파일")
        df_v = read_kma_grib(vsrt_files, target_lat, target_lon, quiet_eccodes=quiet_eccodes)
        df_v = _to_hourly(df_v)
        df_v['forecast_type'] = 'VSRT'
        frames.append(df_v)
        print()

    if shrt_files:
        print(f"[SHRT] {len(shrt_files)}개 파일")
        df_s = read_kma_grib(shrt_files, target_lat, target_lon, quiet_eccodes=quiet_eccodes)
        df_s = _to_hourly(df_s)
        df_s['forecast_type'] = 'SHRT'

        # 연속 valid_time 간격이 1h를 초과하는 지점(3시간 간격 구간)부터 제거
        df_s = df_s.sort_values('valid_time').reset_index(drop=True)
        gap_mask = pd.to_datetime(df_s['valid_time']).diff() > pd.Timedelta('1h')
        if gap_mask.any():
            cut = int(gap_mask.idxmax())
            n_dropped = len(df_s) - cut
            df_s = df_s.iloc[:cut].reset_index(drop=True)
            print(f"  3시간 간격 구간 제거: {n_dropped}행 삭제 "
                  f"(마지막 hourly valid_time: {df_s['valid_time'].iloc[-1]})")

        frames.append(df_s)
        print()

    if len(frames) == 1:
        df_merged = frames[0]
    else:
        df_v, df_s = frames[0], frames[1]
        vsrt_times = set(pd.to_datetime(df_v['valid_time'].dropna()))
        df_s_extra = df_s[~pd.to_datetime(df_s['valid_time']).isin(vsrt_times)]
        n_overlap = len(df_s) - len(df_s_extra)
        df_merged = pd.concat([df_v, df_s_extra], ignore_index=True)
        print(f"병합 결과: VSRT {len(df_v)}행 + SHRT {len(df_s_extra)}행 "
              f"(SHRT 중복 제거 {n_overlap}행, VSRT 우선)")

    df_merged['valid_time'] = pd.to_datetime(df_merged['valid_time'])
    df_merged = df_merged.sort_values('valid_time').reset_index(drop=True)
    print(f"✅ 최종 {len(df_merged)}개 hourly 데이터 "
          f"({df_merged['valid_time'].min()} ~ {df_merged['valid_time'].max()})")
    return df_merged


# ---------------------------------------------------------------------------
# 시계열 시각화
# ---------------------------------------------------------------------------

def plot_timeseries(
    df,
    time_col: str = 'valid_time',
    value_col: str = 'value',
    title: str = '시계열 데이터',
    ylabel: str = '값',
    units: str = '',
    save_path=None,
):
    """시계열 DataFrame을 꺾은선 그래프로 시각화한다."""
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(df[time_col], df[value_col],
            'o-', color='#2196F3', linewidth=2, markersize=5,
            markerfacecolor='white', markeredgewidth=2)
    ax.fill_between(df[time_col], df[value_col], alpha=0.15, color='#2196F3')
    ax.set_title(title, fontsize=16, fontweight='bold', pad=15)
    ax.set_xlabel('시간', fontsize=12)
    ax.set_ylabel(f'{ylabel} ({units})' if units else ylabel, fontsize=12)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.tick_params(axis='x', rotation=45)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"📊 그래프 저장: {save_path}")

    return fig


# ---------------------------------------------------------------------------
# CLI 실행 예시
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # 추출할 위치
    TARGET_LAT = 37.5665    # 서울시청 위도
    TARGET_LON = 126.9780   # 서울시청 경도

    # GRIB 파일 디렉터리
    DATA_DIR = './forecast_rainfall'

    file_list = sorted(glob.glob(f'{DATA_DIR}/*PCP*'))

    if not file_list:
        print(f"⚠️  GRIB 파일을 찾을 수 없습니다. DATA_DIR='{DATA_DIR}'")
    else:
        print(f"📁 {len(file_list)}개 파일 발견\n")

        # 방법 선택: 1=xarray, 2=pygrib(generic), 3=KMA DFS(권장)
        METHOD = 3

        if METHOD == 1:
            df = read_grib_xarray(file_list, TARGET_LAT, TARGET_LON)
        elif METHOD == 2:
            df = read_grib_pygrib(file_list, TARGET_LAT, TARGET_LON)
        else:
            df = read_kma_grib(file_list, TARGET_LAT, TARGET_LON)

        print("\n" + "=" * 60)
        print(df.to_string())

        plot_timeseries(df,
                        title=f'시계열 ({TARGET_LAT}°N, {TARGET_LON}°E)',
                        ylabel='강수량',
                        save_path='timeseries.png')

        df.to_csv('timeseries_data.csv', index=False, encoding='utf-8-sig')
        print("\n💾 CSV 저장: timeseries_data.csv")
