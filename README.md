# rkit

配置驱动的 Loon、Mihomo 与 sing-box 规则订阅构建工具。

上游订阅与本地规则 → 统一解析、排除、合并、去重 → 客户端适配 → 校验 → 单次发布。
三个客户端均为正式输出目标，目前全部启用；开关统一放在 `rkit.yaml` 的 `targets`。

## 我应该编辑哪里？

| 需求 | 编辑位置 |
|---|---|
| 自己维护完整的直连、代理列表 | `lq/manual/direct.list`、`lq/manual/proxy.list` |
| 为 ESPN、Bitget、Fake-IP 上游追加规则 | `custom/<规则集>.list` |
| 从上游结果中排除条目 | `custom/<规则集>-exclude.list`，在配置中登记 |
| 增加上游、规则集、调整目标平台 | `rkit.yaml` |

`lq/manual/` 可以直接供 Loon 订阅，也作为其他客户端的输入，不由生成器改写。
提交后不必等待转换即可拉取手写列表，客户端缓存和刷新周期仍然适用。
`lq/generated/`、`cat/`、`singbox/` 是生成目录，请不要直接修改。

手写列表使用不带策略名的规则；目标 IP 规则必须带且只带一个 `no-resolve`：

```text
DOMAIN-SUFFIX,example.com
IP-CIDR,192.0.2.0/24,no-resolve
IP-CIDR6,2001:db8::/32,no-resolve
```

CI 会检查手写文件，生成器会拒绝不符合约定的规则集。直接订阅的文件以提交内容为准，CI 不会回滚手动提交。

## 订阅地址

以下均为可直接订阅的 Raw 链接。策略名在客户端配置中指定。

| 规则集 | Loon | Mihomo | sing-box 域名 | sing-box IP |
|---|---|---|---|---|
| Direct | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/manual/direct.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/direct.yaml) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/direct_domain.json) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/direct_ip.json) |
| Proxy | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/manual/proxy.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/proxy.yaml) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/proxy_domain.json) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/proxy_ip.json) |
| Merged | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/merged_rules.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/merged_rules.yaml) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/merged_rules_domain.json) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/merged_rules_ip.json) |
| ADLite | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/adlite.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/adlite.yaml) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/adlite_domain.json) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/adlite_ip.json) |
| ESPN | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/espn.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/espn.yaml) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/espn_domain.json) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/espn_ip.json) |
| Bitget | [list](https://raw.githubusercontent.com/lucere30/rkit/main/lq/generated/bitget.list) | [yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/bitget.yaml) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/bitget_domain.json) | [json](https://raw.githubusercontent.com/lucere30/rkit/main/singbox/bitget_ip.json) |

Fake-IP 单独使用 [fakeip-filter.yaml](https://raw.githubusercontent.com/lucere30/rkit/main/cat/fakeip-filter.yaml)，
属于 Mihomo `behavior: domain` / `format: yaml` 的域名排除列表；其余 Mihomo 文件为 `behavior: classical` / `format: yaml`。
sing-box 文件为 `format: source` 的规则集，域名与 IP 独立；没有对应条目时输出 `rules: []`，不会输出匹配全部流量的 `{}`。
DNS resolve 行为及域名/IP 规则集的引用顺序由客户端配置决定。

## 配置

```yaml
version: 1
targets:
  loon: true
  mihomo: true
  singbox: true
rulesets:
  example:
    sources:
      - url: https://example.org/rules.list
        format: classical
    additions: custom/example.list
    exclusions: custom/example-exclude.list
    targets: [loon, mihomo, singbox]
```

- 输入格式：`classical`、`clash-classical`、`domain-list`、`clash-domain`。
- 来源二选一：HTTPS `url`，或位于 `custom/`、`lq/manual/` 的本地 `path`。
- `additions`、`exclusions` 可省略；声明的文件必须存在，允许只有注释。
- `collapse_ip: true` 将 IPv4/IPv6 分开合并等价网段；目前仅 Merged 启用。
- `layout: split` 可将 Loon/Mihomo 输出拆为 `_domain`、`_ip`、`_other`，只生成非空类别；sing-box 固定输出 domain/IP 两份。
- `purpose: fakeip` 目前只支持 Mihomo。其源和增删文件使用域名模式，普通分流规则使用 classical 增删文件。
- `omit: {mihomo: [USER-AGENT, URL-REGEX], singbox: [USER-AGENT, URL-REGEX]}` 明确允许目标不支持类型的省略；默认遇到无法转换的规则即失败。
- 手写直订来源不能同时配置上游合并、增删文件或 split，以免直订与转换结果指向不同规则集合。

先对上游应用排除，再加入自定义追加，最后去重。因此追加可以明确恢复被排除的条目。
排除不是流量阻断：精确域名只删除同名精确规则，后缀按标签边界覆盖；不会从宽泛后缀中“挖出”一个子域名。
自定义文件始终保留原文，即使当前某条追加被上游后缀覆盖，上游删除后它也会恢复。

## 正确性与兼容性

- 精确域名、后缀与通配符保持独立含义；只优化小写普通域名的确定覆盖关系。不跨规则集去重。
- Loon/Mihomo 支持的目标 IP 规则统一生成一个 `no-resolve`；来源 IP 不加，sing-box 不输出该选项。
- 当前通用模型支持 DOMAIN、DOMAIN-SUFFIX、DOMAIN-KEYWORD、IP-CIDR、IP-CIDR6、SRC-IP-CIDR、IP-ASN、GEOIP、USER-AGENT、URL-REGEX，以及 Fake-IP 域名模式。实际输出受目标能力表限制。
- Loon 保留 USER-AGENT、URL-REGEX；Mihomo 与 sing-box 无等价类型。Merged/ADLite 的配置明确允许省略并记录每条来源；不能把这两种产物视为包含全部 Loon 匹配能力。
- CIDR 输出统一为网络地址；注释仅保留在手写文件和原始输入中，生成订阅不复制上游动态时间戳。
- 自动发布用 Mihomo 1.19.33 做原生配置检查，用 sing-box 1.14.4 编译每份 JSON；下载的官方二进制固定 SHA-256。Loon 使用语法、语义和回归测试，未进行 iOS 客户端实机测试。

## 自动化与失败处理

只有 `CI` 和 `Publish subscriptions` 两个工作流。每天新加坡时间 04:20 自动同步，也支持手动触发；修改输入或构建代码会触发发布。
旧的 `ENABLE_CLASH` / `ENABLE_SINGBOX` Actions 变量已不再使用，以 `rkit.yaml` 为准。

下载与规则集构建各最多 4 个线程。每个 URL 每轮只下载一次，各目标共享同一份内容快照。
一个规则集的来源、解析或目标转换失败时，该规则集所有目标保留旧版；其他成功规则集仍可发布，工作流最终标为失败以提示检查。
全局配置错误、原生客户端校验失败或发布竞态则阻止整批提交。

一个发布任务只提交生成文件。输入指纹与文件摘要必须一致；远端 main 已变化时旧任务退出，需在最新 main 上重跑。绝不强推。
内容不变不提交。禁用目标或从单个规则集移除目标会保留原有输出，避免误删仍在使用的订阅。

`manifest.json` 记录每个规则集/目标的输入 SHA-256、代码与配置摘要、产物 SHA-256 和省略计数。
只清理清单中受管理且本次成功构建不再生成的文件；删除整个规则集定义会退役其受管理文件（涉及全局禁用目标或本轮有构建失败时保留）。未知文件始终保留。
受管理文件被手工修改时拒绝覆盖/清理，需要先把修改迁移到输入。
完整省略明细与失败信息保留在 Actions 的 `rkit-build-report` artifact 中，保留 14 天。

## 本地开发

Python 3.11+、Git、curl；安装依赖后可使用 CLI：

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
rkit check
rkit build --output .rkit-stage --cache-dir .rkit-cache
python tools/validate_clients.py .rkit-stage
```

`build` 只写暂存目录，不覆盖订阅或提交 Git。每次使用新的空暂存目录。
网络获取成功的输入可写入 `.rkit-cache`；使用 `--offline --cache-dir .rkit-cache` 可重放同一快照。
在线下载失败不会偷偷使用旧缓存。原生客户端检查脚本适用于 Linux amd64。
只有 `rkit publish --stage .rkit-stage` 执行 Git 发布，需要在已提交且与远端一致的 main 上运行。

模块：`config` → `fetch` / `parsers` → `model` / `transform` → `renderers` → `build` / `publish`。
新增订阅修改配置；新增输入格式注册解析器；新增客户端注册输出适配器并补能力、语义与原生校验测试。

## 从旧目录迁移

| 旧路径 | 新路径 |
|---|---|
| `lq/direct.list`、`lq/proxy.list` | `lq/manual/direct.list`、`lq/manual/proxy.list` |
| `lq/espn.list`、`lq/bitget.list`、`lq/adlite.list` | `lq/generated/` 下同名文件 |
| `lq/merged_rules.txt` | `lq/generated/merged_rules.list` |
| `cat/*` | 路径保留 |
| `singbox/*_domain.json`、`singbox/*_ip.json` | 路径保留，新增 ESPN 与 Bitget |
| `singbox/reports/conversion-report.json` | Actions 构建报告 + `manifest.json` |

迁移保留 direct/proxy 手写原文及所有 custom 追加/排除文件。
上游来源与作者地址完整保留在 `rkit.yaml`；上游内容的许可与使用限制仍以对应项目为准。
