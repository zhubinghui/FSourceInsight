# M1 后续：隔离部署测试准备（原方案未执行）

> 用户随后授权直接切生产，当前执行以[M1受控发布](2026-09-07-m1-release.md)为准。必要门禁并入发布，以下独立验证计划仅保留历史/后续检查范围，不再是阻塞上线的单独阶段。

## 前提与授权边界

- 用户要求整个M1完成后再做部署测试。[M1本地交付](../../audits/2026-09-07-m1-local-completion.md)已完成：459通过，12项MySQL专用skip不是通过。
- **本文件是下一阶段计划，本轮未SSH、构建候选、创建远端资源、运行CI或迁移生产。**
- 测试目标是新的完整M1候选，不是拿M0.5历史镜像/结果背书。生产切换、提交推送与发布步骤另行明确；不能把“部署测试”理解为自动切换生产。
- 单写者；保留本地M1 dirty文件。任何环境/权限/断言偏差先记录计划，不reset/stash，不重跑安装或dump恢复。

## 1. 只读预检与固定候选输入

- 本地记录HEAD/branch、完整改动清单与源码manifest；当前基线f3644ca，不假称已有M1 commit/CI。
- 后续访问OVH沿用`france-vps`、BatchMode和StrictHostKeyChecking；不读私钥/`.env`/备份内容，不输出凭据。
- 重新核对远端checkout、当前四应用/数据库/Redis/其他项目容器身份与启动时间、公网health、磁盘/RAM和Docker/Compose版本；历史M0.5数据只作参考。
- 只传allowlist源码/测试/迁移/requirements/构建文件，排除env/Git/dump/原始网页证据；固定摘要。候选标签和临时目录使用本轮唯一ID，不覆盖现有标签/checkout。
- 使用完整新构建候选；不得把覆盖旧镜像app源码称为最终候选验收。资源不足时暂停，不停止其他项目腾资源。

## 2. 独立MySQL与候选运行

- 独立internal网络、专用卷、MySQL8.0.x；无宿主端口、不连接生产数据或broker，禁止生产凭据/模型key/SMTP。
- 初始资源参考MySQL768MiB/1CPU、runner512MiB/1CPU；以预检容量为准，变更先记录。构建资源也需评估，不能宣称Docker BuildKit天然服从这些runner限额。
- runner只读rootfs、cap-drop、仅临时/tmp写入；按候选真实UID/文件权限运行，不复用历史UID假设，也不靠开放根目录权限掩盖失败。
- 专用数据库固定`m0-mysql/fsource_m0_validation`，只有`FSI_DESTRUCTIVE_TESTS=1`才运行已有破坏性fixture。测试清库严格限定这个隔离目标，绝不使用生产URL。
- web/worker真实候选分别运行`python -m unittest discover -s tests/integration -v`：目标12项，包括新引擎JSON/去重和最后CrawlLog失败回滚；空库→e6、旧Enum/旧Article→e6、旧数据与配置保持、model diff0。
- 所有HTTP仍走合成bootstrap，LLM/邮件仍mock。候选内复跑完整离线pytest，验证新版requests/urllib3及parser依赖；记录实际Python/依赖版本，不仅核对requirements范围。
- 验证`d472ac9e6102 → e6a91f4c820d`仅新增三个可空列；历史SQL NULL不变，旧应用可读扩展后的库。实际MySQL DDL路径、metadata lock与表结构限制需核对，SQLite/离线SQL不能代替。

## 3. Linux worker、交付与网络边界

- 在不连生产队列的独立Celery配置下验收prefork中两个helper创建/退出/超时回收，不改变父worker信号；检查PID/FD/内存无持续增长。
- 检查四候选都包含新Python helper和CLI，依赖API满足SafeFetch要求；镜像中无env/Git/dump，原始snapshot文件不进入镜像。
- 模板40个编译、匿名CSRF/权限、news/API新标记与旧NULL兼容。手工CLI默认preview、--apply只指向测试DB；验证snapshot 0600/不覆盖旧文件/回放无HTTP及partial退出码。
- 真实DNS/socket/TLS/证书链、受控慢响应和重定向需要独立网络试验；不得用本地合成TLS当已完成。若安排公开站点小样本，先列出允许域名/请求额度/robots与预期，不访问登录、付费墙、验证码，不调用真实LLM或邮件。
- 整理15个自定义source及startup_discovery未迁移清单；不自动把候选接入所有生产来源或发布任何schema。

## 4. 证据、清理与发布门禁

- 记录候选镜像ID、源码摘要、所有命令/exit code、12项MySQL与完整本地结果、失败/复跑记录和未覆盖项；新CI若未运行明确标注。
- 精确删除本轮临时容器/卷/internal网络/凭据/辅助文件，不用global prune或down -v。归档不含凭据的证据。
- 复核所有原有服务身份/启动时间与health不变；隔离测试通过不自动启动生产发布。
- 若后续授权发布：先固定提交/CI与真正候选，备份并记录可回滚的**当前**四镜像/ref；停beat、排空worker、warm-stop，有限metadata lock等待升级e6，再切四应用并做worker/health/匿名CSRF门禁。
- 回滚优先旧四应用，保留可空扩展列；不downgrade、不整库覆盖，不把gzip完整性称为恢复演练。DDL与源码回滚风险独立记录。

## 当前状态

1. [pending] 只读预检、固定输入与资源批准。
2. [pending] 真正候选、隔离MySQL12项及完整离线回归。
3. [pending] Linux prefork/交付/受控真实网络验收。
4. [pending] 证据归档与精确清理；生产切换未授权执行。
