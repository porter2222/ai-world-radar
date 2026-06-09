from __future__ import annotations

from worker.collectors.hn_algolia import HNStory
from worker.collectors.page_cache import PageFetchResult


class EvidenceAgentStub:
    prompt_version = "stub-v1"

    def build(self, story: HNStory, page: PageFetchResult) -> dict:
        title = page.page_title or story.title
        candidate_score = min(1.0, story.hn_heat_score / 100)
        subjects = _extract_subjects(title)

        return {
            "source_id": "hacker_news",
            "source_item_id": story.hn_id,
            "original_title": story.title,
            "original_url": story.original_url,
            "author": story.author,
            "published_at": story.created_at.isoformat() if story.created_at else None,
            "points": story.points,
            "num_comments": story.num_comments,
            "story_text": story.story_text,
            "page_title": page.page_title,
            "page_excerpt": page.page_excerpt,
            "page_text_hash": page.page_text_hash,
            "page_cache_path": page.page_cache_path,
            "fetch_status": page.fetch_status,
            "claim_summary": f"{title} 在 Hacker News 获得讨论。",
            "normalized_title": title,
            "subjects": subjects,
            "event_trigger": "HN community discussion",
            "event_type": "community_discussion",
            "category": "developer_tools",
            "heat_clues": [f"HN points={story.points}", f"HN comments={story.num_comments}"],
            "impact_clues": ["stub uses title and cached page metadata only"],
            "audience_value_reason": "该条目可帮助中文 AI 学习型用户了解海外开发者社区关注点。",
            "suggested_route": "high_heat_candidate" if candidate_score >= 0.6 else "normal_candidate",
            "candidate_score": candidate_score,
            "candidate_reason": "HN heat score from points plus double comments.",
            "merge_key_hint": f"{story.hn_id}:{title.lower()}",
            "dedupe_key": story.hn_id,
            "raw_heat_metrics": {"points": story.points, "num_comments": story.num_comments},
            "processing_status": "processed",
            "model_name": "deterministic-stub",
            "prompt_version": self.prompt_version,
        }


def _extract_subjects(title: str) -> list[str]:
    known_subjects = ["OpenAI", "ChatGPT", "Anthropic", "Claude", "Gemini", "NVIDIA", "Hugging Face", "MCP"]
    subjects = [subject for subject in known_subjects if subject.lower() in title.lower()]
    return subjects or ["AI"]
