def test_pydantic_is_available():
    """验证 Pydantic 依赖可以在 worker 环境导入。

    输入：本地 worker 虚拟环境。
    输出：构造一个最小 BaseModel，并断言字段值保持正确。
    """
    from pydantic import BaseModel

    class SmokeModel(BaseModel):
        """Task 1 依赖导入烟测模型。

        输入：name 字符串。
        输出：Pydantic 校验后的对象实例。
        """

        name: str

    assert SmokeModel(name="ai-world-radar").name == "ai-world-radar"
