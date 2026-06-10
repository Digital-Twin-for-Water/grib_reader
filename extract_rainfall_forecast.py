"""
KMA DFS VSRT+SHRT GRIB 강수 시계열 다중 지점 추출 → CSV 저장
Usage: python extract_rainfall_forecast.py [--data-folder PATH] [--points-csv PATH] [--output PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from read_grib_timeseries import read_kma_grib_merged

# ── 설정 (CLI 인자 미사용 시 기본값) ────────────────────────
DEFAULT_DATA_FOLDER = Path("forecast_rainfall")
DEFAULT_VSRT_GLOB   = "*VSRT*PCP*"
DEFAULT_SHRT_GLOB   = "*SHRT*PCP*"
DEFAULT_POINTS_CSV  = Path("kr_rf_obs_st.csv")
DEFAULT_OUTPUT_CSV  = Path("kr_rf_forecast.csv")

OUTPUT_COLS = [
    "point_name",
    "point_code",
    "base_time",
    "forecast_hour",
    "valid_time",
    "variable",
    "value",
    "forecast_type",
]


def load_points_csv(path: Path) -> list[dict]:
    last_error: Exception | None = None
    for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except UnicodeDecodeError as e:
            last_error = e
    else:
        raise UnicodeDecodeError(
            "csv", b"", 0, 1,
            f"{path} 인코딩을 읽을 수 없습니다. utf-8-sig/cp949/euc-kr로 저장 후 다시 시도하세요.",
        ) from last_error

    df.columns = [str(c).strip() for c in df.columns]
    lower = {c.lower(): c for c in df.columns}

    def col(*candidates: str) -> str | None:
        for k in candidates:
            if k.strip().lower() in lower:
                return lower[k.strip().lower()]
        return None

    c_name = col("name", "point_name")
    c_lat  = col("y", "lat", "latitude")
    c_lon  = col("x", "lon", "longitude")
    c_code = col("code")

    if c_lat is None or c_lon is None:
        raise ValueError(f"{path}에 위도/경도 열이 필요합니다. 현재 열: {list(df.columns)}")

    points: list[dict] = []
    for _, row in df.iterrows():
        lat  = float(row[c_lat])
        lon  = float(row[c_lon])
        name = (
            str(row[c_name]).strip()
            if c_name and pd.notna(row[c_name]) and str(row[c_name]).strip()
            else f"{lat:.4f}_{lon:.4f}"
        )
        code = (
            str(row[c_code]).strip()
            if c_code and pd.notna(row[c_code]) and str(row[c_code]).strip()
            else ""
        )
        points.append({"name": name, "lat": lat, "lon": lon, "code": code})
    return points


def extract(
    data_folder: Path,
    points: list[dict],
    output_csv: Path,
    vsrt_glob: str = DEFAULT_VSRT_GLOB,
    shrt_glob: str = DEFAULT_SHRT_GLOB,
) -> None:
    frames: list[pd.DataFrame] = []
    total = len(points)
    for i, pt in enumerate(points, 1):
        name = pt.get("name") or f"{pt['lat']:.4f}_{pt['lon']:.4f}"
        code = pt.get("code", "")
        print(f"[{i}/{total}] {name}", flush=True)
        df = read_kma_grib_merged(
            data_folder,
            float(pt["lat"]),
            float(pt["lon"]),
            vsrt_glob=vsrt_glob,
            shrt_glob=shrt_glob,
        )
        df.insert(0, "point_code", code)
        df.insert(0, "point_name", name)
        frames.append(df)

    df_all = pd.concat(frames, ignore_index=True)

    missing = [c for c in OUTPUT_COLS if c not in df_all.columns]
    if missing:
        raise ValueError(f"저장할 열이 결과에 없습니다: {missing}")

    df_all[OUTPUT_COLS].to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"저장 완료: {output_csv.resolve()}  ({len(df_all)}행)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="KMA GRIB 강수 시계열 추출 → CSV")
    p.add_argument("--data-folder", type=Path, default=DEFAULT_DATA_FOLDER)
    p.add_argument("--points-csv",  type=Path, default=DEFAULT_POINTS_CSV)
    p.add_argument("--output",      type=Path, default=DEFAULT_OUTPUT_CSV)
    p.add_argument("--vsrt-glob",   default=DEFAULT_VSRT_GLOB)
    p.add_argument("--shrt-glob",   default=DEFAULT_SHRT_GLOB)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.data_folder.is_dir():
        sys.exit(f"오류: 데이터 폴더를 찾을 수 없습니다 — {args.data_folder}")
    if not args.points_csv.is_file():
        sys.exit(f"오류: 지점 CSV를 찾을 수 없습니다 — {args.points_csv}")

    points = load_points_csv(args.points_csv)
    print(f"지점 수: {len(points)},  데이터 폴더: {args.data_folder}")

    extract(
        data_folder=args.data_folder,
        points=points,
        output_csv=args.output,
        vsrt_glob=args.vsrt_glob,
        shrt_glob=args.shrt_glob,
    )


if __name__ == "__main__":
    main()
