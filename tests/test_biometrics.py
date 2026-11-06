"""
Unit tests for on-device Biometrics DSP Engine.
"""

from whoop_ble.biometrics import BiometricsEngine


def test_biometrics():
    engine = BiometricsEngine()

    # 1. Test RMSSD
    rrs = [1000, 1020, 980, 1010, 990, 1005]
    rmssd = engine.calculate_rmssd(rrs)
    print(f"Calculated RMSSD: {rmssd} ms")
    assert rmssd is not None and 10.0 <= rmssd <= 50.0

    # 2. Test RHR
    hrs = [60, 62, 59, 58, 57, 58, 65, 70, 58, 59]
    rhr = engine.calculate_rhr(hrs)
    print(f"Calculated RHR: {rhr} BPM")
    assert rhr is not None and 56 <= rhr <= 60

    # 3. Test Strain
    test_hrs = [60] * 300 + [140] * 600 + [160] * 300
    strain, zones = engine.calculate_cardiovascular_strain(test_hrs, rhr=58.0)
    print(f"Calculated Strain: {strain}, Zones: {zones}")
    assert 8.0 <= strain <= 17.0

    # 4. Test Recovery Score
    rec = engine.calculate_recovery_score(
        hrv_rmssd=65.0, rhr=55.0, sleep_performance_pct=85.0, skin_temp_c=33.5
    )
    print(f"Calculated Recovery: {rec['recovery_score']}% ({rec['recovery_state']})")
    assert rec["recovery_state"] in ("GREEN", "YELLOW")
    assert 1 <= rec["recovery_score"] <= 99

    # 5. Test Stress
    stress_calm = engine.calculate_stress_score(
        current_hr=60, current_rmssd=65.0, movement_delta_g=0.002, rhr=58.0
    )
    print(f"Stress Calm: {stress_calm['stress_score']} ({stress_calm['category']})")
    assert stress_calm["stress_score"] < 1.0

    stress_acute = engine.calculate_stress_score(
        current_hr=85, current_rmssd=20.0, movement_delta_g=0.002, rhr=58.0
    )
    print(f"Stress Acute (stationary): {stress_acute['stress_score']} ({stress_acute['category']})")
    assert stress_acute["stress_score"] >= 1.5

    stress_motion = engine.calculate_stress_score(
        current_hr=85, current_rmssd=20.0, movement_delta_g=0.08, rhr=58.0
    )
    print(f"Stress with motion decoupling: {stress_motion['stress_score']} ({stress_motion['category']})")
    assert stress_motion["stress_score"] < stress_acute["stress_score"]

    print("ALL BIOMETRICS UNIT TESTS PASSED!")


if __name__ == "__main__":
    test_biometrics()
