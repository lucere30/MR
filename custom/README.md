# 自定义追加与排除

完整的手写 Direct/Proxy 列表放在 `lq/manual/`；这里存对上游的追加与排除。

| 文件 | 用途 |
|---|---|
| `espn.list` | ESPN 追加，不带策略名 |
| `bitget.list` | Bitget 追加，不带策略名 |
| `bitget-exclude.list` | 排除上游共享服务，追加可明确恢复 |
| `fakeip-filter.list` | Fake-IP 域名模式追加，`+.` 包含根域名与子域名 |

生成器不会修改这些文件。上游删除某条覆盖规则后，被覆盖的自定义追加仍会重新生效。
先过滤上游，再合并追加；域名覆盖去重不会改写自定义源文件。

输出位置、来源、定时任务、客户端开关及新增规则集方法见 [项目 README](../README.md)。
Bitget 的原始来源审查见 [bitget-review.md](bitget-review.md)。
