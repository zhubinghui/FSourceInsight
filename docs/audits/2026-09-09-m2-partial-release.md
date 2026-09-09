# M2-A/B1/B2a 生产发布记录

## 结果

- **已上线**：应用 `22c098c5fa1564ec17c47bc780e2f64eae0b5143`（业务A/B1/B2a来自90c94b6，22c098c增加可选证据Compose层及验收），schema **`b6c2a4d9e710`**。
- 2026-09-09 **15:25:00Z→15:25:06Z** 四应用切换至health恢复，约6秒；worker readiness、镜像一致、证据挂载及公网门禁通过，未触发回滚。
- 仅web/worker/worker_fast/beat改变；MySQL、Redis和其他项目容器ID/启动时间/重启数逐项不变。系统Caddy仍从2026-07-09 08:56:14Z运行，没有重启。
- 新用户“部署一下生产”授权覆盖本次发布，取代旧“完整M2后才上线”的安排；**不是完整M2已经实现**。[执行计划](../superpowers/plans/2026-09-09-m2-partial-release.md)记录边界及偏差。

## 本轮验证

| 项目 | 结果 |
|---|---|
| 可选Compose层TDD | prod、prod+caddy两个组合先因缺文件red；随后规范化CLI environment列表观察（测试错误，不算业务red），两项green |
| 本地全套 | 576 passed / 14专用MySQL skip / 3453 warnings，154.31秒 |
| 准确22c098c CI | [34367023823](https://github.com/zhubinghui/FSourceInsight/actions/runs/34367023823)，test、mysql-integration均success |
| 真正web / worker候选 | 本轮各14/14隔离MySQL通过，26.715 / 26.538秒；真实候选代码，只挂测试副本，不覆盖app源码 |
| 四候选smoke | 43模板、Admin/CSRF、API/HTML质量标记、快照回放及基础billiard prefork→parser通过 |
| 真实Docker证据卷 | Admin HTTP捕获、跨容器非阻塞flock忙时新捕获503、另一重建容器离线回放200且未启动fetch；Article0/无active，原报告保留可读 |
| 文件权限 | 0700目录/0600文件，另一UID读取拒绝；实际save经过flush/fsync及目录fsync。不是加密/同UID沙箱/分布式锁 |
| 生产迁移 | e6→a731→b6，仅新三表且初始为空，model diff0；10179 Article、38 sources、15317 logs及4模型配置保持不变 |
| 上线公网 | home/health/login/www 200；有效CSRF匿名candidate/preview/replay/cleanup均拒绝；旧API/HTML unknown标记正确、无私有provenance |
| 真实网络 | 只对本站health/robots执行有界SafeFetcher，DNS/socket/TLS/CA通过；没有额外新闻/付费模型/邮件 |
| 最终运维 | 两worker ready，四应用restart0/OOM false；测试容器/网络/三卷/生成凭据精确清理，生产证据卷保留 |

上线短时内存观察约web311/512MiB、worker573/1024MiB、fast366/512MiB、beat245/256MiB；后续观察beat仍245MiB、restart0/OOM false。**beat余量小，是监控/后续容量验收风险**，本轮没有擅改资源上限，短时通过不代表长期稳定或并发压力验收。完整broker、长期FD/RSS、真实来源覆盖率/成本、崩溃/恢复演练仍未完成。

## 私有证据配置

[运维说明](../ops/private-crawl-evidence.md)：生产层顺序为base→prod→caddy→**evidence**。仅web挂外部专用卷`fsourceinsight_crawl_evidence_data`至`/var/lib/fsource-evidence`；当前真实应用UID0，新卷确认空后初始化0700。worker/worker_fast/beat无原文挂载，四应用均无源码挂载。

默认不保存原文，管理员仍须在候选页单次许可/质量设置后主动勾选。生产卷未植入合成测试数据。24小时可用期不代表到点物理删除；后台显式全store清理或下一次保存才回收过期/孤儿，无新增cron。升级时漏掉evidence层会禁用保留/回放能力，外部卷仍存在，不应删卷“修复”。

捕获/回放ready仍不授予批准、入库或网络权限。持久policy/独立验证/人工审批/active及previous/CAS、可靠run/lease/outbox、统一调度与Agent/浏览器均待实现，旧日常爬虫链不变。

## 备份与回滚

- 本轮目录：`/home/ubuntu/fsourceinsight-backups/m2-20260909145831`
- single-transaction/quick备份18,992,013 bytes、mode600；gzip和SHA256复核通过，未读取/外传正文，未做完整恢复演练。
- SHA256：`ba74023a4a03c18341bd7d3c54469a72b71379700feb6dc03a8798bfad378c60`
- 旧checkout4477cfd、旧应用M1/1052edf、旧schema e6；准确旧image ID、`fsourceinsight-<service>:rollback-m2-20260909145831`及rollback overlay均保留。
- 回滚仅以旧四镜像恢复应用，保留新三表及证据卷，**不downgrade、不恢复整库覆盖新写入**。旧M1不需要evidence层。恢复分支未触发，不冒称故障回滚演练已完成。
- helper已归档至本轮备份`helpers/`、mode600，外部执行入口已删除；包含固定旧ref/路径，不得直接重跑。测试资源清理按本轮精确label/name，不prune，不影响其他项目。

最终镜像：

```text
web         sha256:266f7d7fe7dfbfaabbd33ef23922ac71a6e6fdee65abf2ba14f1e231be5bbaf5
worker      sha256:eaa41111ac0866479b44d9cd277aa3955f540d3a5ce29611cff37c31e4ad7cd7
worker_fast sha256:51db50582a5dc576fec6634583b120d06f0e911476ac71d5cdfca1b84eb11df3
beat        sha256:b00f98a81d648224b93759ca2a782b4c8ecd0328ea7390f4967bcd8cf6fdc248
```

4模型配置指纹（含role/priority）仍为`ff4b48c9f237d6974d8e5605bd9233d6f29215ab21ea157d5856fff3697faef1`，不重新seed或替换管理员配置。
