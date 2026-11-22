# 跨学科新词的趋势与语料回查

编辑部回答的问题是：**某个研究概念是否真的写进了越来越多的论文**，而不是某个新词
在摘要里出现多少遍。`conceptwatch/` 是配套的 Python 标准库工具，把用词识别、义项
归属、月份比较、抽核席位与撤回留档串成一条可复核的流水线。材料中的人、机构及经营
记录是合成的。

## 资料

每份资料为 UTF-8 JSON 数组。id 在同一份资料内唯一，原始文字按收到的形式保留。

- `data/lexicon.json`：编辑词表。版本按生效月登记，sense 是概念内部的稳定义项；
  aliases 是术语写法，notes 是词义范围与区分提示；parent 为全刊汇总口径。
- `data/abstracts.json`：摘要传输记录。work 为文献 ID，单文种 serial 较大表示该
  文种重发；retract=true 时 text 为空，仅撤回相应文种；month 是语料归属月。
- `data/desk.json`：栏目账。receipt 是供数方对学科×文种是否齐全的回执；slots 是
  各变化必需的月份与学科席位；review 是编辑复核；旧 bulletin 只保留历史发行元数据。

## 运行

Python 3.11 标准库，无需安装软件包或外部服务。

```sh
# 人类可读的工作稿（趋势区间、席位、人审队列、旧刊回查）
python3 -m conceptwatch --data data

# 逐条用词记录：原文片段、用法分类、义项或存疑原因
python3 -m conceptwatch --data data --sightings

# 出刊工作稿的 JSON 快照
python3 -m conceptwatch --data data --json

# 测试
python3 -m unittest discover -s tests -v
```

在隔离模式（`python3 -I`）下运行时，`-I` 不把当前目录加入 `sys.path`，可显式注入：

```sh
python3 -I -c "import sys; sys.path.insert(0, '.'); from conceptwatch.pipeline import main; main(['--data','data'])"
```

## 规则与实现对应

| 编辑部规则 | 实现位置 |
| --- | --- |
| 按登记概念、义项、语言习惯识别；记录原文片段、实际指向与存疑原因 | `detect.py`、`linguistics.py` |
| 同一简称跨学科可能指两件事；连着写的领域词有长短边界 | `registry.resolve_alias`、`linguistics.iter_matches`（长写法优先、英文词边界） |
| 否定用法、仅转述他人的引用与本文自身研究分开，只有自身研究计证据 | `linguistics.classify_usage`，`SightingStatus` |
| 重发沿用文献 ID；多文种算同一篇；更正不抹掉另一文种的有效证据 | `corpus.Corpus`（CURRENT / SUPERSEDED / RETRACTED） |
| 撤回只撤相应文种；撤回原文不再展示，旧刊仍能解释当时如何计入 | `status_of`、`visible_text`、`publish.explain_historical` |
| 旧概念拆成两个义项后旧口径仍可打开；两月比较统一用现行义项范围 | `registry.lineage`、`compare.compare_months` |
| 一篇可含两个义项；合计按文献去重 | `compare._month_stats`（集合并集） |
| 分母＝两月都交齐且覆盖的学科×文种中的有效文献；交集为空即不可比 | `shared_complete_cells`、`valid_works`、`ComparisonResult.comparable` |
| 存疑不给零、不跨义项重复计入同一篇，给出确定值与变化区间 | 每个义项与概念的 low/high 文献集合、`SenseTrend` |
| 每个拟发表变化都有可点回原文的抽核席位；两个月与关键学科都要见证据 | `audit.build_audit_plan`、`SeatAssignment.sighting_id` |
| 有效候选不足要明确缺哪一格；同一篇不能充当两个变化的独立证据 | 全局占用集合 `blocked`、`missing_cells` |
| 语义不明的文献另送人审，不能占确定席位 | `AuditPlan.review_queue` |
| 编辑复核后趋势与席位重新协调；已核实且证据仍有效的决定继续可查，席位不冒领旧决定 | `review.ReviewLedger`、`audit.recoordinate`，sighting 确定性 ID 挂接 |

## 当前合成数据的工作稿结论（2026-08 → 2026-09）

共同覆盖为 `计算/zh` 与 `能源/zh`；`计算/en` 仅八月交齐、`光学/zh` 仅九月交齐，
均不进比较。分母为 5 → 4 篇有效文献。

- **C1-gpu（算力/显存）**：确定 1→2 篇，存疑区间 3→2；变化 **+1 ~ −1 篇**。
- **C1-grid（储能/电力）**：确定 0→3 篇，存疑区间 2→3；变化 **+3 ~ +1 篇**。
- 概念合计按文献去重：1~3 → 4 篇；W04 同篇含两个义项，合计只计一次。
- 抽核：gpu 两月席位由 W09、W04 充当；grid 九月席位由 W10 充当，**八月能源席
  空缺**（W11/W12 存疑送人审，W03 已撤回）。
- W01 中文更正版 A9 取代 A1，但英文 A2 仍有效；W03 的 A4 被 A10 撤回，旧刊 D5
  保留当时计数并标注证据现已不可用。
