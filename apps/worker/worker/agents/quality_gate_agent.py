from __future__ import annotations


class QualityGateAgentStub:
    def check(self, detail: dict) -> dict:
        required_fields = ["title", "summary", "body", "source_refs"]
        missing = [field for field in required_fields if not detail.get(field)]
        return {
            "status": "passed" if not missing else "failed",
            "recommended_action": "publish" if not missing else "manual_review",
            "check_results": {
                "required_fields_present": not missing,
                "source_refs_present": bool(detail.get("source_refs")),
            },
            "fail_reasons": missing,
            "checked_by": "code",
            "gate_version": "stub-v1",
        }
