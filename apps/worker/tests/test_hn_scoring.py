from worker.collectors.hn_algolia import calculate_hn_heat_score


def test_calculate_hn_heat_score_uses_points_plus_double_comments():
    assert calculate_hn_heat_score(points=11, num_comments=7) == 25


def test_calculate_hn_heat_score_treats_missing_metrics_as_zero():
    assert calculate_hn_heat_score(points=None, num_comments=None) == 0
