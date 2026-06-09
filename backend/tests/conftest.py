"""共享测试配置。

在任何 app 模块导入*之前*强制启用 mock-LLM 模式与一个隔离的 SQLite 数据目录
（使被缓存的 Settings 能拾取它们），并在每个会话清空一次该目录，
以便跨运行 / 元评估断言具有确定性。
"""
from __future__ import annotations

import os
import shutil

os.environ.setdefault("VOLC_MOCK", "1")
os.environ.setdefault("DATA_DIR", "./.test-data")

# 在收集测试时清空一次测试数据目录。
shutil.rmtree(os.environ["DATA_DIR"], ignore_errors=True)
