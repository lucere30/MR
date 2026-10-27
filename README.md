# rkit

Loon / Mihomo 规则订阅，自动同步、转换并发布。sing-box 暂停更新。

## 订阅

| 规则集 | Loon | Mihomo |
|---|---|---|
| Direct | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/manual/direct.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/direct.yaml) |
| Proxy | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/manual/proxy.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/proxy.yaml) |
| Merged | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/merged_rules.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/merged_rules.yaml) |
| ADLite | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/adlite.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/adlite.yaml) |
| ESPN | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/espn.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/espn.yaml) |
| Bitget | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/bitget.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/bitget.yaml) |

Mihomo Fake-IP：[fakeip-filter.yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/fakeip-filter.yaml)（`behavior: domain`）；其余 Mihomo 规则集使用 `behavior: classical`。

## 维护

- **手动规则**：`lq/manual/direct.list`、`lq/manual/proxy.list`
- **自定义追加 / 排除**：`custom/`
- **上游与平台开关**：`rkit.yaml`
- **自动更新**：每天 04:20（新加坡时间），也可在 Actions 手动触发

`lq/generated/`、`cat/`、`singbox/` 为生成目录，不要手动编辑。Loon / Mihomo 的 IP 规则使用 `no-resolve`；sing-box 不使用。

上游规则来源见 [rkit.yaml](rkit.yaml)。
