# sing-box 规则集

由 `scripts/loon_to_singbox.py` 将 `lq/*.list` 和 `lq/*.txt` 自动转换为分离的域名和 IP JSON source rule-set，使用规则集版本 2（sing-box 1.10.0+）。此目录根部的 JSON 均为生成文件，请修改 `lq/` 中的源规则。

| Loon 源文件 | 域名规则集 | IP 规则集 |
| --- | --- | --- |
| `lq/adlite.list` | `adlite_domain.json` | `adlite_ip.json` |
| `lq/direct.list` | `direct_domain.json` | `direct_ip.json` |
| `lq/proxy.list` | `proxy_domain.json` | `proxy_ip.json` |
| `lq/merged_rules.txt` | `merged_rules_domain.json` | `merged_rules_ip.json` |

以上文件都直接位于 `singbox/`。域名文件只包含 `domain`、`domain_suffix`、`domain_keyword`；IP 文件只包含 `ip_cidr`（包括 IPv4 和 IPv6）。每个源文件都生成两份文件，缺少某类规则时使用 `"rules": []` 表示不匹配任何目标，绝不生成可能匹配全部目标的空规则对象 `{}`。

旧的 `adlite.json`、`direct.json`、`proxy.json`、`merged_rules.json` 已移除，旧地址不再可用。请把旧订阅切换到新的 `_domain.json` / `_ip.json`；需要覆盖原有全部条件时引用两份规则集，并按主配置安排匹配顺序。

## 开关

两个开关默认开启，关闭时跳过该格式的测试、转换和发布，保留已发布文件。

- **手动运行**：Actions → Auto Convert → Run workflow，分别勾选 `enable_clash` 和 `enable_singbox`。手动选项优先于仓库变量。
- **定时、push、上游完成触发**：在仓库 Settings → Secrets and variables → Actions → Variables 中设置 `ENABLE_CLASH` / `ENABLE_SINGBOX`，值为小写 `true` 或 `false`。未设置时默认为 `true`。
- 两项都关闭时不转换、不提交；非法值会报错，避免误开启。公共发布器测试仍可运行。
- 命令行：`python3 scripts/auto_convert.py --clash false --singbox true`（会向 `origin/main` 推送）。

## 自动更新

`Auto Convert` 保留原有 Clash 转换，并生成、提交 sing-box 规则集和转换报告。支持手动运行、源文件/转换器变更触发、每天 UTC 21:00（北京时间次日 05:00）定时运行，以及 `Merge`、`Sync and Process ADLite` 成功完成后触发。后者也能处理由 `GITHUB_TOKEN` 提交规则时不会继续触发 push workflow 的情况。

转换和发布由三个脚本负责：

- `scripts/loon_to_clash.py`：一次遍历生成 `cat/*.yaml`，保留规则顺序和重复项，过滤清理后的空行、注释。解析生成的 YAML 并与原规则字符串逐项比较；遇到会改变 YAML 含义的字符时使用引号编码，避免 `null`、映射对象或规则截断。
- `scripts/loon_to_singbox.py`：分别生成 sing-box 域名/IP JSON 和兼容性报告，保持现有的规则映射、去重和排序行为。
- `scripts/auto_convert.py`：每次从最新 `main` 的临时工作副本分别运行两种格式的测试和转换，只有某种格式全部成功后才发布该格式的结果。另一种格式失败时保留其已发布文件，workflow 仍会报告失败，不会将部分结果当成全部成功。

发布前重新检查远端。远端有更新或推送被拒绝时，从最新提交重新转换，最多尝试 3 次；不再将旧转换结果直接 rebase 到新源文件上。没有输出变化时不创建提交。

**不自动删除旧文件。** 删除或重命名 `lq/` 源文件不会删除 `cat/`、`singbox/` 中已存在的文件；两个独立转换脚本也保留旧输出。需要清理时请手动处理。转换过程中使用的临时文件清理不影响仓库中已有规则。

本地生成：

```sh
python3 -m pip install PyYAML==6.0.3
python3 -m unittest discover -s tests -v
python3 scripts/loon_to_clash.py
python3 scripts/loon_to_singbox.py
```

`auto_convert.py` 会实际向 `origin/main` 推送，供 workflow 使用；本地只生成文件时使用上面两个转换脚本。

## 兼容性与限制

- `DOMAIN`、`DOMAIN-SUFFIX`、`DOMAIN-KEYWORD`、`IP-CIDR` 和 `IP-CIDR6` 分别映射到对应的域名和 IP 匹配字段；规则去重、排序，保留各条规则之间的 OR 关系。
- `USER-AGENT` 和 `URL-REGEX` 无对应的 sing-box headless rule 字段，不能等价转换。跳过的完整规则、源文件行号和统计保存在 [转换报告](reports/conversion-report.json)，workflow 同时输出警告。原始 Loon 文件不变。
- `no-resolve` 不属于 sing-box rule-set 字段，只转换其 IP 匹配条件并记录数量。DNS 解析时机由使用方的 sing-box 路由/DNS 配置控制，不能在这些规则集里逐条复刻 Loon 的 `no-resolve` 行为。
- 未知规则类型、格式错误、附带策略的规则、空规则集或同名输出冲突会使转换失败，避免悄悄发布不完整结果。
- 规则集只包含匹配条件，不包含代理节点、直连/代理/拒绝动作；请在主配置中指定动作。

## 引用示例

将下面片段合并进主配置的 `route`（sing-box 1.11+ 动作语法）。`proxy` 必须替换为已有代理出站的 tag：

```json
{
  "rule_set": [
    {
      "type": "remote",
      "tag": "mr-proxy",
      "format": "source",
      "url": "https://raw.githubusercontent.com/lucere30/MR/main/singbox/proxy_domain.json",
      "update_interval": "1d"
    }
  ],
  "rules": [
    { "rule_set": "mr-proxy", "action": "route", "outbound": "proxy" }
  ]
}
```

其他域名规则集使用同目录下的 `adlite_domain.json`、`direct_domain.json`、`merged_rules_domain.json`；IP 规则集使用对应的 `_ip.json`。例如广告规则可在主配置中使用 `action: reject`，直连规则指向已有直连出站。按需要安排规则顺序。

如需二进制文件，可自行编译（本仓库自动发布 JSON）：

```sh
sing-box rule-set compile --output proxy.srs singbox/proxy_domain.json
```

官方文档：[Source Format](https://sing-box.sagernet.org/configuration/rule-set/source-format/) · [Headless Rule](https://sing-box.sagernet.org/configuration/rule-set/headless-rule/)
