# Worker 临时调试区

这个目录用于放本地临时调试脚本，例如测试某个函数、某个 Agent 节点或某段 prompt。

推荐用法：

```powershell
cd "D:\AI World Radar"
.\apps\worker\.venv\Scripts\python apps\worker\scratch\你的脚本.py
```

约定：

- `*.py`、`*.json`、`*.txt` 会被 Git 忽略，适合放临时实验。
- 不要在这里写真实 API Key。
- 需要复用的测试应转成 `apps/worker/tests/` 下的 pytest。
