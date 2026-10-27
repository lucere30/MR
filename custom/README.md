# 自定义订阅规则

| 用途 | 自定义源（在这里增删） | 自动合并结果（客户端订阅） |
| --- | --- | --- |
| Fake-IP 排除 | `custom/fakeip-filter.list` | `cat/fakeip-filter.yaml` |
| ESPN 分流 | `custom/espn.list` | `lq/espn.list` |
| Bitget 分流 | `custom/bitget.list` | `lq/bitget.list` → `cat/bitget.yaml` |

自定义源由你维护，不会被同步脚本改写。即使一条自定义规则目前被上游覆盖，
也应保留在这里；上游以后移除覆盖规则时，它会自动重新出现在合并结果中。
上游新增和删除都会反映到结果；不要直接修改生成文件，否则下次同步会覆盖。

- Fake-IP 每行一个域名模式，`+.example.com` 匹配根域名及所有层级子域名；
  精确域名和 `*.` 模式保持各自含义。结果使用 `behavior: domain`、`format: yaml`。
- ESPN 使用不带策略名的规则，例如 `DOMAIN-SUFFIX,example.com`。
  不要添加末尾的 `,ESPN`，在客户端订阅规则集时指定 ESPN 策略。
- Bitget 同样使用不带策略名的 `DOMAIN` / `DOMAIN-SUFFIX`；自定义补充写入
  `custom/bitget.list`，排除上游条目写入 `custom/bitget-exclude.list`。
  排除只作用于上游，自定义补充可明确恢复需要的域名；不会封禁流量或强制直连。
  `DOMAIN-SUFFIX` 排除项按域名标签边界覆盖根域名及其子域名，`DOMAIN` 排除项
  只删除同名精确规则，不会删除更广的上游后缀规则。
  生成的 `cat/bitget.yaml` 使用 `behavior: classical`、`format: yaml`。
- `Sync Custom Rules` 每天 UTC 20:20（新加坡次日 04:20）同步，GitHub 调度可能延迟。
  修改自定义源、同步脚本或 workflow 会立即触发；也可在 Actions 手动运行。
- Fake-IP 跟随 DustinWin `mihomo-ruleset` Release 的 `fakeip-filter.list`（MRS 配套文本）；
  ESPN 跟随 blackmatrix7 的 `Espn_No_Resolve.yaml`。上游地址集中在脚本 `SOURCES`。
- Bitget 跟随 uhovohu/clash 的 `Rules/bitget.yaml`，保留其交易所及钱包范围，
  过滤已识别的共享服务，详见 [审查记录](bitget-review.md)。精确域名转为 `DOMAIN`，
  `+.` 转为 `DOMAIN-SUFFIX`；遇到 `*.` 等无法无损转换的模式时停止本次发布。
- 只删除完全重复项和语义明确的域名覆盖项，精确域名不会被当成后缀处理。
- 任一上游下载或校验失败，本次三个结果均不发布，保留此前版本。无变化不提交。
  并发提交时重新读取最新自定义源并生成，最多重试 3 次，不强制推送。
- 同步成功会触发现有 Clash / sing-box 转换流程，仍遵循各自开关；
  sing-box 默认关闭保持不变。Fake-IP 在 `cat` 直接生成，不经过通用转换器。

本地验证（Python 3、Git、curl、PyYAML）：

```bash
python3 -m unittest discover -s tests -p 'test_sync_custom_rules.py' -v
python3 scripts/sync_custom_rules.py --output-dir /tmp/custom-rule-preview
```
