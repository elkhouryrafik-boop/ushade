import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import traceback


def test_detection_loads():
    from src.detection import DetectionService
    svc = DetectionService()
    df = svc.get_all()
    assert len(df) >= 20, f"Expected at least 20 records, got {len(df)}"
    print(f"  PASS test_detection_loads: {len(df)} records")


def test_summary_has_required_keys():
    from src.detection import DetectionService
    svc = DetectionService()
    summary = svc.get_summary()
    required = [
        "total_sources", "total_m2", "total_kg",
        "total_carbon_avoided_kg", "total_carbon_avoided_tonnes",
        "materials_detected", "expiring_count", "available_now_count",
    ]
    for k in required:
        assert k in summary, f"Missing key: {k}"
    print(f"  PASStest_summary_has_required_keys: all {len(required)} keys present")


def test_classifier_offline():
    from src.classifier import MaterialClassifier
    c = MaterialClassifier()
    result = c.classify("blue nylon netting construction site")
    assert result["best_match_code"] == "NET", f"Expected NET, got {result['best_match_code']}"
    print(f"  PASStest_classifier_offline: best_match_code = {result['best_match_code']}")


def test_predictions_returns_dataframe():
    import pandas as pd
    from src.predictions import PredictionEngine
    engine = PredictionEngine()
    df = engine.all_predictions()
    assert isinstance(df, pd.DataFrame), "Expected a DataFrame"
    assert len(df) >= 10, f"Expected at least 10 predictions, got {len(df)}"
    print(f"  PASStest_predictions_returns_dataframe: {len(df)} predictions")


def test_carbon_net_benefit():
    from src.logistics import LogisticsOptimiser
    opt = LogisticsOptimiser()
    result = opt.carbon_comparison(total_transport_carbon_kg=10, total_quantity_m2=100)
    assert result["net_benefit_is_positive"] is True, (
        f"Expected positive net benefit, got net_benefit_kg={result['net_benefit_kg']}"
    )
    print(f"  PASStest_carbon_net_benefit: net_benefit_kg={result['net_benefit_kg']}")


if __name__ == "__main__":
    tests = [
        test_detection_loads,
        test_summary_has_required_keys,
        test_classifier_offline,
        test_predictions_returns_dataframe,
        test_carbon_net_benefit,
    ]
    passed = 0
    failed = 0
    print("\n=== Material Harvesting Engine — Core Tests ===\n")
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  FAIL {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{'='*48}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
