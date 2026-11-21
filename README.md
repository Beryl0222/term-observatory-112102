# 跨学科新词的趋势与语料回查

编辑部往来摘要、术语范围说明与抽核账。材料中的人、机构及经营记录是合成的。

每份资料为 UTF-8 JSON 数组。id 在同一份资料内唯一，原始文字按收到的形式保留。

- `data/lexicon.json`。编辑词表。版本按生效月登记，sense 是概念内部的稳定义项。aliases 是可出现的术语写法，notes 是词义范围及编辑用的区分提示。parent 为全刊汇总口径。
- `data/abstracts.json`。摘要传输记录。work 为文献 ID，单文种 serial 较大表示该文种重发。retract=true 时 text 为空，仅撤回相应文种。month 是语料归属月。
- `data/desk.json`。栏目账。receipt 是供数方对学科和文种是否齐全的回执。slots 是各变化必需的月份与学科席位。旧 bulletin 只给限期保留的历史发行元数据。

使用 Python 3.11 标准库，无需安装软件包或连接外部服务。

以下命令分别读取一份原始资料、检查资料中的字段与关联。

```sh
python3 -m json.tool data/lexicon.json
python3 -m unittest discover -s tests -v
```
