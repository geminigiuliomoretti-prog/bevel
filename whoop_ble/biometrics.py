"""
On-Device Biometric DSP Engine (Zero Cloud / Local Execution).
Implements pure Python physiological signal processing algorithms:
1. HRV (RMSSD Task Force 1996 standard) & RHR (5-10th percentile sustained)
2. Sleep Staging (Awake, Light, Deep/SWS, REM), Sleep Performance (0-100%), Respiratory Rate (RSA 0.15-0.40 Hz)
3. Cardiovascular Strain (0.0 - 21.0 Karvonen HRR & Banister TRIMP) & Auto-Workout Detection (Keytel kcal/kJ)
4. Recovery Score (0 - 100% Multi-Factor Sigmoid: 60% HRV, 20% RHR, 15% Sleep, 5% Temp)
5. Real-Time Stress Monitor (0.0 - 3.0 Autonomic Arousal Decoupled from Physical Motion)
"""

import math
from typing import Any, Dict, List, Optional, Tuple


class BiometricsEngine:
    def __init__(
        self,
        user_age: int = 30,
        user_weight_kg: float = 75.0,
        user_gender: str = "male",
        default_baseline_hrv: float = 55.0,
        default_baseline_rhr: float = 58.0,
        default_baseline_temp_c: float = 33.5,
    ):
        self.age = user_age
        self.weight_kg = user_weight_kg
        self.gender = user_gender.lower()
        self.hr_max = 220 - self.age

        # Baseline parameters (rolling 14-day or defaults)
        self.baseline_hrv = default_baseline_hrv
        self.baseline_hrv_std = 15.0
        self.baseline_rhr = default_baseline_rhr
        self.baseline_rhr_std = 5.0
        self.baseline_temp_c = default_baseline_temp_c

    # =========================================================================
    # 1. HRV (RMSSD) & RHR (Resting Heart Rate)
    # =========================================================================

    def calculate_rmssd(self, rr_ms_list: List[int]) -> Optional[float]:
        """
        Calculates RMSSD according to Task Force 1996 standard:
        RMSSD = sqrt( (1 / (N - 1)) * sum( (RR_{i+1} - RR_i)^2 ) )
        Requires at least 2 consecutive intervals.
        """
        if not rr_ms_list or len(rr_ms_list) < 2:
            return None

        diffs_sq = [(rr_ms_list[i + 1] - rr_ms_list[i]) ** 2 for i in range(len(rr_ms_list) - 1)]
        mean_diff_sq = sum(diffs_sq) / float(len(diffs_sq))
        return round(math.sqrt(mean_diff_sq), 2)

    def calculate_rhr(self, hr_list: List[int], percentile: float = 0.10) -> Optional[float]:
        """
        Calculates Resting Heart Rate (RHR):
        Extracts sustained low heart rates (5th-10th percentile) during resting/sleep.
        """
        valid_hrs = [hr for hr in hr_list if 35 <= hr <= 120]
        if not valid_hrs:
            return None

        sorted_hrs = sorted(valid_hrs)
        k = int(len(sorted_hrs) * percentile)
        k = max(0, min(k, len(sorted_hrs) - 1))
        # Average around the k-th percentile for stability
        window = sorted_hrs[max(0, k - 2) : min(len(sorted_hrs), k + 3)]
        return round(sum(window) / float(len(window)), 1)

    # =========================================================================
    # 2. Sleep Staging, Performance & Respiratory Rate (RSA)
    # =========================================================================

    def stage_sleep_epoch(
        self,
        hr_window: List[int],
        rr_window: List[int],
        movement_delta_window: List[float],
        hardware_sleep_state: int,
        rhr: float,
    ) -> str:
        """
        Classifies a 30-second epoch into:
        - 'AWAKE': active motion or high heart rate
        - 'LIGHT': low motion, HR near baseline
        - 'DEEP': near-zero motion, lowest HR dip, high autonomic stability
        - 'REM': near-zero motion, but elevated HR/RR variability
        """
        avg_motion = sum(movement_delta_window) / max(1, len(movement_delta_window))
        avg_hr = sum(hr_window) / max(1, len(hr_window)) if hr_window else rhr
        rmssd = self.calculate_rmssd(rr_window) or 20.0

        # Awake threshold
        if avg_motion > 0.035 or avg_hr > (rhr + 20) or hardware_sleep_state == 0:
            return "AWAKE"

        # If motion is extremely low
        if avg_motion < 0.015:
            # Check autonomic variability
            # Deep sleep (SWS): lowest HR dip, low RMSSD variation / autonomic calmness
            if avg_hr <= (rhr + 5) and rmssd < 45.0:
                return "DEEP"
            # REM sleep: high RMSSD / variable autonomic activity
            elif rmssd >= 45.0 or (rhr + 5 < avg_hr <= rhr + 14):
                return "REM"
            else:
                return "LIGHT"

        return "LIGHT"

    def calculate_sleep_metrics(
        self,
        records_1hz: List[Dict[str, Any]],
        rhr: float,
        baseline_sleep_need_hours: float = 8.0,
        sleep_debt_hours: float = 0.0,
        strain_surplus_hours: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Analyzes full sleep session in 30-second epochs.
        """
        if not records_1hz:
            return {
                "total_sleep_time_seconds": 0,
                "sleep_duration_hours": 0.0,
                "sleep_performance_pct": 0.0,
                "sleep_efficiency_pct": 0.0,
                "sleep_consistency_pct": 0.0,
                "stage_durations_seconds": {"awake": 0, "light": 0, "deep": 0, "rem": 0},
                "stage_percentages": {"awake": 0.0, "light": 0.0, "deep": 0.0, "rem": 0.0},
            }

        # Divide into 30-second chunks
        epoch_size = 30
        stage_counts = {"AWAKE": 0, "LIGHT": 0, "DEEP": 0, "REM": 0}

        for i in range(0, len(records_1hz), epoch_size):
            chunk = records_1hz[i : i + epoch_size]
            hr_win = [r["primary_hr"] for r in chunk if r.get("primary_hr", 0) > 0]
            rrs_win: List[int] = []
            for r in chunk:
                rrs_win.extend(r.get("rr_intervals_ms") or [])
            motion_win = [r.get("movement_delta_g", 0.0) or 0.0 for r in chunk]
            hw_sleep = chunk[0].get("sleep_state", 1)

            stage = self.stage_sleep_epoch(hr_win, rrs_win, motion_win, hw_sleep, rhr)
            stage_counts[stage] += len(chunk)

        total_time_in_bed_sec = len(records_1hz)
        asleep_seconds = stage_counts["LIGHT"] + stage_counts["DEEP"] + stage_counts["REM"]
        asleep_hours = asleep_seconds / 3600.0

        efficiency = (asleep_seconds / float(total_time_in_bed_sec) * 100.0) if total_time_in_bed_sec > 0 else 0.0

        total_need_hours = baseline_sleep_need_hours + sleep_debt_hours + strain_surplus_hours
        sleep_performance = min(100.0, round((asleep_hours / total_need_hours) * 100.0, 1)) if total_need_hours > 0 else 0.0

        # Stages percentages
        stage_pcts = {
            k.lower(): round((v / float(total_time_in_bed_sec) * 100.0), 1) if total_time_in_bed_sec > 0 else 0.0
            for k, v in stage_counts.items()
        }

        return {
            "total_time_in_bed_seconds": total_time_in_bed_sec,
            "total_sleep_time_seconds": asleep_seconds,
            "sleep_duration_hours": round(asleep_hours, 2),
            "sleep_need_hours": round(total_need_hours, 2),
            "sleep_performance_pct": sleep_performance,
            "sleep_efficiency_pct": round(efficiency, 1),
            "stage_durations_seconds": {k.lower(): v for k, v in stage_counts.items()},
            "stage_percentages": stage_pcts,
        }

    def estimate_respiratory_rate_rsa(self, rr_intervals_ms: List[int]) -> Optional[float]:
        """
        Estimates Respiratory Rate (RPM) via Respiratory Sinus Arrhythmia (RSA).
        Detects periodic modulation of RR intervals in the 0.15 - 0.40 Hz band (9 - 24 breaths/min).
        Uses peak autocorrelation in the respiratory cycle lag window.
        """
        if not rr_intervals_ms or len(rr_intervals_ms) < 30:
            return 14.5  # Median physiological default

        # Convert RR intervals into an approximated 4Hz uniformly sampled series
        # Mean RR in seconds:
        mean_rr = (sum(rr_intervals_ms) / float(len(rr_intervals_ms))) / 1000.0
        if mean_rr <= 0:
            return 14.5

        # Detrend: subtract mean
        norm_rrs = [r - (mean_rr * 1000.0) for r in rr_intervals_ms]

        # Autocorrelation over lags corresponding to 9-24 breaths/min
        # Period T in seconds = 60 / RPM -> for 9..24 RPM, T is 2.5s .. 6.67s
        # In terms of beat intervals: lag = T / mean_rr
        min_lag = max(2, int(2.5 / mean_rr))
        max_lag = min(len(norm_rrs) // 2, int(6.67 / mean_rr))

        if min_lag >= max_lag:
            return 14.0

        best_lag = None
        best_corr = -1e9
        n = len(norm_rrs)

        for lag in range(min_lag, max_lag + 1):
            corr = sum(norm_rrs[i] * norm_rrs[i + lag] for i in range(n - lag))
            if corr > best_corr:
                best_corr = corr
                best_lag = lag

        if best_lag is not None and best_lag > 0:
            period_seconds = best_lag * mean_rr
            if period_seconds > 0:
                rpm = 60.0 / period_seconds
                # Clamped within physiological human limits 9.0 - 24.0 RPM
                return round(max(9.0, min(24.0, rpm)), 1)

        return 14.5

    # =========================================================================
    # 3. Cardiovascular Strain (0.0 - 21.0) & Workout Auto-Detection
    # =========================================================================

    def calculate_cardiovascular_strain(
        self,
        hr_series: List[int],
        rhr: float,
    ) -> Tuple[float, Dict[str, int]]:
        """
        Calculates WHOOP-style cardiovascular strain (0.0 - 21.0) using Karvonen Heart Rate Reserve:
        %HRR = (HR - RHR) / (HRmax - RHR)
        
        Zones:
        - Zone 1: 50% - 60% HRR (Recovery)
        - Zone 2: 60% - 70% HRR (Base Aerobic)
        - Zone 3: 70% - 80% HRR (Endurance)
        - Zone 4: 80% - 90% HRR (Threshold)
        - Zone 5: 90% - 100% HRR (Anaerobic Max)
        
        TRIMP integration with exponential weighting by zone, mapped logarithmically to 0.0 - 21.0.
        """
        if not hr_series or len(hr_series) == 0:
            return (0.0, {"zone1": 0, "zone2": 0, "zone3": 0, "zone4": 0, "zone5": 0})

        hr_range = max(10.0, float(self.hr_max - rhr))
        trimp_acc = 0.0

        zone_seconds = {
            "zone1": 0,
            "zone2": 0,
            "zone3": 0,
            "zone4": 0,
            "zone5": 0,
        }

        for hr in hr_series:
            if hr <= rhr:
                continue

            hrr = (hr - rhr) / hr_range
            hrr = min(1.0, max(0.0, hrr))

            # Weight and zone classification
            if hrr >= 0.90:
                zone_seconds["zone5"] += 1
                w = 5.5
            elif hrr >= 0.80:
                zone_seconds["zone4"] += 1
                w = 3.5
            elif hrr >= 0.70:
                zone_seconds["zone3"] += 1
                w = 2.2
            elif hrr >= 0.60:
                zone_seconds["zone2"] += 1
                w = 1.5
            elif hrr >= 0.50:
                zone_seconds["zone1"] += 1
                w = 1.0
            else:
                # Below 50% HRR: minimal aerobic stress
                w = 0.3 * (hrr / 0.50)

            # Second-by-second TRIMP increment
            trimp_acc += (hrr * w) / 60.0

        # Logarithmic mapping from TRIMP to WHOOP 0.0 - 21.0 scale:
        # Strain = 21 * (1 - exp(-k * TRIMP^0.65))
        # Calibrated: 15min workout -> ~7-9, 45min workout -> ~12-14, 90min intense -> ~16-18
        strain = 21.0 * (1.0 - math.exp(-0.075 * (trimp_acc ** 0.65)))
        strain = round(max(0.0, min(21.0, strain)), 1)

        return (strain, zone_seconds)

    def detect_workouts(
        self,
        records_1hz: List[Dict[str, Any]],
        rhr: float,
        min_duration_minutes: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Auto-detects workouts:
        Contiguous periods >= min_duration_minutes with HR in Zone 2+ (>= 60% HRR)
        and active accelerometer motion.
        Calculates session strain, Keytel calories, and kJ.
        """
        workouts: List[Dict[str, Any]] = []
        if len(records_1hz) < (min_duration_minutes * 60):
            return workouts

        hr_thresh = rhr + 0.55 * (self.hr_max - rhr)
        current_streak: List[Dict[str, Any]] = []

        for rec in records_1hz:
            hr = rec.get("primary_hr") or 0
            motion = rec.get("movement_delta_g") or 0.0

            # Elevated HR with active motion
            is_active = (hr >= hr_thresh and motion > 0.02) or (hr >= (rhr + 0.75 * (self.hr_max - rhr)))

            if is_active:
                current_streak.append(rec)
            else:
                if len(current_streak) >= (min_duration_minutes * 60):
                    workouts.append(self._build_workout_payload(current_streak, rhr))
                current_streak = []

        if len(current_streak) >= (min_duration_minutes * 60):
            workouts.append(self._build_workout_payload(current_streak, rhr))

        return workouts

    def _build_workout_payload(self, records: List[Dict[str, Any]], rhr: float) -> Dict[str, Any]:
        start_ts = records[0]["timestamp_unix"]
        end_ts = records[-1]["timestamp_unix"]
        duration_sec = len(records)
        hrs = [r["primary_hr"] for r in records if r.get("primary_hr", 0) > 0]
        avg_hr = round(sum(hrs) / float(len(hrs)), 1) if hrs else rhr
        max_hr = max(hrs) if hrs else int(rhr)

        strain, zones = self.calculate_cardiovascular_strain(hrs, rhr)

        # Keytel Formula for energy expenditure (kcal/min):
        # Male: (-55.0969 + (0.6309 x HR) + (0.1988 x Weight) + (0.2017 x Age)) / 4.184
        # Female: (-20.4022 + (0.4472 x HR) - (0.1263 x Weight) + (0.074 x Age)) / 4.184
        duration_min = duration_sec / 60.0
        if self.gender == "female":
            cal_per_min = (-20.4022 + (0.4472 * avg_hr) - (0.1263 * self.weight_kg) + (0.074 * self.age)) / 4.184
        else:
            cal_per_min = (-55.0969 + (0.6309 * avg_hr) + (0.1988 * self.weight_kg) + (0.2017 * self.age)) / 4.184

        calories_kcal = round(max(0.0, cal_per_min * duration_min), 1)
        kilojoules = round(calories_kcal * 4.184, 1)

        return {
            "serial_number": records[0]["serial_number"],
            "start_timestamp_unix": start_ts,
            "end_timestamp_unix": end_ts,
            "duration_seconds": duration_sec,
            "workout_strain": strain,
            "avg_hr_bpm": avg_hr,
            "max_hr_bpm": max_hr,
            "calories_kcal": calories_kcal,
            "kilojoules": kilojoules,
            "zone_durations": zones,
            "auto_detected": 1,
        }

    # =========================================================================
    # 4. Recovery Score (0 - 100%)
    # =========================================================================

    def calculate_recovery_score(
        self,
        hrv_rmssd: float,
        rhr: float,
        sleep_performance_pct: float,
        skin_temp_c: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculates WHOOP-equivalent Recovery Score (0 - 100%):
        Multi-metric weighted model:
        - 60% HRV (RMSSD) Z-score vs baseline
        - 20% Inverse RHR Z-score (lower RHR = better recovery)
        - 15% Sleep Performance (0 - 100%)
        - 5% Skin Temperature stability (deviation from 33.5C baseline)
        
        Mapped via sigmoid to 1% - 99%:
        - GREEN: 67% - 99%
        - YELLOW: 34% - 66%
        - RED: 1% - 33%
        """
        # Z-scores
        z_hrv = (hrv_rmssd - self.baseline_hrv) / max(1.0, self.baseline_hrv_std)
        z_rhr = -(rhr - self.baseline_rhr) / max(1.0, self.baseline_rhr_std)  # Inverted

        z_sleep = (sleep_performance_pct - 70.0) / 15.0

        delta_temp = abs(skin_temp_c - self.baseline_temp_c) if skin_temp_c else 0.0
        z_temp = -max(0.0, (delta_temp - 0.3) / 0.5)

        # Weighted Composite Index
        s = (0.60 * z_hrv) + (0.20 * z_rhr) + (0.15 * z_sleep) + (0.05 * z_temp)

        # Sigmoid transfer function centered around 50%
        rec_pct = 100.0 / (1.0 + math.exp(-0.85 * s))
        score = int(round(max(1.0, min(99.0, rec_pct))))

        if score >= 67:
            state = "GREEN"
        elif score >= 34:
            state = "YELLOW"
        else:
            state = "RED"

        return {
            "recovery_score": score,
            "recovery_state": state,
            "hrv_rmssd_ms": round(hrv_rmssd, 1),
            "resting_hr_bpm": round(rhr, 1),
            "sleep_performance_pct": round(sleep_performance_pct, 1),
            "skin_temp_c": round(skin_temp_c, 1) if skin_temp_c else self.baseline_temp_c,
            "factors": {
                "hrv_z_score": round(z_hrv, 2),
                "rhr_z_score": round(z_rhr, 2),
                "sleep_z_score": round(z_sleep, 2),
                "temp_delta_c": round(delta_temp, 2),
                "composite_s": round(s, 2),
            },
        }

    # =========================================================================
    # 5. Real-Time Stress Monitor (0.0 - 3.0)
    # =========================================================================

    def calculate_stress_score(
        self,
        current_hr: int,
        current_rmssd: float,
        movement_delta_g: float,
        rhr: float,
    ) -> Dict[str, Any]:
        """
        Calculates instantaneous / rolling 1-5 min Stress Score (0.0 - 3.0):
        - LOW: < 1.0 (Parasympathetic dominance / Calm)
        - MEDIUM: 1.0 - 1.9 (Mild arousal / Normal daytime engagement)
        - HIGH: 2.0 - 3.0 (Sympathetic dominance / Acute Stress)
        
        Movement Decoupling:
        If movement_delta_g is elevated, the HR increase is physically driven (motion),
        NOT autonomic stress, so the stress score is suppressed.
        If movement is low while HR rises and HRV drops, sympathetic stress is high.
        """
        # HR elevation above resting baseline
        delta_hr = max(0.0, float(current_hr - rhr))
        hr_component = delta_hr / 35.0  # normalized

        # HRV suppression relative to baseline
        hrv_ratio = current_rmssd / max(1.0, self.baseline_hrv)
        hrv_suppression = max(0.0, 1.0 - min(1.0, hrv_ratio))

        # Raw sympathetic arousal
        raw_stress = (hr_component * 1.5) + (hrv_suppression * 1.5)

        # Movement Decoupling Penalty:
        # movement_delta_g > 0.035 g indicates physical motion
        motion_factor = min(1.0, movement_delta_g / 0.08)
        # Suppress motion-induced HR elevation from stress score
        autonomic_stress = raw_stress * (1.0 - (0.80 * motion_factor))

        stress_score = round(max(0.0, min(3.0, autonomic_stress)), 2)

        if stress_score >= 2.0:
            category = "HIGH"
        elif stress_score >= 1.0:
            category = "MEDIUM"
        else:
            category = "LOW"

        return {
            "stress_score": stress_score,
            "category": category,
            "current_hr": current_hr,
            "current_rmssd": round(current_rmssd, 1),
            "movement_delta_g": round(movement_delta_g, 4),
            "is_motion_artifact": motion_factor > 0.50,
        }

    # =========================================================================
    # Full Biometric Pipeline Runner
    # =========================================================================

    def run_full_pipeline(
        self,
        serial_number: str,
        records_1hz: List[Dict[str, Any]],
        rr_intervals_valid: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Executes the complete on-device biometric DSP suite on a set of records.
        """
        if not records_1hz:
            return {"status": "NO_DATA", "serial_number": serial_number}

        # 1. Primary HR & RR
        hrs = [r["primary_hr"] for r in records_1hz if r.get("primary_hr", 0) > 0]
        rrs = [r["rr_ms"] for r in rr_intervals_valid]

        rhr = self.calculate_rhr(hrs) or self.baseline_rhr
        overall_rmssd = self.calculate_rmssd(rrs) or self.baseline_hrv

        # 2. Temperature
        temps = [r["skin_temp_c"] for r in records_1hz if r.get("skin_temp_c")]
        avg_temp = round(sum(temps) / float(len(temps)), 1) if temps else self.baseline_temp_c

        # 3. Sleep & Respiratory Rate
        sleep_res = self.calculate_sleep_metrics(records_1hz, rhr)
        resp_rate = self.estimate_respiratory_rate_rsa(rrs)

        # 4. Cardiovascular Strain
        strain, zones = self.calculate_cardiovascular_strain(hrs, rhr)
        detected_workouts = self.detect_workouts(records_1hz, rhr)

        # 5. Recovery Score
        recovery_res = self.calculate_recovery_score(
            hrv_rmssd=overall_rmssd,
            rhr=rhr,
            sleep_performance_pct=sleep_res["sleep_performance_pct"],
            skin_temp_c=avg_temp,
        )

        # 6. Stress Score (average over rolling epochs)
        stress_scores: List[float] = []
        for r in records_1hz:
            hr_val = r.get("primary_hr", 0)
            if hr_val > 0:
                sc = self.calculate_stress_score(
                    current_hr=hr_val,
                    current_rmssd=overall_rmssd,
                    movement_delta_g=r.get("movement_delta_g", 0.0),
                    rhr=rhr,
                )
                stress_scores.append(sc["stress_score"])

        avg_stress = round(sum(stress_scores) / float(len(stress_scores)), 2) if stress_scores else 0.50
        stress_category = "HIGH" if avg_stress >= 2.0 else ("MEDIUM" if avg_stress >= 1.0 else "LOW")

        return {
            "status": "SUCCESS",
            "serial_number": serial_number,
            "total_records_processed": len(records_1hz),
            "valid_rr_processed": len(rrs),
            "recovery": recovery_res,
            "strain": {
                "day_strain": strain,
                "max_hr_bpm": max(hrs) if hrs else int(rhr),
                "avg_hr_bpm": round(sum(hrs) / float(len(hrs)), 1) if hrs else rhr,
                "zone_durations_seconds": zones,
                "workouts_detected_count": len(detected_workouts),
                "workouts": detected_workouts,
            },
            "sleep": sleep_res,
            "respiratory_rate_rpm": resp_rate,
            "rhr_bpm": rhr,
            "hrv_rmssd_ms": overall_rmssd,
            "skin_temp_c": avg_temp,
            "stress": {
                "avg_stress_score": avg_stress,
                "stress_category": stress_category,
            },
        }
