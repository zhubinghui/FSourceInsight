# 可选学习worker：配置与运行门禁

**本地配置/协议验证完成，尚未部署；M3未完成。不要据此直接启用生产学习。** 实际容器、只读挂载、MySQL/Redis、prefork超时/崩溃及容量仍须独立门禁和部署授权。业务限制见[学习操作说明](crawl-learning.md)。

## 层与权限

新增`docker-compose.learning.yml`必须放在prod及evidence之后；使用系统Caddy时顺序为：

```text
docker-compose.yml
→ docker-compose.prod.yml
→ docker-compose.caddy.yml（如使用）
→ docker-compose.evidence.yml
→ docker-compose.learning.yml
```

新服务`worker_learn`属于`crawl-learning` profile，普通启动不会启动它。但Compose显式指定服务也可以启动profile服务，不能把profile当访问控制。

另一个独立条件是`CRAWL_LEARNING_ENABLED=1`。学习层将该插值值统一用于web/beat/worker_learn，默认0；未启用时启动guard拒绝消费。不要只改一个容器的环境，也不要把启动worker视为授予来源访问或计费许可。普通两worker的队列、并发和资源限制不变。

新worker和web使用**同一个预先初始化的外部卷**`fsourceinsight_crawl_evidence_data`：
- web读写/保留/清理；worker_learn只读、nocopy。
- 根目录0700、归实际应用UID拥有，单文件仍由每次证据加载核对0600/UID/链接数/指纹/绑定/期限。当前Dockerfile默认UID为0；若改UID，须协调web/worker和现有文件，不能简单chmod放宽。
- 不创建/复制/重新初始化现有卷；不给普通worker、beat、nginx或浏览器服务原文访问。
- worker读路径不创建锁或清理文件，web清理后失效的证据仍会阻断学习。只读挂载不加密、不证明是正确卷，也不保证证据不会到期。
- 解析helper仍不是OS/文件系统沙箱：在可信协调worker内运行的helper可能访问该进程环境允许的文件系统，不应冒称浏览器级隔离。

## 初始运行边界（待实测）

| 项目 | worker_learn |
|---|---|
| 消费队列 / 节点 | `crawl_learn` / `learn@%h` |
| 池 / 并发 / prefetch | prefork / 1 / 1 |
| 子进程回收 | 完成50个Celery任务，或任务完成时RSS高水位393216KiB |
| soft / hard task limit | 180 / 195秒 |
| 容器初始上限 | 1GiB、1 CPU、64 PIDs |
| 可写临时空间 | 64MiB `/tmp` tmpfs；日志`/tmp/crawl-learning.log` |
| 其它 | 根只读、cap_drop ALL、no-new-privileges、init |
| warm-stop宽限 / 重启 | 210秒 / on-failure最多3次 |
| 健康检查 | 间隔60秒、Docker timeout20秒、启动宽限60秒、连续失败3次 |

回收计数包括`recover`，不是文章数或模型轮次数。RSS回收只在任务结束后检查；内存可能在结束前耗尽。1GiB需容纳父进程、池child、解析helper、健康CLI及tmpfs，不是已证明的容量。还要考虑现有服务和同机项目，不能直接套用旧整机余量。

任务soft/hard limit是新池的进程保护配置，不改变从Admin提交起的180秒逻辑期限，也不能撤回远端已准入请求。hard kill后的预留仍可能unknown/reserved；不得清除重付。Docker stop宽限超时可能强杀，正式切换必须先观察、排空和warm-stop，不能靠强杀满足部署计时。

## 启动guard与健康CLI

Compose entrypoint为`python scripts/learning_worker.py run`，仅接受Compose中的完整、已审查Celery命令。变更队列/并发/timeout/recycling等需要同步CLI契约与测试，不能给这个入口传任意命令或`--purge`。

启动前只读检查：
1. 学习标记启用。
2. 私有目录在checkout之外、非末端symlink、0700且当前UID拥有；实际目录fd的文件系统标记为只读。
3. DB `alembic_version`与镜像内唯一head一致（当前候选head `c7f21a9d680e`；4a历史里程碑为`f8b64d2c901e`）。这不是完整schema diff或模型/权限批准。

启动前不迁移、修权限、建卷或派发任务。失败输出固定NOT_READY，不打印路径/SQL/broker异常。启动失败最多重启3次后需人工处理。

容器内运行：

```bash
python scripts/learning_worker.py check
```

默认只查询本机`learn@hostname`；指定目标时用`check --node learn@HOST`。检查local前置后，通过Celery控制接口核对该节点的注册任务、唯一队列/routing key/exchange、实际prefork进程数、prefetch、任务回收和soft/hard配置。没有业务任务/付费调用；不输出原始控制回复。

`LEARNING_WORKER_READY`仅表示这些运行检查通过，不证明：beat/web同时启用、所有来源证据可用、供应商价格正确、模型可用、账本已对账、全局没有额外worker、cgroup参数已实际应用或容量足够。普通两worker另用既有`check_worker_readiness.py`；启用三worker后显式`--expected-workers 3`，并额外运行学习检查。不得只用任务注册或ping代替队列检查。

独立CLI的DB连接/控制查询不是全程硬deadline；控制查询每次2秒，Docker健康检查以20秒超时保护该检查进程。健康失败不会自动重启正在运行的容器、取消模型调用或授权重试。

离线诊断已有控制快照：

```bash
python scripts/learning_worker.py check --snapshot PRIVATE_STATUS.json --node learn@HOST
```

只读取最多65536字节，拒绝重复JSON键/非有限数字/坏结构；输出`SNAPSHOT_LEARNING_WORKER_READY/NOT_READY`，**绝不是live通过**。输入须为受信本地普通文件，可能含敏感broker信息，不提交或公开原始快照。

## 独立启用/回滚前置

1. 当前所有22项隔离MySQL在本地仍未运行；执行最新schema的空库/迁移/model-diff与真实HTTP会话、重试/取消/ACK/账本故障门禁。
2. 在明确可丢弃的隔离环境，使用实际候选镜像/Compose验证：同卷RW→RO可读、worker写被内核拒绝、错UID/权限/缺卷退出、重启保留；不要用生产卷做破坏性验证。
3. 实际Redis/prefork验证：注册及唯一队列、重复投递、soft/hard、broker/进程失联、未决预留不重付、恢复收敛、readiness失败。当前Redis仍是既有配置，本层不提供新broker持久性或防驱逐保证。
4. 验证cgroup实际CPU/RAM/PIDs、冷启动/最大允许样本/历史扫描/健康检查/回收的峰值和长时行为。监控parent/child PSS、memory.events/oom_kill、队列延迟及数据库压力；container restart计数不证明child没OOM。
5. [企业初始分析迁LLM](startup-analysis.md)已本地完成；其它refresh/扫描请求可靠性、实际服务等M3前置仍待完成。学习消息现在带派发键，旧单参数消息不被新worker执行，缺dispatch状态的旧active也不自动补权。另取部署授权、备份、当前镜像回退点；协调停止所有旧付费调用方。不能混用新旧预算/历史/派发协议。
6. 之后才允许显式启用profile和标记、协调重建web/beat/worker_learn，并复查全部实际镜像。保留旧两worker限制及私有卷层，不误重建DB/Redis。

回退先停止接收新学习委托并处理/排空在途工作，再停止学习consumer；不删卷、表、预留或审计，不通过schema downgrade恢复。不要在仍有已授权任务时把整个worker强杀或把已准入调用当免费。旧应用回滚的兼容限制仍按[预算说明](llm-budget-accounting.md)及[学习说明](crawl-learning.md)处理。
