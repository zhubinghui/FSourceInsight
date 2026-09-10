# Worker并发/任务后回收：实施、合入与发布

## 授权与范围

用户在容量评估后授权合入/部署，并明确“继续实现”LLM并发4→2及任务后的子进程回收。主会话单写者，不使用子代理。保留现有五份未提交容量文档，不reset/stash/覆盖。仅FSourceInsight，不改其他项目、swap、CPU配额、数据库参数或模型路由；不手工触发生产新闻/模型/邮件。

- 生产overlay将LLM并发改2；fast仍2，队列与worker名保持。开发base不受影响。
- 两个task worker明确prefork；每子进程**最多50个已完成任务**，或任务完成后RSS超过**393216KiB（384MiB）**即替换。beat不是pool，不配置回收。该初始值比已观察约270–295MiB RSS有约90MiB余量，50限制长期保留且避免逐任务fork；不是实测最优吞吐值。
- Celery CLI与已安装billiard实现确认单位KiB、先返回任务结果再检查回收。回收不是任务进行中的硬RSS限制，不改变ack/retry/outbox，不保证OOM时不丢任务或不重复付费；不杀正在执行的任务来腾内存。
- 继续fast/LLM1GiB、beat384MiB/web512MiB。当前13:00Z可用3840MiB、磁盘21GiB，LLM852.6MiB；重建后的降幅含进程重启效应，不全归功于并发/回收，不称夜间容量已验证。

## TDD与运维验收（沿用已确认接口）

1. [complete] 真实Compose CLI：生产LLM=2，dev=4；随后两个worker的prefork/50/393216、队列不变、层叠组合与原私有卷/限额不变。逐条red→green，非自身helper mock。
2. [complete] 独立Linux实际broker/prefork验收：真实Admin HTTP触发已有crawl任务，公开Celery结果/inspect与OS PID观察已完成任务及子进程更替；不新增生产或测试专用任务/API。合成网络只在Popen/DNS等系统边界，内存触发只在测试worker的外部边界保留/释放受限内存。确认任务未完成时不回收、完成后换PID、父worker存活/后续任务可执行。LLM实际启动参数/并发单独检查；不通过真实付费请求测试。
3. [complete] 本地全套/静态/文档、正常allowlist提交推送、准确CI；如果复用既有image，必须核对本轮运行源码无改变并明确image ref与配置ref，不冒称新构建。
4. [complete] 重新远端预检/备份/旧镜像与**旧命令**回滚点；候选验证、独立MySQL15项及资源门禁。临时MySQL768MiB+Redis64MiB+一次仅一个生命周期runner≤1GiB，进入前MemAvailable至少3.5GiB；不常驻占资源，不与其他重任务并跑。
5. [complete] 停beat/排空两worker/warm-stop，**无新DDL**、c9保持；优先只重建worker/worker_fast并恢复原beat，web/MySQL/Redis/Caddy/其他项目不动。检查实际CLI参数、pool并发/回收设置、健康、OOM计数、任务注册与可用内存；失败恢复旧命令/镜像，不降级DB。
6. [complete] 部署后独立MySQL复验/精确清理、记录实际资源与剩余风险、合入报告/文档同步；不为纯文档重新构建运行应用。

## 当前验证记录

- 已按准确Docker日志恢复冲突的MySQL输出，保留lifecycle独立前缀产物并全部重新核对。14:02:28Z验证home/www/login/health、原web和非目标容器身份不变、beat原ID恢复、证据卷UID0/0700保持；9个临时容器/网络/测试卷/合成凭据删除，helpers/state归档600且原入口删除。
- 清理后MemAvailable4297MiB，LLM365.7MiB、fast378.7MiB、beat243.1MiB；不以重启后降幅冒称长期/吞吐验证。发布报告见 [worker回收发布审计](../../audits/2026-09-10-worker-recycling-release.md)。收尾仅文档提交与ff-only同步，不重建；对应文档CI另按准确SHA确认。

- retry-2新备份19,094,088 bytes/600；13:53:30Z→13:53:54Z切换成功，完整规范化argv校验通过、两pool2/50、c9与DB元数据相同，原beat恢复，web未重启。
- 部署后web/worker隔离MySQL15/15（29.475/28.779秒），部署worker image再次完整broker门禁通过RSS450672KiB。
- 清理前证据门禁发现host日志名冲突：post MySQL `deployed-worker.log` 被随后同名lifecycle输出覆盖；容器名字不同、两个实际执行均exit0，所有容器/卷尚未删除。先暂停清理，给lifecycle产物统一独立前缀并禁止覆盖，从仍保留且有正确label/exit0的MySQL容器Docker日志恢复精确原输出；不重跑业务、降低断言或将其称测试失败。

- 首次配置切换在checking阶段stdin第7行assert失败；已确认是门禁将Compose命令字符串与Docker实际argv数组直接比较，类型不同而误拒。候选两pool实际2/50已通过；恢复分支warm-stop新worker、用旧image+旧command重建并通过注册门禁，13:49:13Z恢复原beat。只读复核旧命令确实恢复、四应用OOM false/restart0、web原ID/启动时间未变、13:50:32Z公网health全ok。
- 修复仅对预期CLI字符串shlex规范成argv，保留完整参数等值断言；负对照必须仍拒绝已恢复的旧命令。重试前新建retry-2备份/清单/时间点，保留第一次失败日志和原备份，重新检查同机服务。配置commit/镜像/CI不变，不通过宽松检查绕过问题。

- 配置提交81135d8，准确CI34483808675两个job均success（含新真实broker gate）；远端checkout已ff-only同步，运行image未改。web/worker独立MySQL候选15/15（30.023/29.817秒）。
- 新备份wr-20260910132339：19,094,087 bytes/mode600/gzip/SHA256通过，旧镜像+旧命令回滚JSON已保留。负label工具错误已按相同协议、严格partial文件集合恢复；不删除备份或重复迁移。
- 发布采用四标准Compose层+本轮只固定两image的临时overlay；无DDL/web重启。先短暂停beat、确认idle再TERM/wait，不用docker stop超时强杀。若warm-stop超时，保持beat暂停并报告，不通过强制重建中断任务。web继续服务期间允许正常业务计数变化，结构/模型配置检查与计数记录分开，不将正常任务结果误判为数据损坏。

- 新备份预检在容器清单处遇到Docker CLI `invalid filter 'label!'`，立即停止，尚未备份数据库/打tag/同步checkout/暂停服务。已创建的只有本轮备份目录与refs/state元数据。先记录偏离，再将不支持的负label过滤改为两次受支持的正向ID清单集合差；仅在精确partial文件集合/旧HEAD/state匹配时同协议恢复，不重跑旧activate或删除现有备份。

- Compose两轮真实red：先生产并发4≠2，最小修改后4组合green；再缺prefork/回收阈值，最小修改后生产运维10项green。dev保持4/不配置回收。
- 独立Linux首次完整通过：生产LLM真实prefork2/50；真实Admin发送100个停用来源任务，子进程回收/父进程存活；新fresh pool的RSS实际450420KiB，在任务内保持存活，释放后RSS回收/回收后新任务成功，Article0。模拟仅进程/网络边界，无新任务/API或真实模型调用。内存case新pool消除50任务计数混淆；随后补49任务不提前回收断言，在准确fast运行image完整复跑通过（RSS450720KiB）。
- 本地643 passed/15专用MySQL skip，184.44秒。Linux gate不以skip代替，新的真实broker检查加入CI：offline job导出仅commands artifact，mysql job下载后执行，避免手抄生产参数。
- 已确认Linux RSS是ru_maxrss高水位，不是PSS/当前RSS；文档明确任务尝试计数、父进程增长不受回收控制、吞吐未实测。静态审阅时更正测试管理员fixture为实际is_active_user/password_hash，无执行失败或产品修改。
- 应用代码/依赖/Dockerfiles自14dc6f1完全未改，本轮采用**配置发布、复用固定运行images**，不做无意义重建；仍执行新Compose/真实broker/独立MySQL门禁。
- 新临时RUN=wr-20260910132339，internal网络/独立MySQL768MiB/Redis64MiB/串行runner1GiB。该条为隔离验收阶段记录，当时生产尚未暂停或改动；随后部署与测试资源清理完成。测试state仅新路径，不复用旧发布helper。

## 基线

本地/远端de80b81，运行应用14dc6f1/c9；本地5份容量文档未提交。当前生产LLM852.6/1024MiB、fast445.1/1024MiB、beat245.2/384MiB、web385.2/512MiB。上一轮CI/MySQL15通过只代表旧配置，不替代本轮prefork回收验收。
