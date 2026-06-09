from __future__ import annotations


class DetailWriterAgentStub:
    """详情写作 stub。

    输入：排序后的 cluster 和 evidence。
    输出：临时 PublishedEvent 详情内容，供 QualityGate 和 PublishService 验证链路。
    """

    def write(self, ranked_cluster: dict, evidence: dict) -> dict:
        """生成事件详情内容。

        输入：ranked_cluster 字典和 evidence 字典。
        输出：包含 title、summary、body、source_refs 的详情内容 dict。
        """
        event_key = ranked_cluster["event_key"]
        title = ranked_cluster["title_hint"]
        excerpt = evidence.get("page_excerpt") or evidence.get("story_text") or evidence["claim_summary"]
        source_refs = [url for url in [evidence.get("original_url")] if url]

        return {
            "published_event_id": f"pub-{event_key}",
            "event_key": event_key,
            "artifact_type": "event_detail",
            "title": title,
            "summary": evidence["claim_summary"],
            "body": (
                f"{title}\n\n"
                f"{excerpt}\n\n"
                "这是一段后端 P1 确定性 stub 生成的临时详情内容，用于验证 HN 事件生产管道。"
            ),
            "why_it_matters": evidence["audience_value_reason"],
            "follow_up_points": ["观察官方来源是否跟进", "观察 HN 讨论热度是否持续"],
            "source_refs": source_refs,
            "category": ranked_cluster["category"],
            "ranking_score": ranked_cluster["ranking_score"],
            "quality_status": "qc_pending",
        }
