from __future__ import annotations


class EventClusterAgentStub:
    """事件聚合 stub。

    输入：单张 EvidenceCard 字典。
    输出：一证据卡一事件的 EventCluster 字典，保证第一轮 pipeline 可跑通。
    """

    def cluster(self, evidence: dict) -> dict:
        """生成 EventCluster 字典。

        输入：EvidenceCard 字典。
        输出：包含 event_key、主体、事件类型和初始分数的 dict。
        """
        hn_id = evidence["source_item_id"]
        heat_score = min(1.0, (evidence["points"] + evidence["num_comments"] * 2) / 100)
        return {
            "event_key": f"hn-{hn_id}",
            "title_hint": evidence["normalized_title"],
            "summary_hint": evidence["claim_summary"],
            "primary_subject": evidence["subjects"][0],
            "subjects": evidence["subjects"],
            "event_trigger": evidence["event_trigger"],
            "event_type": evidence["event_type"],
            "category": evidence["category"],
            "merge_key": evidence["merge_key_hint"],
            "heat_score": heat_score,
            "impact_score": 0.5,
            "audience_value_score": min(1.0, evidence["candidate_score"] + 0.2),
            "evidence_card_count": 1,
            "source_count": 1,
            "cluster_status": "new",
            "publish_decision": "hold",
            "brief_candidate": False,
            "evidence": evidence,
        }
