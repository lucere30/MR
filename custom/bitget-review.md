# Bitget 上游规则审查

上游：[uhovohu/clash 的 Rules/bitget.yaml](https://github.com/uhovohu/clash/blob/main/Rules/bitget.yaml)。
2026-10-27 检查时，上游 blob 为 `3d57de3d1d43e074871d3aa182ed012ad76b77d8`，
共 60 条，完全去重后 57 条；排除下列 13 个共享服务域名后生成 44 条。
这些数字是本次快照，后续随上游和自定义源变化。

本规则沿用上游的交易所及钱包范围。没有把所有保留域名逐一认定为 Bitget 自有域名，
也没有通过客户端抓包证明其完整性。这里的筛选依据是减少共享服务被整域归入 Bitget
策略的范围，而不是判定这些服务不被 Bitget 使用。

| 排除域名 | 原因与核对依据 |
| --- | --- |
| `amazontrust.com` | [AWS 公共证书服务](https://www.amazontrust.com/) |
| `rapidssl.com` | [公共 SSL 证书服务](https://www.rapidssl.com/) |
| `ss2.us` | 多款无关软件也依赖此域名，例如 [Autodesk 许可联网清单](https://help.autodesk.com/view/fusion360/ENU/?caas=caas%2Fsfdcarticles%2Fsfdcarticles%2FWhat-URLs-protocols-should-be-accessible-for-Desktop-Subscription-to-work-html.html)；属于共享证书基础设施 |
| `engagelab.com`、`engagelab.cc` | [通用消息服务](https://www.engagelab.com/)及[官方 API 域名说明](https://www.engagelab.com/docs/email/rest-api/marketing/members) |
| `geetest.com` | [通用验证码和机器人检测](https://www.geetest.com/en/) |
| `airbrake.io` | [通用错误和性能监控](https://www.airbrake.io/) |
| `alchemy.com` | [共享区块链基础设施](https://www.alchemy.com/) |
| `arbitrum.io` | [公共区块链平台](https://arbitrum.io/) |
| `web3modal.org` | [Reown 钱包连接服务域名](https://docs.reown.com/advanced/security/content-security-policy) |
| `fiat24.com` | [面向多个项目的钱包支付基础设施](https://docs.fiat24.com/developer) |
| `marqeta.com` | [面向多家企业的发卡和支付平台](https://www.marqeta.com/) |
| `paydify.com` | [跨钱包及交易所的支付服务](https://www.paydify.com/) |

实际排除项在 `bitget-exclude.list` 中，后续同步不会覆盖它。未添加上游配套 IP 列表。
被排除的服务仍按客户端其他规则处理；登录验证码、钱包连接或支付功能如需固定出口，
可依据连接日志把具体主机名补入 `bitget.list`。显式自定义补充优先于上游排除。

新增上游域名自动进入下一次合并，并继续应用排除文件；不会自动声称新增域名已经人工审查。
