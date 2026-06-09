from worker.collectors.hn_algolia import calculate_hn_heat_score


def test_calculate_hn_heat_score_uses_points_plus_double_comments():
    """验证 HN 热度分公式。

    输入：points=11、num_comments=7。
    输出：断言结果为 25。
    """
    assert calculate_hn_heat_score(points=11, num_comments=7) == 25


def test_calculate_hn_heat_score_treats_missing_metrics_as_zero():
    """验证热度分对空值的兜底。

    输入：points 和 num_comments 都为 None。
    输出：断言结果为 0。
    """
    assert calculate_hn_heat_score(points=None, num_comments=None) == 0
