# 独立Admin安全发布（2026-09-20，已部署）

## 结果与范围

用户要求解释付费暂停并尽快部署其他功能；未同意停用现有AI。因此按[分批计划](../superpowers/specs/2026-09-20-admin-safety-release.md)发布不包含M3的独立Admin修复：

- **应用 `e6469ba0e5f430955d3abf97c85dd3a10ee5126d`，schema仍 `b3d5e8a1c407`**。
- 已上线账号防自锁、密码/重复邮箱校验、已有usage/采集审计关联的删除保护、危险操作确认、每日采集小时/时区设置修复。既有生态地图/审核/去重保留。
- 四应用一致切换；现有LLM代码、模型/价格/环境配置及运行依赖不变，没有为此次发布禁用付费AI。
- **不是M3部署**：新计费账本、学习/留出、异步初始企业分析和M3追加审计删除保护仍在release分支。没有迁移/seed/自动赋权；不是把新账本回退给旧付费调用方。
- 没有用真实模型、新闻抓取、SMTP作验收；只检查本站及隔离合成业务。没有完整M3或长期容量声明。

## 候选和门禁

准确[e646 CI35510283338](https://github.com/zhubinghui/FSourceInsight/actions/runs/35510283338)成功：713离线/16专用skip（441.57s）、16真实MySQL（44.533s）、真实broker100任务及RSS451212KiB完成后回收。

实际镜像在同机独立internal网络、无host端口、合成凭据600、m0-mysql/fsource_m0_validation中验证；仅挂tests，不覆盖镜像应用/迁移。MySQL512MiB、Redis64MiB、串行runner1536MiB/1.5CPU/192PIDs。实际结果：

| 阶段 | 镜像 | MySQL | 秒 |
| --- | --- | --- | ---: |
| 候选 | web | 16/16 | 37.278 |
| 候选 | worker | 16/16 | 37.197 |
| 部署后 | web | 16/16 | 36.314 |
| 部署后 | worker | 16/16 | 37.341 |

- 两镜像各48模板编译、真实CSRF/登录、Admin/公开HTTP、防自锁、弱密码及无效时间设置拒绝通过。
- 实际worker镜像真实Admin→Redis→prefork100任务后回收、RSS450868KiB任务完成后回收、父进程存活/下一任务正常，`WORKER_LIFECYCLE_OK`。
- 应用/迁移/scripts/celery_app/wsgi逐文件SHA与固定e646源一致。服务环境/argv/资源/卷同切换前。

### 保留的准备失败

1. 私有helper误假设.dockerignore首字节为`**`，实际首行是解释注释；构建前退出。改为首条非空/非注释规则检查，无产品变更。
2. 普通Dockerfile重新构建把**LiteLLM1.101.0变成1.102.0**，被实际runtime一致性门禁阻断，未投入生产。为不顺带改变AI，改从现网不可变web/worker镜像ID构建源码覆盖层；不使用容器可写层，范围无文件删除/依赖输入变化，并用完整源码manifest防残留。
3. 新候选保留Python3.12.14、LiteLLM1.101.0、OpenAI2.54.0、SQLAlchemy2.0.54、Celery5.6.3、PyMySQL1.2.3。独立release Dockerfile及被拒镜像保留；仓库Dockerfile未改。未来标准全量重建仍会使用浮动依赖，需要另行审核，不能复用本次runtime稳定性结论。

## 切换与备份

15:58:16Z最终门禁通过；15:58:18Z暂停beat。两worker active/reserved/scheduled、crawl/llm/email/celery深度及unacked均0；只发送TERM，未到期KILL。15:58:40Z全部旧应用退出，冻结Admin写入。

服务器私有备份：`/home/ubuntu/fsourceinsight-backups/admin-20260920-1530/database.sql.gz`，**19,930,641 bytes / mode600**，gzip CRC、dump完成trailer及SHA核验：

```text
b83ac507ec836337ed526607d61c82ad2a41e0307663c533068997979224fc07
```

没有取回备份正文。`rollback.compose.json`保留旧四image/完整argv，`candidate.compose.json`固定本次image。服务器工作树从clean b08正常ff到e646；同一临界区flock、原refs/身份再检查，无force/reset或对另一工作树的写入。

15:58:51Z新web健康恢复；停止全部旧应用到该健康检查约10.4秒，不是精确HTTP不可用时长。15:59:21Z在线验收完成，**15:59:22Z beat最后恢复**。未触发回滚，无DDL/整库恢复。

实际image IDs：

```text
web                 sha256:c252d372ff0838c6027ad48876115e20c9c44984c5d86d7f602fe8a21743db5c
worker/fast/beat    sha256:15f671fd5aaddbf91511b2cab4541c191dcf16541b82383260a42d08d0a3259c
```

## 在线验收与清理

- 本地/公网health、companies/API正常；匿名Admin四入口拒绝；两worker注册和实际队列/prefork2/50次回收参数通过。393216KiB回收argv、web512MiB/worker各1GiB/beat384MiB保留。
- schema b3、实际model diff0；billing上界列仍不存在。Article10822/Company7836/NewsSource38/StartupSource26/User3/LLMConfig4及五张M2表0保持；approved7637/rejected199分布不变。LLM配置、系统设置、两类来源全投影hash一致，不是只检查行数。
- web原external私有卷RW、UID0/0700保留，其他应用不挂证据；没向生产卷写合成文件或改权。
- 9个非目标容器（含MySQL/Redis）的image/start/restart保持，Caddy主PID/start保持。只更新四个目标应用。
- 部署后两镜像MySQL复验通过后，精确清理本轮label的9容器、1 internal网络、独立MySQL卷及测试Redis隐式/data匿名卷共2卷；删除合成凭据。删除匿名卷前确认精确测试容器独占引用。未prune/触及生产卷。
- 16:05:54Z清理后health仍全ok，四应用OOM false/restart0，MemAvailable4527384KiB。16:10:18Z再确认公网健康/服务器clean e646及清理记录，四应用memory.events max/oom/oom_kill均0。短观察不是长期内存/吞吐或专用学习worker容量证明。

原始准备/构建/测试/切换日志、源manifest、pin层、备份及被拒runtime证据仅留服务器上述私有目录；受选非敏感证据可保留本地临时目录，不提交原始控制回复/凭据/dump。

后续仍须完成[M3计费审核](2026-09-20-m3-billing-review-inputs.md)及M3实际镜像/切换门禁。此前发现的日常备份cron失效也未在本次修复；本次新全备份不能代替长期备份恢复管理。
