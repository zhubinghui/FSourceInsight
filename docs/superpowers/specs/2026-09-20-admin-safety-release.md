# 独立Admin安全发布：保持现有AI（2026-09-20）

## 依据及范围

用户要求解释付费暂停并尽快部署其他功能。按照[完整发布计划](2026-09-19-m3-current-release.md)新增分批策略：先发布可独立的`e6469ba0e5f430955d3abf97c85dd3a10ee5126d`，不部署M3计费/学习分支，不需要为此次发布停用AI、改价格/上界或混跑旧新调用路径。

改动：Admin防自锁、密码校验、重复邮箱拒绝、已有usage/采集历史的删除保护、后台设置有效性与整点按所配时区/小时采集。生态地图和数据保留。schema仍`b3d5e8a1c407`，本次无新迁移/seed/业务数据修正。

## 硬边界

- 单主会话，不用子代理；不改另一工作树，不覆盖M3累计内容。只发布已提交固定SHA。
- 不重启MySQL/Redis/Caddy或其他项目；保持base→prod→caddy→evidence、web原私有卷/UID/0700、两worker并发2及回收限制。
- 不做真实采集/模型/SMTP验收；预检/验收只读本站与合成隔离数据。
- 独立internal网络、显式m0-mysql别名/fsource_m0_validation、合成凭据600、无host端口。测试只挂tests/support，不覆盖镜像内app/migrations；串行执行，受CPU/RAM/PID限额保护。
- 候选构建/测试不改运行容器；保持至少约1.5GiB可用内存，不承诺构建工具整个主机硬内存上限。若资源不足先停止本轮测试，不杀生产业务。
- 只有准确SHA CI和真实候选门禁通过，才进入beat暂停/drain/worker warm-stop/web短切换。停止前再次核对原容器身份和代码refs，发现他人发布则停。
- 非阻塞flock标识本轮发布；锁不能证明其他未遵循协议的写者不存在，仍做身份复核。
- 新数据库全备份压缩校验/trailer/hash/mode600，只留服务器私有目录，不取回内容。记录旧四images/完整argv用于回滚。
- 不downgrade/恢复整库。此独立分支schema和旧程序一致，切换失败可恢复固定旧四镜像；仍先停止新beat/worker，禁止不明任务强杀重试。
- 超时/错误先更新本计划，再调整；测试失败不换旧证据、不跳过。精确清理本轮label资源及合成凭据；保留备份/镜像。

## 步骤

1. [complete] 生产clean b08/schema b3，原四镜像/argv/环境hash/私有卷与数据计数/配置指纹留档；e646准确CI通过。
2. [complete] 独立源码/固定原runtime构建web c252d372ff08、worker 15f671fd5aad；源逐文件hash一致，Python3.12.14/LiteLLM1.101.0/OpenAI2.54.0等与现网相同。
3. [complete] 实际web/worker各16项MySQL、各合成Admin/模板/HTTP、真实Redis/prefork回收全部通过，prepare.exit=0；生产身份未变、MemAvailable4036808KiB。拒绝的普通重建将LiteLLM升级到1.102.0，未采用。
4. [complete] 15:58:18Z停beat，active/reserved/scheduled/三工作队列及celery/unacked全0；仅TERM顺序warm-stop，15:58:40Z全部旧应用退出。新600备份19930641字节/CRC/trailer/SHA核验后ff e646，15:58:51Z web健康；四应用同SHA，15:59:22Z beat最后恢复。无迁移/模型或价格更改/回滚。
5. [complete] 本地/公网health、companies/API、匿名Admin拒绝、四应用环境/argv/limits/挂载、schema/model diff0、数据计数/review分布及4类配置hash均通过；9个非目标容器及Caddy PID/start不变。部署后web16/36.314s、worker16/37.341s均通过；已精确清理9容器/1网络/2卷和合成凭据，Redis匿名卷删除前核对独占引用，无全局prune。16:10:18Z公网health全ok、服务器clean e646、四应用memory.events max/oom/oom_kill全0。
6. [complete] 独立发布审计/主计划/进度已更新，收尾仅正常提交文档，应用不变；明确Admin已部署/M3仍待，不声称全部M3完成。

切换helper在最终临界区再次检查原身份/refs/Compose生效环境、保留源数据fingerprint和schema。所有warm-stop仅发送TERM并等待，不调用带到期KILL的stop。若超时保留状态/停止切换，不能强杀在途付费。回滚前必须只读确认schema仍b3且无M3账本；他人并发改版/新账本出现时不自动恢复旧付费调用方。

## 观察

- 15:19:36Z：四应用仍eco-20260919220547，连续运行17小时；MySQL/Redis2个月。Compose5.1.3，工作目录/home/ubuntu/FSourceInsight。
- MemAvailable4234656KiB、root磁盘19239MiB可用。仅初始余量，不是压力门禁。
- origin/master=e6469ba、另一工作树clean；CI35510283338成功（713离线/16专用skip、16实际MySQL44.533s、真实broker100任务/RSS451212KiB回收）。完整M3分支9baf6f3保留，不更新master代码。
- 初次私有准备helper在构建前退出：错误假设.dockerignore首字节为`**`，实际先有解释注释。属helper前提错误，不是产品失败；准备日志保留prepare-01.log，先修正为首条非空/非注释规则，再同协议重试。没有构建/测试资源或生产变更。另外SystemSetting真实文件为models/setting.py、主键key，已按实际结构准备只读指纹查询。
- 最终临界区前再次核对：GitHub master仍e646、另一工作树clean、生产仍clean b08。候选web16/37.278s、worker16/37.197s；两镜像各48模板及真实CSRF/登录/防自锁/弱密码/无效时间设置通过；真实broker100任务/RSS450868KiB任务完成后回收通过。
- 实际源码比较b08→e646：app/llm、app/config.py、requirements均无变化；候选另比较实际Python/SDK依赖版本，避免无意升级现有AI适配器。
- 第二次准备被实际runtime版本门禁正确阻断：公开Dockerfile的浮动基础镜像/未锁依赖重建改变了运行依赖，尚未开始MySQL/Redis/生产切换；保留prepare-02.log及被拒镜像。修订构建：以当前运行的不可变web/worker **镜像ID**（不是容器可写层）作基础，仅复制固定e646源码。该范围无删除文件/requirements变化；另外逐文件核对镜像app/migrations/scripts/celery_app/wsgi与固定源的一致性。保留原Python/SDK依赖，记录独立release Dockerfile；不改变仓库Dockerfile或计费行为。后续完整重建/依赖升级仍须单独审核。
