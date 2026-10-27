# 进程规则

只生成 Mihomo classical YAML，不发布到 Loon 或 sing-box。

| 可编辑输入 | 订阅输出 | 策略 |
|---|---|---|
| `custom/proxy-tools.list` | `cat/proxy-tools.yaml` | DIRECT，放在一般规则及 UDP 443 拒绝前 |
| `custom/download.list` | `cat/download.yaml` | download，可选择直连或代理 |

以 [Loyalsoldier applications](https://github.com/Loyalsoldier/clash-rules/blob/release/applications.txt) 为基础拆分，下载器补充参考 [blackmatrix7 Download](https://github.com/blackmatrix7/ios_rule_script/blob/master/rule/Clash/Download/Download.list)。仅采用明确的 PROCESS-NAME，不采用 Download 中的域名关键词，浏览器、curl、wget、通用 Java/Python 进程不纳入下载器。

这是人工审阅的名单快照：修改 custom 后由既有构建流程生成。不会自动将上游新增的未知进程归入 DIRECT，后续增补需审阅。两份名单应保持互斥。

proxy-tools 是此配置选择的防代理回环直连策略，并非每种部署中都必须直连；有意让代理工具串联上游时应先移除对应进程。需要操作系统能识别本机进程；网关不能据此识别其他设备上的下载器。find-process-mode 不应设置为 off。

download 接管的是下载器进程的全部连接，不只文件数据，也包含登录、更新和 tracker 请求。手动域名规则仍优先于 download，现有全局 UDP 443 拒绝也仍优先于下载器。代理工具直连规则则置顶。

分支试用的复写订阅指向 `feat/applications-download`；该分支不会自动运行 main 的定时发布。合并到 main 后，可将两个新 provider 的 URL 改为 main 再使用定时构建。
