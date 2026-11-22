"""conceptwatch —— 编辑部研究概念趋势与语料回查工具。

模块划分：
- models:      不可变标识与数据类
- linguistics: 句子/小句切分、长短术语匹配、线索词与用法判断
- registry:    词表版本、义项索引与拆分谱系
- detect:      单篇摘要扫描，产出带原文片段的用词记录
- corpus:      文献多文种版本、重发更正、撤回与语料格
- review:      编辑复核决定台账
- compare:     同口径月份比较（确定值 + 存疑区间）
- audit:       抽核席位编排与人审队列
- publish:     出刊快照与撤回感知的读者视图
"""

from .models import UsageType, SightingStatus, EditionStatus

__all__ = ["UsageType", "SightingStatus", "EditionStatus"]
