from __future__ import annotations


class DetailWriterAgentStub:
    def write(self, ranked_cluster: dict, evidence: dict) -> dict:
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
