# sing-box 规则集

由 `scripts/loon_to_singbox.py` 将 `lq/*.list` 和 `lq/*.txt` 自动转换为同名 JSON source rule-set，使用规则集版本 2（sing-box 1.10.0+）。此目录根部的 JSON 均为生成文件，请修改 `lq/` 中的源规则。

| Loon 源文件 | sing-box 文件 |
| --- | --- |
| `lq/adlite.list` | `singbox/adlite.json` |
| `lq/direct.list` | `singbox/direct.json` |
| `lq/proxy.list` | `singbox/proxy.json` |
| `lq/merged_rules.txt` | `singbox/merged_rules.json` |

## 自动更新

`Auto Convert` 保留原有 Clash 转换，并生成、提交 sing-box 规则集和转换报告。支持手动运行、源文件/转换器变更触发、每天 UTC 21:00（北京时间次日 05:00）定时运行，以及 `Merge`、`Sync and Process ADLite` 成功完成后触发。后者也能处理由 `GITHUB_TOKEN` 提交规则时不会继续触发 push workflow 的情况。

本地生成：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/loon_to_singbox.py
```

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
      "url": "https://raw.githubusercontent.com/lucere30/MR/main/singbox/proxy.json",
      "update_interval": "1d"
    }
  ],
  "rules": [
    { "rule_set": "mr-proxy", "action": "route", "outbound": "proxy" }
  ]
}
```

其他规则集使用同目录下的 `adlite.json`、`direct.json`、`merged_rules.json`。例如广告规则可在主配置中使用 `action: reject`，直连规则指向已有直连出站。按需要安排规则顺序。

如需二进制文件，可自行编译（本仓库自动发布 JSON）：

```sh
sing-box rule-set compile --output proxy.srs singbox/proxy.json
```

官方文档：[Source Format](https://sing-box.sagernet.org/configuration/rule-set/source-format/) · [Headless Rule](https://sing-box.sagernet.org/configuration/rule-set/headless-rule/)
