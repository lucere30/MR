# 规则同步

`Merge` 和 `Sync and Process ADLite` 共用 `sync_rules.py`，分别更新
`lq/merged_rules.txt` 和 `lq/adlite.list`。原有上游地址保存在脚本的 `SOURCES` 中。

两个 workflow 保留每天 UTC 20:00（次日 SGT 04:00）和手动触发；修改各自的
workflow、共用脚本或测试也会触发验证及同步。成功后由 `Auto Convert Clash`
和 `Auto Convert Singbox` 各自的 `workflow_run` 触发后续转换（受各自开关控制）。

## 独立格式转换

- `Auto Convert Clash` 只测试、转换及发布 `cat/`；`Auto Convert Singbox`
  只测试、转换及发布 `singbox/`，仍按 `_domain.json`、`_ip.json` 区分规则。
- 两者分别保留每日 UTC 21:00（次日 SGT 05:00）、`lq/` 源文件 push、
  上游同步成功和手动触发。修改某种格式的转换器、测试或 workflow 只触发该格式；
  修改共用发布脚本或其测试则触发两者。发布只允许在 `main` 上运行。
- 自动运行继续读取仓库 Actions 变量 `ENABLE_CLASH`、`ENABLE_SINGBOX`，
  值为字符串 `true` / `false`；未设置时 Clash 开启、sing-box 关闭。
  手动运行使用各自的 `enabled` 复选框覆盖变量，仅影响这一次；
  默认 Clash 勾选、sing-box 不勾选。关闭时整个转换 job 跳过。
- 两个 workflow 使用不同的并发组，运行状态、重跑和停用互不依赖；
  共用 `auto_convert.py` 的发布逻辑，固定只启用自己的格式。
  共用发布测试使用临时 Git 仓库和模拟转换器，不执行另一格式的真实转换测试。
- 同时推送到 `main` 时，保留现有最多 3 次重新获取最新提交、重新生成和推送的机制，
  不强制推送、不删除已有规则文件。两个格式分别提交，不保证同一时刻来自同一源提交。
- 保留 `workflow_run` 是因为上游使用 `GITHUB_TOKEN` 提交时不会再次触发 push workflow。
  转换摘要写入各自 Actions 运行记录，既有 sing-box 转换报告仍保留原位置。

## 处理约定

- Merge 保留非 IP 规则去重、排序，以及 IPv4 / IPv6 分别合并网段的逻辑。
- 两个同步任务都执行域名覆盖去重：同一输出中，`DOMAIN-SUFFIX,example.com`
  可以去掉子域名后缀，以及 `example.com` 本身和子域名的 `DOMAIN` 规则。
  按域名标签边界检查父域名集合，不会把 `notexample.com` 当作子域名；不跨文件去重。
  仅处理无额外选项的小写 ASCII 普通域名（至少两段）。大小写混合、前后带点、
  通配符、Unicode 等特殊写法保留，关键词、正则和 UA 不参与覆盖判断。
  完全相同的行仍由 Merge 原有逻辑去重，ADLite 不额外删除这类重复行。
  Actions 摘要分别统计被覆盖的后缀规则和精确域名规则数量。
- ADLite 保留注释、空行及剩余规则的顺序。仅 IP 规则补充一个 `no-resolve`，
  同时处理 IPv4 和 IPv6，保留上游地址写法。
- 当前支持 `DOMAIN`、`DOMAIN-SUFFIX`、`DOMAIN-KEYWORD`、`USER-AGENT`、
  `URL-REGEX`、`IP-CIDR` 和 `IP-CIDR6`。UA 和 URL 表达式保持原样。
- 每个来源单独校验。HTTP 错误、空文件、无效 IP、类型与地址版本不符、未知规则类型
  或不支持的 IP 选项会中止该次发布，摘要提供来源和行号。不会跳过坏来源生成残缺文件。
- 下载最多重试 3 次，连接超时 10 秒、单次请求 20 秒、重试窗口 60 秒，
  每个来源另有 90 秒进程上限；任务总时限 15 分钟。
- 发布仅替换当前 workflow 的目标文件，不执行旧文件清理。使用基于最新 `main`
  的临时 Git 索引，不改动检出目录或其他文件。并发更新时重新下载和验证，
  最多尝试发布 3 次，不强制推送。若处理代码已改变，旧任务停止，需运行最新版本。
- 内容没有变化时不创建提交。统计和错误只写入 Actions 运行摘要
  `GITHUB_STEP_SUMMARY`，不在仓库生成报告文件。

## 本地验证

需要 Python 3、Git 和 curl；同步脚本本身只使用 Python 标准库。

```bash
python3 -m unittest discover -s tests -p 'test_sync_rules.py' -v
python3 scripts/sync_rules.py merge --output /tmp/merged_rules.txt
python3 scripts/sync_rules.py adlite --output /tmp/adlite.list
```

`--output` 只在全部来源校验通过后写入指定文件，不执行 Git 发布。
`--publish --attempts 3` 用于 workflow 内发布，需要 `contents: write` 权限。
