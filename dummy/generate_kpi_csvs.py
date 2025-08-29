# generate_kpi_csvs.py
import csv
import os
import stat
import math
import random
from pathlib import Path
from datetime import date, datetime, time, timedelta
from calendar import monthrange
from typing import Optional, Iterator, Tuple

# Deterministic randomness
RNG = random.Random(42)

# Output directory
OUT_DIR = Path("./kpi_csv_out")
OUT_DIR.mkdir(parents=True, exist_ok=True)

CLIENT_ID = 2  # as in your sample

# KPI catalog using your provided IDs and schema
KPIS = [
    # Daily (originally 1 row/day; now 10 rows/day)
    {"name": "on_time_performance", "unit": "%", "frequency": "Daily", "kpi_threshold": "68958470d97275e03c78ebc0"},
    {"name": "flight_cancellation_rate", "unit": "%", "frequency": "Daily", "kpi_threshold": "6895848ad97275e03c78ebc1"},
    {"name": "passenger_load_factor", "unit": "%", "frequency": "Daily", "kpi_threshold": "689584bbd97275e03c78ebc4"},
    {"name": "baggage_mishandling_rate", "unit": "Count", "frequency": "Daily", "kpi_threshold": "689584c6d97275e03c78ebc5"},
    {"name": "aircraft_utilization_rate", "unit": "Hours", "frequency": "Daily", "kpi_threshold": "68958562d97275e03c78ebcd"},

    # Was “Minutes” with 20/day; now 10/day
    {"name": "average_delay_per_flight", "unit": "Minutes", "frequency": "Daily", "kpi_threshold": "689584dfd97275e03c78ebc7"},
    {"name": "check_in_counter_wait_time", "unit": "Minutes", "frequency": "Daily", "kpi_threshold": "6895854fd97275e03c78ebcc"},

    # Monthly (originally 1 row/month; now 10 rows/day)
    {"name": "revenue_per_available_seat_kilometer_rask", "unit": "USD", "frequency": "Monthly", "kpi_threshold": "689584a2d97275e03c78ebc2"},
    {"name": "cost_per_available_seat_kilometer_cask", "unit": "USD", "frequency": "Monthly", "kpi_threshold": "689584b0d97275e03c78ebc3"},
    {"name": "net_promoter_score_nps", "unit": "Score", "frequency": "Monthly", "kpi_threshold": "689584d2d97275e03c78ebc6"},
    {"name": "employee_cost_ratio", "unit": "%", "frequency": "Monthly", "kpi_threshold": "689584f3d97275e03c78ebc8"},
    {"name": "fuel_cost_per_kilometer", "unit": "USD", "frequency": "Monthly", "kpi_threshold": "68958503d97275e03c78ebc9"},
    {"name": "customer_complaint_rate", "unit": "Count", "frequency": "Monthly", "kpi_threshold": "68958515d97275e03c78ebca"},

    # Quarterly (originally 1 row/quarter start; now 10 rows/day)
    {"name": "return_on_aircraft_assets", "unit": "%", "frequency": "Quarterly", "kpi_threshold": "68958532d97275e03c78ebcb"},
]

# Full range: Aug 2024 -> Jul 2025 (inclusive)
START_YEAR, START_MONTH = 2024, 8
END_YEAR, END_MONTH = 2025, 8


def months_range(start_year: int, start_month: int, end_year: int, end_month: int) -> Iterator[Tuple[int, int]]:
    y, m = start_year, start_month
    while (y < end_year) or (y == end_year and m <= end_month):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def sample_logged_ats(d: date, count: int = 10):
    # Evenly spaced between 08:00 and 18:00
    start = datetime.combine(d, time(8, 0))
    end = datetime.combine(d, time(18, 0))
    total_minutes = int((end - start).total_seconds() // 60)
    step = total_minutes // (count - 1) if count > 1 else total_minutes
    return [(start + timedelta(minutes=step * i)).strftime("%Y-%m-%dT%H:%M:%S") for i in range(count)]


def doy(d: date) -> int:
    return d.timetuple().tm_yday


def month_phase(y: int, m: int) -> float:
    # 0..1 across the year, based on month
    return (m - 1) / 12.0


def gen_value(kpi_name: str, unit: str, freq: str, d: date, sample_idx: Optional[int]) -> float | int:
    # Trendy but reasonable ranges per KPI
    # Add light seasonal/weekly-ish variation via sin waves + small noise
    dy = doy(d)
    phase30 = 2 * math.pi * (dy % 30) / 30.0
    phase14 = 2 * math.pi * (dy % 14) / 14.0
    noise = RNG.uniform(-1.0, 1.0)

    # Sub-daily shape across the 10 samples to vary within a day
    i = sample_idx or 0
    intra = math.sin(math.pi * i / 9.0) ** 2  # 0..1

    if kpi_name == "on_time_performance":
        val = 85 + 6 * math.sin(phase30) + noise * 2 - 2 * intra
        return round(clamp(val, 70, 98), 1)

    if kpi_name == "flight_cancellation_rate":
        val = 1.2 + 0.7 * math.sin(phase14) + noise * 0.3 + 0.3 * intra
        return round(clamp(val, 0.0, 3.0), 2)

    if kpi_name == "passenger_load_factor":
        val = 78 + 7 * math.sin(phase30) + noise * 2 + 1.0 * intra
        return round(clamp(val, 60, 95), 1)

    if kpi_name == "baggage_mishandling_rate":
        # integer count/day
        base = 4 + 1.5 * math.sin(phase14) + noise + 0.5 * intra
        return int(clamp(round(base), 1, 10))

    if kpi_name == "aircraft_utilization_rate":
        val = 8.2 + 1.0 * math.sin(phase30) + noise * 0.3 + 0.4 * intra
        return round(clamp(val, 6.0, 11.0), 1)

    if kpi_name == "average_delay_per_flight":
        # Keep within 5..30 minutes; two peaks across the 10 samples
        peak = math.sin(math.pi * i / 9.0) ** 2 + 0.5 * math.sin(2 * math.pi * i / 9.0) ** 2
        val = 10 + 12 * peak + noise * 2
        return round(clamp(val, 5, 30), 1)

    if kpi_name == "check_in_counter_wait_time":
        # Busy periods cause higher wait; keep within 2..20 minutes
        val = 6 + 6 * intra + noise * 1.2
        return round(clamp(val, 2, 20), 1)

    if kpi_name == "revenue_per_available_seat_kilometer_rask":
        ph = month_phase(d.year, d.month)
        val = 2.55 + 0.15 * math.sin(2 * math.pi * ph) + noise * 0.05 + 0.02 * (intra - 0.5)
        return round(clamp(val, 2.3, 3.1), 2)

    if kpi_name == "cost_per_available_seat_kilometer_cask":
        ph = month_phase(d.year, d.month)
        val = 3.75 + 0.15 * math.sin(2 * math.pi * ph + 0.4) + noise * 0.05 + 0.02 * (intra - 0.5)
        return round(clamp(val, 3.3, 4.2), 2)

    if kpi_name == "net_promoter_score_nps":
        ph = month_phase(d.year, d.month)
        val = 30 + 6 * math.sin(2 * math.pi * ph + 0.2) + noise * 2 + 2.0 * (intra - 0.5)
        return int(clamp(round(val), 0, 100))

    if kpi_name == "employee_cost_ratio":
        ph = month_phase(d.year, d.month)
        val = 31 + 3.5 * math.sin(2 * math.pi * ph + 0.6) + noise * 1.2 + 0.6 * (intra - 0.5)
        return round(clamp(val, 20, 45), 1)

    if kpi_name == "fuel_cost_per_kilometer":
        ph = month_phase(d.year, d.month)
        val = 1.72 + 0.12 * math.sin(2 * math.pi * ph + 0.8) + noise * 0.03 + 0.01 * (intra - 0.5)
        return round(clamp(val, 1.5, 2.0), 3)

    if kpi_name == "customer_complaint_rate":
        # integer count per (now) sub-daily sample
        ph = month_phase(d.year, d.month)
        base = 25 + 8 * math.sin(2 * math.pi * ph + 0.3) + noise * 3 + 1.0 * (intra - 0.5)
        return int(clamp(round(base), 5, 60))

    if kpi_name == "return_on_aircraft_assets":
        # allow small intra-day variation; keep within 5..10%
        ph = month_phase(d.year, d.month)
        val = 7.6 + 0.6 * math.sin(2 * math.pi * ph) + noise * 0.2 + 0.1 * (intra - 0.5)
        return round(clamp(val, 5.0, 10.0), 2)

    # Default guard
    return 0


def write_month_csv(year: int, month: int):
    days_in_month = monthrange(year, month)[1]
    out_path = OUT_DIR / f"kpis_{year}_{month:02d}.csv"

    # Overwrite safely (handle read-only/locked cases)
    try:
        if out_path.exists():
            os.chmod(out_path, stat.S_IWRITE)
            out_path.unlink()
    except Exception as e:
        ts = datetime.now().strftime("%H%M%S")
        alt = OUT_DIR / f"{out_path.stem}_{ts}{out_path.suffix}"
        print(f"⚠️ Could not overwrite {out_path} ({e}); writing to {alt} instead.")
        out_path = alt

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "date", "kpi_name", "logged_value", "unit", "frequency",
            "kpi_threshold", "client_id", "logged_at"
        ])

        for day in range(1, days_in_month + 1):
            d = date(year, month, day)
            ats = sample_logged_ats(d, 10)  # 10 rows per day per KPI

            for k in KPIS:
                name = k["name"]
                unit = k["unit"]
                freq = k["frequency"]
                kt = k["kpi_threshold"]

                for i, at_str in enumerate(ats):
                    writer.writerow([
                        d.isoformat(),
                        name,
                        gen_value(name, unit, freq, d, i),
                        unit,
                        freq,
                        kt,
                        CLIENT_ID,
                        at_str,
                    ])

    print(f"✔ Wrote {out_path}")


def main():
    for (y, m) in months_range(START_YEAR, START_MONTH, END_YEAR, END_MONTH):
        write_month_csv(y, m)


if __name__ == "__main__":
    main()