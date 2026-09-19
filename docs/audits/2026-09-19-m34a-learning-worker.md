# M3.4a：可选学习worker及运行门禁（本地）

**配置/协议切片完成，不是实机服务、容量、部署或整个M3完成。** 基线`master@8bf2563`未变，保留此前全部M3未提交改动；主会话，无子代理、SSH、生产、真实新闻/付费模型/SMTP或提交部署。本轮没有DDL，head保持`f8b64d2c901e`。

## 改动

- `docker-compose.learning.yml`：在prod/(caddy)/evidence之后显式使用；新`worker_learn`仅在`crawl-learning` profile或明确指定服务时才启动。web/beat/新worker共享默认0的启用标记，入口另查启用状态。没有给模型/来源自动授权，旧两worker命令/资源不改。
- 同一external证据卷web RW、学习worker RO/nocopy；其它worker/beat/代理无原文挂载。读取路径复用既有0700/当前UID和逐文件0600/绑定/时效检查，不复制、chown或建卷。读路径不依赖写锁；解析helper仍非OS/文件系统沙箱。
- 新worker为prefork1、prefetch1、完成50个Celery任务或RSS高水位393216KiB后回收；soft180/hard195。初始容器1GiB/1CPU/PIDs64、根RO、64MiB tmpfs、init、drop ALL/no-new-privileges，warm-stop210秒及最多3次失败重启。这些只是待实测初值，不是容量结论。
- `scripts/learning_worker.py run`：只接受已审查的完整Celery命令；检查启用、只读私有目录、当前唯一schema head后exec，不先修配置/迁移/授予权限。
- `check`：检查上述local条件后只发指定learn节点的Celery控制查询，核对注册、实际唯一消费队列/routing key/exchange、prefork进程/prefetch/回收/timeout。输出固定状态，不输出回复/异常私有数据，不发业务任务。
- `check --snapshot`只验证给定控制协议形状，最大65536字节并拒绝重复键/坏JSON，输出明确SNAPSHOT状态；不接触DB/worker，不当live证明。

## 确认的边界

健康检查不是模型定价/可用性、来源授权、原始证据完整性、全系统唯一worker或付费安全批准。schema head标记不替代schema diff。不同空目录也可能满足local权限，仍须验证实际卷绑定及每次文件/DB绑定。

实际消费者若在长任务内，recover也可能排队；soft/hard并不能取消已准入供应商调用。预留、冷却、原期限和历史沿用M3.1/2c，不解锁不确定费用、不自动接管 paid work。Docker健康检查有20秒timeout，但独立CLI的数据库/控制读取不是全程硬deadline；健康失败不自动重启容器或授权重试。

当前broker仍用既有Redis配置，本层没有新的防驱逐/持久性保证；模型/企业发现队列拆分及完整恢复仍待完成。1GiB需要同时容纳parent、child、helper、health CLI和tmpfs，不能借09-10历史容量快照证明现在够用。

## TDD与实际证据

沿用已确认的运维CLI/Compose/注册与真实Admin任务验收，不增加测试业务API、不mock内部预算/引擎。

新增**46项离线**：
- `tests/test_ops/test_learning_worker.py`：5项真实Compose离线merge，含Caddy/开关组合、未选profile不启动、RW/RO同external卷、私有端口/挂载、资源/命令/health边界及旧worker保留。
- `tests/test_ops/test_learning_worker_cli.py`：40项实际CLI/runpy入口，覆盖snapshot/live分离、真实DB只读head检查、OS mount/exec及Celery控制边界替身；缺任务/错节点/队列/池/prefetch/回收/timeout、目录权限/缺失/symlink/RW、开关/旧schema、坏快照/隐私/命令拒绝。
- `tests/test_web/test_learning_worker_evidence.py`：1项真实Admin保留→生产学习任务→候选。只在外部os.open边界拒绝证据写，读取成功且原文件内容/mtime不变；不是实际内核RO mount证明。

先红后绿：缺overlay、缺CLI、缺live检查、缺run入口。既有安全路径的后续拒绝回归直接通过，不冒称每项都有独立产品red。

实测偏差已先记计划：本地Docker Compose **5.1.0**在service pids_limit和deploy limits未同时声明时拒绝merge；显式两处64解决，未去掉限制。CPU的JSON输出为数值，修正测试期待，未把序列化差异当业务缺陷。

- 相关旧新运维子集：58 passed / 42 warnings / 6.20秒。
- **最终全套：924 passed / 19 dedicated-MySQL skipped / 8869 warnings / 481.94秒**。完整日志`/tmp/fsi-m3-izjIZv/m34a-full-01.log`；faulthandler30秒未触发。
- 静态：**209 Python AST、48 Jinja模板**、单head、指定flake8/diff通过；既有Docker构建allowlist测试确认新scripts/*.py在镜像复制范围内。
- Compose仅`config`，`--env-file /dev/null --no-env-resolution`且清理进程环境，不读取项目.env、不联系daemon，不导出真实凭据。

本机仍无Docker socket及mysqld/redis-server。**19项MySQL未运行；没有实际容器build/start、同卷RO/UID/内核写拒绝、实际prefork参数/超时/回收、broker/进程故障或容量通过记录。** Celery协议来自安装版本接口；外部SDK和mount标记替身不是服务证据。

## 后续

操作说明：[学习worker](../ops/learning-worker.md)。保留M3未完成标记：实际MySQL/Redis/进程与资源容量门禁、企业发现迁LLM队列及补偿、完整可靠恢复、通用RSS/多列表/分页留出和全系统暴露覆盖仍待办；M2人工审批/active/previous/日常schema路由另列。

本轮没有启用学习、添加清理cron、执行生产配置、替换现有容器、写Article/派文章LLM或发布规则。任何真实服务验证、模型/网页调用与部署仍需按既定隔离和独立授权处理。
