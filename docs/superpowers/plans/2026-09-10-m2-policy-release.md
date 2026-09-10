# M2-B2b.1 提交、生产发布与远程MySQL验收

## 授权与边界

用户新授权“提交并部署，完成之后远程完成一下mysql的测试”。本轮允许明确allowlist正常提交/推送、SSH、备份、独立候选测试、b6→c9增量迁移及四应用切换；部署后额外复跑远程独立MySQL测试。为避免未验证迁移先进入生产，切换前也须远程跑15项作为门禁，失败先停发布并记录。

起点master@e98af16、24个B2b.1已知改动，暂存区空。生产最后验证22c098c/b6，需重新预检。只发布已完成策略/撤权，不声称独立验证、规则发布、run/outbox或调度完成。单写者，不使用子代理。

- 不读取/输出.env、私钥、数据库备份正文或凭据；不seed、dump恢复、down -v、prune、强推/reset/stash，不运行历史归档activate。
- 只更新web/worker/worker_fast/beat；保持MySQL、Redis、Caddy及同机项目不变，保持base→prod→caddy→evidence层与原有私有external卷；不覆盖或chmod已有卷。
- 测试仅独立内部网络/临时MySQL8.0/合成数据和凭据，无生产凭据、无host端口。真正候选只挂tests，不覆盖app源码。生产SQL只读检查，唯一计划内写操作为已备份的扩展迁移。
- 不触发额外新闻、模型、邮件或创建生产grant/候选/原文；仅本站health/robots真实TLS canary与匿名权限探针。原有后台正常恢复不等于额外手工触发。
- beat余量小需复核，不凭旧短smoke称容量通过；若资源不足先记录调整，不盲目抢资源。

## 顺序与门禁

1. [in_progress] 本地差异/全部测试/静态与allowlist核对；远端只读预检：Git、镜像、schema、计数/LLM配置、卷权限/挂载、资源与worker状态。
2. [pending] 正常提交推送固定候选，准确SHA对应CI两job成功；备份gzip/校验/权限及旧四镜像/ref/Compose回滚点。
3. [pending] 远端ff-only、串行构建四候选；独立MySQL真正web/worker各15项、四镜像模板/HTTP/回放/基础prefork门禁，生产容器不变。
4. [pending] 准备有阶段恢复的**新**helper；停beat、active/reserved/scheduled全0、warm-stop worker；lock_wait_timeout=10迁移b6→c9，model diff0、旧数据/配置保持，源策略不自动grant。
5. [pending] 仅四应用切换，health/worker/image/私有卷/匿名权限/本站TLS通过；记录资源、重启/OOM、非目标容器身份。
6. [pending] 按用户要求部署后用准确已部署image在独立MySQL复跑15项；不在生产库运行破坏性fixture，不把普通串行15项称完整policy并发/压力/恢复验收。
7. [pending] 精确清理临时测试资源/凭据；保留备份/回滚镜像/生产卷，归档helper并移除外部执行入口；报告、收尾文档提交/推送与准确CI，文档同步不重建镜像。

## 回滚约束

迁移expand-only，应用回滚保留新表/列/原始证据，不能downgrade或整库覆盖。旧22不理解持续策略/source_generation，不能保证回滚期间新策略控制；切换失败若没有新policy决定可直接恢复原四镜像（保持evidence层）。如果已产生policy决定，则旧版恢复前必须限制后台采集入口/变更，恢复新版后重新审阅策略；不得静默回到B1许可。回滚分支准备不代表真实回滚演练。

## 记录

- 容量契约第一次执行遇到fixture观察错误：`--no-interpolate`返回`512M`字符串而非字节数，int转换ValueError，尚非容量契约red。改检查CLI真实保留的尺寸声明，再观察旧fast/beat上限不满足新契约。

- OOM证据：内核2026-09-09 23:00:19的MEMCG杀进程明确对应fast容器，memory.events max104/oom5/oom_kill1；不是宿主整机内存耗尽，也不是单纯陈旧flag（父进程存活，restart0）。暂不重放真实采集诱发OOM，不宣称内存增长/峰值根因已定位。部署范围补充**容量缓解**：fast512MiB→1GiB、beat256→384MiB，保持并发/其他服务上限不变；现有可用3776MiB容纳增加640MiB及串行768+512MiB测试预算。先以已认可Compose CLI验收面新增上限/有界总额契约red→green；这只验证配置，不冒充OOM负载回归。长期内存/单任务峰值仍后续。
- 回滚进一步收紧：恢复旧web前只读确认无policy决定；若已经有决定或无法安全确认，保持web停止（对本站HTTP fail-closed）并恢复旧workers/beat，报告人工恢复需求，不用旧B1绕过新策略。新脚本明确此分支，不重跑历史helper。

- 预检偏差（先停切换）：远端e98 clean，MySQL8.0.46/b6、Article10207/log15381/source38、新三表0、4模型配置指纹不变、原证据卷UID0/0700/空。内存可用3776MiB/磁盘21GiB。**worker_fast running但OOMKilled=true/restart0，473.5/512MiB；beat245/256MiB**，不同于上轮OOM false。需只读查内核/容器事件及worker任务状态，必要资源变更先TDD再提交，不用短health掩盖。
- 本轮本地复验638 passed/15专用skip/4367 warnings，185.68秒；日志/tmp/fsi-mp-local-tests.log。

- 2026-09-10 05:48Z确认本地e98af16、24项已知改动/暂存区空。上轮638/15仅历史本地结果，本轮复验及远程实测尚待。
