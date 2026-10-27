# rkit

自动聚合并转换规则，生成 Loon / Mihomo 等客户端订阅。

## 订阅

| 规则集 | Loon | Mihomo |
|---|---|---|
| Direct | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/manual/direct.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/direct.yaml) |
| Proxy | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/manual/proxy.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/proxy.yaml) |
| Merged | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/merged_rules.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/merged_rules.yaml) |
| ADLite | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/adlite.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/adlite.yaml) |
| ESPN | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/espn.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/espn.yaml) |
| Bitget | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/bitget.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/bitget.yaml) |

Mihomo Fake-IP：[fakeip-filter.yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/fakeip-filter.yaml)（`behavior: domain`；其余规则集为 `classical`）。

配置与上游：[rkit.yaml](rkit.yaml) · 手动规则：`lq/manual/` · 自定义规则：`custom/` · 自动构建：[Actions](../../actions)
