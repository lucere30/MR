# sing-box 规则集

由 `scripts/loon_to_singbox.py` 将 `lq/*.list` 和 `lq/*.txt` 自动转换为同名 JSON source rule-set，使用规则集版本 2（sing-box 1.10.0+）。此目录根部的 JSON 均为生成文件，请修改 `lq/` 中的源规则。

| Loon 源文件 | sing-box 文件 |
| --- | --- |
| `lq/adlite.list` | `singbox/adlite.json` |
| `lq/direct.list` | `singbox/direct.json` |
| `lq/proxy.list` | `singbox/proxy.json` |
| `lq/merged_rules.txt` | `singbox/merged_rules.json` |
| 已审核的 `USER-AGENT` 应用映射 | `singbox/merged_rules_windows_process.json`（可选 Windows 补充） |

## 自动更新

`Auto Convert` 保留原有 Clash 转换，并生成、提交 sing-box 规则集和转换报告。支持手动运行、源文件/转换器变更触发、每天 UTC 21:00（北京时间次日 05:00）定时运行，以及 `Merge`、`Sync and Process ADLite` 成功完成后触发。后者也能处理由 `GITHUB_TOKEN` 提交规则时不会继续触发 push workflow 的情况。

本地生成：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/loon_to_singbox.py
```

## 兼容性与限制

- `DOMAIN`、`DOMAIN-SUFFIX`、`DOMAIN-KEYWORD`、`IP-CIDR` 和 `IP-CIDR6` 分别映射到对应的域名和 IP 匹配字段；规则去重、排序，保留各条规则之间的 OR 关系。
- `USER-AGENT` 和 `URL-REGEX` 无对应的 sing-box headless rule 字段，不能等价转换。原规则仍计入 [转换报告](reports/conversion-report.json) 的 `skipped`，workflow 同时输出警告。已审核应用的可选 Windows 进程替代规则另列在 `windows_process_supplements`，不计作等价转换成功。原始 Loon 文件不变。
- `no-resolve` 不属于 sing-box rule-set 字段，只转换其 IP 匹配条件并记录数量。DNS 解析时机由使用方的 sing-box 路由/DNS 配置控制，不能在这些规则集里逐条复刻 Loon 的 `no-resolve` 行为。
- 未知规则类型、格式错误、附带策略的规则、空规则集或同名输出冲突会使转换失败，避免悄悄发布不完整结果。
- 规则集只包含匹配条件，不包含代理节点、直连/代理/拒绝动作；请在主配置中指定动作。

## Windows 进程补充规则

转换器读取 [Windows 映射表](../scripts/windows_process_map.json)，按源文件中**完整 UA 模式字符串精确查表**，不会根据名称猜测 `.exe`，也不会使用通配符去套用未知 UA 规则。只有源文件实际出现已审核 UA 时，才生成同名的 `<源文件名>_windows_process.json`；不再有对应 UA 时自动删除过期补充文件。修改映射表也会触发 workflow。

当前已收录以下 3 个桌面应用，覆盖 `merged_rules.txt` 中的 4 条 UA 规则（Spotify 有两条），去重后为 3 个进程名：

| 源 UA 模式 | Windows 进程名 | 核实依据 |
| --- | --- | --- |
| `*Spotify*`、`Spotify*` | `Spotify.exe` | [Spotify 员工排查说明](https://community.spotify.com/forum/en/discussion/comment/7481665) |
| `OneDrive*` | `OneDrive.exe` | [Microsoft 部署文档](https://learn.microsoft.com/en-us/sharepoint/deploy-on-windows) |
| `hearthstone*` | `Hearthstone.exe` | [Blizzard 论坛用户提供的 Windows 崩溃日志](https://us.forums.blizzard.com/en/hearthstone/t/pc-game-crashes-multiple-times-unity-error/141864) |

这些证据用于核实可执行文件名；Hearthstone 的来源是用户诊断日志，并非厂商保证。核实日期和来源也保存在映射表中。

**这是按应用匹配的可选补充，不是 UA 的等价转换。** 引用后会匹配这些本机进程的连接，可能比原 UA 规则范围更广；不匹配网页版本，也不代表同名移动端应用。未确认的 UA（包括 YouTube）和 URL-REGEX 继续列入报告，不映射到 Chrome、Edge 等通用浏览器进程。

只在运行 sing-box 的 Windows 本机、能够获取连接所属进程的场景中使用。iOS 不支持这种进程匹配；放在另一台路由器上也无法获知 Windows 客户端的进程名。本仓库已做 JSON/规则集编译校验，但未在你的 Windows 设备上验证实际进程识别，使用时可结合任务管理器“详细信息”和客户端连接日志核对。此补充用于 `route.rules`，不用于 DNS 规则。

将下面条目添加到 `route.rule_set`：

```json
{
  "type": "remote",
  "tag": "mr-windows-process",
  "format": "source",
  "url": "https://raw.githubusercontent.com/lucere30/MR/main/singbox/merged_rules_windows_process.json",
  "update_interval": "1d"
}
```

再将以下条目添加到 `route.rules` 的合适位置（`proxy` 替换为已有代理出站 tag，使用 sing-box 1.11+ 动作语法）：

```json
{ "rule_set": "mr-windows-process", "action": "route", "outbound": "proxy" }
```

原来的 `merged_rules.json` 等域名/IP 规则集不会自动包含这些进程规则；需单独引用以上文件。

## 域名/IP 规则引用示例

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
