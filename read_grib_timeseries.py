# ============================================================
# GRB(GRIB) 파일에서 특정 위치(lat, lon) 시계열 데이터 추출
# ============================================================
#
# 필요 라이브러리 설치:
#   pip install xarray cfgrib pygrib matplotlib pandas numpy
#
# 파일명 예시: DFS_SHRT_GRD_GRB4_PCP.202406212000
#   - DFS: 동네예보
#   - SHRT: 단기예보
#   - GRD: 격자
#   - GRB4: GRIB2 포맷 (기상청 v4)
#   - PCP: 강수량 (Precipitation)
# ============================================================

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime, timedelta
import glob


# ============================================================
# 방법 1: xarray + cfgrib (가장 추천하는 방법)
# ============================================================
def read_grib_xarray(file_paths, target_lat, target_lon):
    """
    xarray + cfgrib을 이용한 GRIB 파일 읽기

    Parameters
    ----------
    file_paths : list of str
        GRIB 파일 경로 리스트 (시계열 구성을 위해 여러 파일)
    target_lat : float
        추출할 위도
    target_lon : float
        추출할 경도

    Returns
    -------
    pd.DataFrame : 시계열 데이터프레임
    """
    import xarray as xr

    try:
        import cfgrib  # noqa: F401 — xarray에 cfgrib 엔진 등록
    except ImportError as exc:
        raise ImportError(
            "cfgrib이 설치되어 있지 않아 engine='cfgrib'으로 GRIB을 열 수 없습니다.\n"
            "  conda install -c conda-forge eccodes cfgrib\n"
            "  또는: pip install eccodes cfgrib\n"
            "기상청 DFS 격자 강수(파일명 예: DFS_*_PCP.*)는 pygrib 기반 read_kma_grib() 사용을 권장합니다."
        ) from exc

    try:
        engines = xr.backends.plugins.list_engines()
    except Exception:
        engines = {}
    if engines and "cfgrib" not in engines:
        raise ValueError(
            "xarray가 cfgrib 엔진을 인식하지 않습니다(cfgrib 미설치 또는 다른 환경의 xarray일 수 있음).\n"
            "동일 conda/venv에서 eccodes·cfgrib를 설치한 뒤 커널을 재시작하세요.\n"
            "또는 read_kma_grib()로 읽으세요."
        )

    results = []

    for fpath in sorted(file_paths):
        # GRIB 파일 열기
        ds = xr.open_dataset(fpath, engine='cfgrib')

        # 데이터셋 정보 출력 (첫 파일만)
        if fpath == file_paths[0]:
            print("=" * 60)
            print("[데이터셋 정보]")
            print(ds)
            print("=" * 60)
            print(f"\n변수 목록: {list(ds.data_vars)}")
            print(f"좌표 목록: {list(ds.coords)}")
            print(f"차원 목록: {list(ds.dims)}")

        # 가장 가까운 격자점 찾기 (nearest neighbor)
        ds_point = ds.sel(
            latitude=target_lat,
            longitude=target_lon,
            method='nearest'
        )

        # 실제 선택된 좌표 확인
        actual_lat = float(ds_point.latitude)
        actual_lon = float(ds_point.longitude)

        # 모든 변수의 값 추출
        record = {
            'file': Path(fpath).name,
            'actual_lat': actual_lat,
            'actual_lon': actual_lon,
        }

        # 시간 정보 추출
        if 'time' in ds_point.coords:
            record['time'] = pd.Timestamp(ds_point.time.values)
        if 'valid_time' in ds_point.coords:
            record['valid_time'] = pd.Timestamp(ds_point.valid_time.values)
        if 'step' in ds_point.coords:
            record['step'] = ds_point.step.values

        # 각 변수 값 추출
        for var_name in ds.data_vars:
            record[var_name] = float(ds_point[var_name].values)

        results.append(record)
        ds.close()

    df = pd.DataFrame(results)
    print(f"\n✅ {len(df)}개 시간 데이터 추출 완료")
    print(f"   위치: ({actual_lat:.4f}°N, {actual_lon:.4f}°E)")

    return df


# ============================================================
# 방법 2: pygrib (세밀한 제어가 필요할 때)
# ============================================================
def read_grib_pygrib(file_paths, target_lat, target_lon, variable_name=None):
    """
    pygrib을 이용한 GRIB 파일 읽기

    Parameters
    ----------
    file_paths : list of str
        GRIB 파일 경로 리스트
    target_lat : float
        추출할 위도
    target_lon : float
        추출할 경도
    variable_name : str, optional
        추출할 변수명 (None이면 모든 메시지 읽기)

    Returns
    -------
    pd.DataFrame : 시계열 데이터프레임
    """
    import pygrib

    results = []

    for fpath in sorted(file_paths):
        grbs = pygrib.open(fpath)

        # 첫 파일에서 메시지 목록 출력
        if fpath == file_paths[0]:
            print("=" * 60)
            print("[GRIB 메시지 목록]")
            for grb in grbs:
                print(f"  {grb.messagenumber}: {grb.name} "
                      f"(level={grb.level}, "
                      f"date={grb.validDate})")
            grbs.seek(0)
            print("=" * 60)

        # 메시지 선택
        if variable_name:
            messages = grbs.select(name=variable_name)
        else:
            messages = grbs.select()

        for grb in messages:
            lats, lons = grb.latlons()
            data = grb.values

            # 가장 가까운 격자점 인덱스 찾기
            dist = np.sqrt((lats - target_lat)**2 + (lons - target_lon)**2)
            idx = np.unravel_index(dist.argmin(), dist.shape)

            actual_lat = lats[idx]
            actual_lon = lons[idx]
            value = data[idx]

            record = {
                'file': Path(fpath).name,
                'variable': grb.name,
                'level': grb.level,
                'valid_date': grb.validDate,
                'forecast_time': grb.forecastTime,
                'actual_lat': actual_lat,
                'actual_lon': actual_lon,
                'value': float(value),
                'units': grb.units,
            }
            results.append(record)

        grbs.close()

    df = pd.DataFrame(results)
    print(f"\n✅ {len(df)}개 레코드 추출 완료")

    return df


# ============================================================
# 방법 3: 기상청 DFS 격자 전용 (Lambert Conformal)
# ============================================================
class KMAGridConverter:
    """
    기상청 동네예보 격자 <-> 위경도 변환기
    (Lambert Conformal Conic 투영법)
    """

    def __init__(self):
        self.RE = 6371.00877    # 지구 반경 (km)
        self.GRID = 5.0         # 격자 간격 (km)
        self.SLAT1 = 30.0       # 투영 위도 1 (degree)
        self.SLAT2 = 60.0       # 투영 위도 2 (degree)
        self.OLON = 126.0       # 기준점 경도 (degree)
        self.OLAT = 38.0        # 기준점 위도 (degree)
        self.XO = 43            # 기준점 X좌표 (격자)
        self.YO = 136           # 기준점 Y좌표 (격자) - v4 기준
        self._init_params()

    def _init_params(self):
        PI = np.pi
        DEGRAD = PI / 180.0
        re = self.RE / self.GRID
        slat1 = self.SLAT1 * DEGRAD
        slat2 = self.SLAT2 * DEGRAD
        olon = self.OLON * DEGRAD
        olat = self.OLAT * DEGRAD
        sn = np.tan(PI * 0.25 + slat2 * 0.5) / np.tan(PI * 0.25 + slat1 * 0.5)
        sn = np.log(np.cos(slat1) / np.cos(slat2)) / np.log(sn)
        sf = np.tan(PI * 0.25 + slat1 * 0.5)
        sf = np.power(sf, sn) * np.cos(slat1) / sn
        ro = np.tan(PI * 0.25 + olat * 0.5)
        ro = re * sf / np.power(ro, sn)
        self.sn = sn
        self.sf = sf
        self.ro = ro
        self.re = re
        self.olon = olon

    def latlon_to_grid(self, lat, lon):
        """위경도 -> 격자 좌표 변환"""
        PI = np.pi
        DEGRAD = PI / 180.0
        ra = np.tan(PI * 0.25 + lat * DEGRAD * 0.5)
        ra = self.re * self.sf / np.power(ra, self.sn)
        theta = lon * DEGRAD - self.olon
        if theta > PI:
            theta -= 2.0 * PI
        if theta < -PI:
            theta += 2.0 * PI
        theta *= self.sn
        x = ra * np.sin(theta) + self.XO
        y = self.ro - ra * np.cos(theta) + self.YO
        return int(x + 0.5), int(y + 0.5)

    def grid_to_latlon(self, x, y):
        """격자 좌표 -> 위경도 변환"""
        PI = np.pi
        RADDEG = 180.0 / PI
        xn = x - self.XO
        yn = self.ro - y + self.YO
        ra = np.sqrt(xn * xn + yn * yn)
        if self.sn < 0:
            ra = -ra
        alat = np.power((self.re * self.sf / ra), (1.0 / self.sn))
        alat = 2.0 * np.arctan(alat) - PI * 0.5
        if abs(xn) <= 1e-6:
            theta = 0.0
        else:
            if abs(yn) <= 1e-6:
                theta = PI * 0.5
                if xn < 0:
                    theta = -theta
            else:
                theta = np.arctan2(xn, yn)
        alon = theta / self.sn + self.olon
        return alat * RADDEG, alon * RADDEG


def _pygrib_get(grb, key, default=None):
    """pygrib은 없는 키 접근 시 RuntimeError를 던질 수 있어 안전히 읽습니다."""
    try:
        return grb[key]
    except (RuntimeError, KeyError, TypeError, IndexError, AttributeError):
        return default


def _pygrib_forecast_hour(grb):
    """메시지별로 예보 시간(h) 추출. 키 이름이 GRIB 에디션/생산자마다 다릅니다."""
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
    try:
        return grb.validDate
    except (RuntimeError, AttributeError, TypeError, ValueError):
        pass
    for key in ("validityDateTime", "validDateTime"):
        v = _pygrib_get(grb, key)
        if v is not None:
            return v
    return None


def _pygrib_units(grb):
    try:
        u = grb.units
        if u is not None:
            return u
    except (RuntimeError, AttributeError, TypeError, ValueError):
        pass
    u = _pygrib_get(grb, "units", "")
    return u if u is not None else ""


def read_kma_grib(file_paths, target_lat, target_lon):
    """
    기상청 DFS GRIB 파일 읽기 (격자 변환 포함)

    Parameters
    ----------
    file_paths : list of str
        기상청 GRIB 파일 경로 리스트
    target_lat : float
        추출할 위도
    target_lon : float
        추출할 경도

    Returns
    -------
    pd.DataFrame : 시계열 데이터프레임
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

        # 파일명에서 시간 정보 파싱
        parts = fname.split('.')
        if len(parts) >= 2 and len(parts[-1]) >= 10:
            time_str = parts[-1][:10]
            try:
                base_time = datetime.strptime(time_str, '%Y%m%d%H')
            except:
                base_time = None
        else:
            base_time = None

        # 변수 타입 파싱
        var_type = fname.split('_')[-1].split('.')[0] if '_' in fname else 'UNKNOWN'

        grbs = pygrib.open(fpath)

        for grb in grbs:
            data = grb.values

            if grid_y < data.shape[0] and grid_x < data.shape[1]:
                value = float(data[grid_y, grid_x])
            else:
                lats, lons = grb.latlons()
                dist = np.sqrt((lats - target_lat)**2 +
                              (lons - target_lon)**2)
                idx = np.unravel_index(dist.argmin(), dist.shape)
                value = float(data[idx])

            forecast_hour = _pygrib_forecast_hour(grb)
            if base_time is not None:
                valid_time = base_time + timedelta(hours=forecast_hour)
            else:
                valid_time = _pygrib_valid_time(grb)
            if valid_time is None:
                valid_time = pd.NaT

            record = {
                'base_time': base_time,
                'forecast_hour': forecast_hour,
                'valid_time': valid_time,
                'variable': var_type,
                'value': value,
                'units': _pygrib_units(grb),
            }
            results.append(record)

        grbs.close()

    df = pd.DataFrame(results)
    df = df.sort_values('valid_time').reset_index(drop=True)

    print(f"✅ {len(df)}개 시계열 데이터 추출 완료")
    return df


# ============================================================
# 시계열 시각화 함수
# ============================================================
def plot_timeseries(df, time_col='valid_time', value_col='value',
                    title='시계열 데이터', ylabel='값', units='',
                    save_path=None):
    """시계열 데이터 시각화"""

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


# ============================================================
# 🚀 메인 실행
# ============================================================
if __name__ == '__main__':

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 📌 여기를 수정하세요!
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # 1) 추출할 위치
    TARGET_LAT = 37.5665   # 서울시청 위도
    TARGET_LON = 126.9780  # 서울시청 경도

    # 2) GRIB 파일 목록
    DATA_DIR = './data'  # GRIB 파일 디렉토리

    # 단일 파일
    # file_list = [f'{DATA_DIR}/DFS_SHRT_GRD_GRB4_PCP.202406212000']

    # 여러 파일 (강수량)
    file_list = sorted(glob.glob(f'{DATA_DIR}/*PCP*'))

    # 여러 파일 (기온)
    # file_list = sorted(glob.glob(f'{DATA_DIR}/*TMP*'))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 실행
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    if not file_list:
        print("⚠️  GRIB 파일을 찾을 수 없습니다.")
        print(f"   DATA_DIR = '{DATA_DIR}' 를 확인해 주세요.")
    else:
        print(f"📁 {len(file_list)}개 파일 발견\n")

        # 방법 선택 (1, 2, 3 중 택1)
        METHOD = 1

        if METHOD == 1:
            df = read_grib_xarray(file_list, TARGET_LAT, TARGET_LON)
        elif METHOD == 2:
            df = read_grib_pygrib(file_list, TARGET_LAT, TARGET_LON)
        elif METHOD == 3:
            df = read_kma_grib(file_list, TARGET_LAT, TARGET_LON)

        # 결과 출력
        print("\n" + "=" * 60)
        print("[추출된 데이터]")
        print(df.to_string())

        # 시각화
        fig = plot_timeseries(df,
            title=f'시계열 데이터 ({TARGET_LAT}°N, {TARGET_LON}°E)',
            ylabel='값',
            save_path='timeseries.png')

        # CSV 저장
        df.to_csv('timeseries_data.csv', index=False, encoding='utf-8-sig')
        print("\n💾 CSV 저장: timeseries_data.csv")
