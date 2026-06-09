from __future__ import annotations


class QualityGateAgentStub:
    """质量门禁 stub。

    输入：详情内容 dict。
    输出：只检查字段齐全和来源存在的质量门禁结果。
    """

    def check(self, detail: dict) -> dict:
        """检查详情内容是否可发布。

        输入：DetailWriterAgentStub 输出的详情 dict。
        输出：包含 status、recommended_action、fail_reasons 的质检 dict。
        """
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
