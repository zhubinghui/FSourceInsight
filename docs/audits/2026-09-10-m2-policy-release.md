# M2-B2b.1 生产发布与远程MySQL验收

## 结果

用户授权提交、部署，并在部署后完成远程MySQL测试。按[本轮计划](../superpowers/plans/2026-09-10-m2-policy-release.md)完成：

- **应用：`14dc6f1a4ae1b32c0d8b66be59c438d910c6e2d2`；schema：`c9e41a7b620f`。** 从旧应用22c098c/b6、checkout e98af16升级。
- **2026-09-10 06:15:19Z→06:15:25Z**四应用切换至health恢复，约6秒。无回滚触发。
- B2b.1策略/质量版本、撤权、preview/replay失效及历史已上线，**不是独立验证/规则审批或日常schema路由完成**；未创建生产grant、候选或合成原文，旧日常入口未切换。
- 本地639 passed / 15专用MySQL skip / 4367 warnings，182.25秒；[准确提交CI34443459274](https://github.com/zhubinghui/FSourceInsight/actions/runs/34443459274)的test/mysql-integration均成功。
- 部署前、**部署后**分别用真实web/worker镜像跑隔离MySQL8.0.46，四轮各15/15通过。暂存区以明确27文件allowlist提交，无强推、未知文件或备份入Git。

## 新发现与容量缓解

预检不是照搬旧健康结论：fast当时running、restart0，却OOMKilled=true。内核2026-09-09 23:00:19的MEMCG记录与该容器ID一致，Celery子进程被杀；memory.events为max104/oom5/oom_kill1。父进程存活，**重启次数不能证明无OOM**。

机器可用3776MiB、磁盘21GiB；fast473.5/512MiB、beat245/256MiB。新增既有Compose CLI契约，观察旧上限red后，把fast提高到**1GiB**、beat提高到**384MiB**，其余服务上限/并发不变。增加640MiB仍为有界部署预算；孤立MySQL768MiB与测试runner512MiB串行运行。

这是实测容量不足后的**缓解**，不是内存增长根因或负载回归/长期容量保证。没有重放真实采集诱发OOM、没有扩大新闻/模型/邮件授权。切换后约318/512MiB web、575/1024MiB worker、366/1024MiB fast、245/384MiB beat；06:20Z复核四应用OOM false/restart0，fast新cgroup各事件计数0。仍需后续单任务峰值、长期内存及旧直连源迁移评估。

## 备份、候选与测试

备份目录：`/home/ubuntu/fsourceinsight-backups/mp-20260910060307`。

- single-transaction/quick/routines/events/triggers：**19,044,026 bytes、mode600**；gzip及SHA256复核通过。
- SHA256：`ec4870745626b909cb2e2cb911c310dc2832b3c282e83711ddb68cd183eebaf0`。
- 旧ref、四个准确image IDs及`rollback-mp-20260910060307` tags/Compose overlay保留。未读取/下载备份正文，未做整库恢复演练。
- ff-only至14dc6f1，串行构建四镜像，构建前后全部生产容器ID/启动时间/restart逐项相同。只挂测试副本，不覆盖真正候选app源码；测试无生产凭据/host端口。

| 阶段 | 真实镜像 | 独立MySQL结果 |
|---|---|---|
| 切换前 | web | 15/15，29.948秒 |
| 切换前 | worker | 15/15，30.100秒 |
| **部署后复跑** | **已部署web image** | **15/15，29.793秒** |
| **部署后复跑** | **已部署worker image** | **15/15，28.861秒** |

新增策略用例真实Admin登录/CSRF、Unicode规范主机JSON读回、旧表单409、实际preview/证据/离线回放、撤权409/Article0；前14项迁移/事务/既有并发回归亦通过。它们不替代新的policy发布并发、完整broker/长期FD/RSS/压力/崩溃恢复。

四镜像各45模板、HTTP质量标记、CSRF/Admin、真实回放/parser与基础billiard prefork通过。另用临时Docker证据卷/SQLite状态卷跑真实HTTP：保存policy→捕获→另一容器flock忙503→重建容器后回放200→撤权后409；无fetch补网、无Article/active、0700/0600、UID1000读取被拒。生产原证据卷为空且从未植入测试数据。

候选实际依赖：Python3.12.14、Flask3.1.3、SQLAlchemy2.0.52、Alembic1.19.2、PyMySQL1.2.0、LiteLLM1.100.0、requests2.34.2、urllib3 2.7.0。

## 迁移与上线

停beat，两worker active/reserved/scheduled全0，warm-stop退出0；`lock_wait_timeout=10`只执行b6→c9扩展迁移。model diff0，原三张M2表hash保持、policy表为空且不回填许可。旧计数前后均：Article10207、source38、CrawlLog15381、profile/candidate/preview各0。

4项LLM配置指纹不变：`ff4b48c9f237d6974d8e5605bd9233d6f29215ab21ea157d5856fff3697faef1`。未seed或替换管理员设置。

| 服务 | 运行image |
|---|---|
| web | `sha256:03a585fa8e69e3133f672e4d48fa4716755cdf9f7d47c794904b64c91d58c51c` |
| worker | `sha256:2aef77e2443ae0c365237016476c3c63809ce5c21661d379e89da632f392911a` |
| worker_fast | `sha256:f8c6ff77ea43e22873c356ae821f153628e1bd8b19a37849044b89a2ead6fd42` |
| beat | `sha256:2105290c2dab088aebca53a17938abb1f09d428d4b80e1187a8b13a4fa0f7a25` |

公网home/health/login/www、有效CSRF匿名candidate/preview/replay/cleanup/**policy/revoke**拒绝、旧账户保护、API/HTML质量标记、本站health/robots真实SafeFetcher TLS通过。worker readiness/实际image/实际内存上限/原卷UID0与0700通过。

仅四应用被重建。MySQL/Redis和同机researchassistant/viva-insight容器身份/启动时间/restart不变；Caddy仍从2026-07-09 08:56:14 UTC运行，未重启。保留base→prod→caddy→evidence层；仅web挂既有external私有卷，另三应用无挂载，均无源码挂载。未chmod或覆盖原卷，无额外新闻/付费模型/邮件手工调用。

## 回滚、清理与边界

新阶段化helper准备了失败恢复，**未触发，不冒称回滚演练**。保留c9表/列及证据、不downgrade/整库覆盖。旧22不会维护持续策略/source_generation：失败恢复先停止web，当前锁定读取确认无policy决定才允许恢复旧web；存在决定或无法确认则旧web保持停止、恢复旧workers/beat并报告人工恢复需求，不能悄悄回到B1。回滚亦保留本轮容量缓解上限。

本轮标记`fsi.validation=fsi-mp-20260910060307`的临时容器/内部网络/三个卷及生成凭据已精确清理；保留生产证据卷、备份及旧镜像。所有新helper归档至备份`helpers/`、mode600，删除`/home/ubuntu/`原执行入口和release-state；`MP_FINALIZED`。日志与非正文元数据选择性取回`/tmp/fsi-mp-evidence/`，未取回数据库备份。

工具/fixture偏差单独保留，不算业务red：Compose无插值输出是`512M`字符串而非字节；无敏感smoke脚本误设600使cap-drop root读失败，仅这两个脚本改644；复合命令曾由末尾gh掩盖SSH失败，随后用set -e；SFTP不展开远端花括号，改逐文件明确参数取回。没有放宽凭据、备份或证据权限。

剩余：B2b.2独立留出验证/规则审批、可靠run/lease/outbox/统一调度、M3/M4、policy并发/负载/恢复与旧采集内存峰值。最后文档提交只同步checkout，不重建14dc6f1运行镜像。
