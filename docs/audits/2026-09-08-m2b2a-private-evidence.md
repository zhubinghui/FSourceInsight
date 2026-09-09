# M2-B2a：私有原始证据与后台回放（本地完成）

后续合入：2026-09-09，90c94b6已推送master，CI离线574/14与独立MySQL14/14通过；[合入记录](../superpowers/plans/2026-09-08-m2-mainline-integration.md)。以下保留开发阶段的原始测试/未部署范围。

## 结论与范围

在M2-A/B1之上完成“明确勾选保留原文 → 私有文件保存 → 报告核验可用性 → 离线重新抽取 → 过期清理”。这是B2的证据切片，**不是完整B2或M2完成**；持久policy、独立验证、人工审批/active/previous/CAS、可靠运行/调度仍待做。

仍为master@4477cfd上的未提交改动。没有提交/推送/SSH/部署、真实新闻来源、付费模型或邮件，也没有使用子代理。生产没有变化。

## 后台操作

1. 候选版本页原有主机许可/质量标准表单新增默认不勾选的`Retain private raw evidence for 24 hours`。
2. 勾选后通过真正M1引擎抓取；原始body/准确URL只写部署方明确配置的私有目录，DB JSON报告保存随机引用、SHA256、长度、截止时间与capture_id。
3. GET报告显示`available / expired / unavailable / not_retained`，核验文件但不联网、不执行parser。只展示转义后的有限文章样本，不下载/内联执行原HTML。
4. 证据可用且配置未过期时可POST `Replay without network or ingestion`：真实M1重新抽取，不复用缓存样本、不写Article/LLM/候选状态，也不伪造新的持久报告ID。
5. Crawl config页的`Clean expired evidence (all sources)`清理专用目录所有来源的过期bundle，包括孤儿；不删除未过期文件。

匿名/普通用户不可使用或查看这些操作，POST保留CSRF和严格单值表单。路径/key/许可/recipe/结果不能由回放请求指定。页面仍no-store/no-referrer，外链noopener/noreferrer。

## 私有存储与边界

- [实现](../../app/crawlers/_evidence.py)只支持受信任的本地POSIX文件系统；`CRAWL_EVIDENCE_DIR`默认未设置，且需专用目录已存在、在checkout外、当前应用UID拥有、0700。不会自动mkdir/chmod、不会放宽现有权限或从recipe接受路径。
- 随机文件0600、独占创建、不覆盖；拒绝symlink、硬链接、FIFO/其他非普通文件。dirfd相对操作及严格key格式防止引用路径穿越。目录中的未知文件使操作拒绝，不全局扫描/清除宿主文件。
- 6文档/单body512KiB/合计body2MiB，单bundle JSON最多3MiB；全目录最多32文件/64MiB，非阻塞flock串行检查/写入与清理。锁忙或满额失败，不自动驱逐未过期证据。
- 24小时是**可用期限**；文件在下一次保存或显式清理时按mtime清理，而非到期即时物理消失。未运行清理时原文仍在磁盘，但过期引用不能回放。没有清理cron/远端对象存储/跨机器锁保证。
- JSON/base64不是加密。目录必须仅用于此功能、不由静态服务器公开，可信祖先目录由运维维护；0700/0600不是对同UID/特权进程的安全沙箱。当前M1 parser也仍不是OS文件系统沙箱。
- 文件先写出并fsync，然后DB保存报告引用；没有跨文件系统/DB原子事务。fsync/SQL失败或崩溃可能留下有界孤儿，DB commit结果不确定时不删文件，避免误删实际已提交证据；过期清理回收。
- B1每候选20报告仍保留；裁剪报告可暂留原始bundle，仍受全目录额度/24h清理约束。额度满时可能已完成抓取但无法保存证据，返回固定503；文件/DB耗时不在引擎20秒预算内。
- 没有取得任何成功文档时，不伪造空证据：勾选保留会503且不保存报告；不勾选仍可使用B1查看原引擎失败报告。原始证据失败不会被当成可审批。

## 绑定与失效

文件与报告核对source/version/generation/source指纹/recipe/engine/可信policy/quality，另含独立服务端capture_id；同一候选的两次相同配置preview也不能仅替换reference互串证据。

整体SHA256只用于一致性，不认证来源或授权。读取还检查严格JSON（重复key/非标准常量/未知字段拒绝）、数量/大小、文档URL范围、请求/最终URL对应、单页body hash/长度及FetchObservation契约。文件不能提高许可或降低当前系统标准。

回放前复制输入并释放数据库Session，后续再次检查source/generation/engine/policy/证据；过程中配置变化或期限届满返回409。partial捕获的缺页由M1回放返回no_evidence，不联网补齐。回放ready不等于完整来源覆盖、独立留出验证、事实认证或批准。

旧B1报告没有原文，不回填伪引用。没有新增表/迁移；本地head仍`b6c2a4d9e710`。

## TDD与验收

[49个新HTTP用例](../../tests/test_web/test_crawl_evidence.py)通过，全部使用真实引擎/抽取/质量、合成DNS/socket/TLS bootstrap、实际私有文件系统。文件、SQL、时间、进程边界用于故障注入，不mock自家的存储或引擎。

真实red后修复：
- 缺保留/回放控件；满32文件仍保存；过宽权限/硬链接仍available。
- 同候选两次捕获reference可互换；引用`../`仍尝试打开目录外文件。
- 零文档仍声称保留；整体checksum匹配但单页hash/URL/JSON结构错误仍available。
- 缺清理操作；symlink loop泄露带路径RuntimeError。

直接通过既有实现的验证：默认不保存、坏目录/缺失/改写/FIFO/超大文件、64MiB额度及清理后再次核对、锁忙、fsync/SQL失败与孤儿回收、过期/运行中失效、partial缺页不联网、权限/CSRF/跨版本/伪造控制字段。保留这些保护，不冒充每项都曾出现新业务red。

测试driver纠正：新增checkbox后按真实浏览器省略未勾选/disabled input；同步原B1和MySQL HTTP driver，不把误提交checkbox当产品要求。

最终：**574 passed / 14 MySQL专用skip / 3453 warnings，147.67秒**。

- 158 Python AST、43模板、指定flake8和diff检查通过，单head b6。
- MySQL既有HTTP用例扩展了私有目录、引用JSON回读及回放；**本轮14项仍未在独立MySQL运行**，不能借M1历史成功证明。
- 本地日志：`/tmp/fsi-m2b2a-tests.log`。没有视觉浏览器E2E、Linux共享卷多worker/压力/崩溃恢复、部署容量或生产验证声明。

## 下一步与部署前提

按[细化计划](../superpowers/plans/2026-09-08-m2b2-evidence.md)继续B2b持久policy、独立验证与人工审批/CAS。需要区分短期原始证据和长期发布审计，不能让捕获成功自动发布规则。

未来另行授权部署时，须提供归应用UID所有的私有持久卷、验证POSIX锁/fsync/额度与恢复、安排过期清理；当前没有改Compose或创建生产目录。不要直接把本地临时测试目录复制上生产，也不要提前部署缺可靠运行/调度的中间状态。
