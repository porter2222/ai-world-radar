from __future__ import annotations


class RankingAgentStub:
    def rank(self, cluster: dict) -> dict:
        heat_score = cluster["heat_score"]
        impact_score = cluster["impact_score"]
        audience_value_score = cluster["audience_value_score"]
        freshness_score = 0.8
        ranking_score = (
            0.45 * heat_score
            + 0.25 * impact_score
            + 0.20 * audience_value_score
            + 0.10 * freshness_score
        )

        ranked = dict(cluster)
        ranked.update(
            {
                "freshness_score": freshness_score,
                "ranking_score": ranking_score,
                "ranking_reason": "Deterministic stub ranking: HN heat plus default impact and audience value.",
                "publish_decision": "publish" if ranking_score >= 0.2 else "hold",
                "brief_candidate": ranking_score >= 0.35,
                "cluster_status": "ranked",
            }
        )
        return ranked
