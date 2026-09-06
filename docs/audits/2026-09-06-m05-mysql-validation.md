# M0.5 隔离 MySQL 实机验收

## 结论

后续发布更新：用户另行授权后已提交部署6451b36/d472，实际新候选再次通过验收，见 [发布记录](2026-09-06-m05-release.md)。下面保留此前独立隔离验收的时间/范围。

**10 项全部实跑通过，两轮分别耗时 15.672 / 15.639 秒，exit=0、无 skip。**

- 执行日期：2026-09-06，约13:13–13:18 UTC；主机 `france-vps` / `vps-babefee9`。
- 用户确认继续隔离验收后执行；主会话单写者。未提交/推送/部署 M0.5，未迁移生产库或重启现有服务。
- [M0.5 本地实施记录](2026-09-06-m05-implementation.md)中的“MySQL待验收”历史缺口已由此次实测补齐。
- 本批代码/验收完成不代表 Agent 已实现，也不代表并发硬预算、lease/outbox、Safe Fetch、断路器Redis可靠性等后续风险已消除。

## 验证对象

| 项目 | 实际值 |
|---|---|
| 本地/服务器 Git HEAD | `d91863fcc0f0a9cb3e6d0302ed834847c2ee4d5e` |
| 测试源代码 | 本地未提交 M0.5 工作区的 allowlist 快照，156 文件 |
| 快照 SHA256 | `6dacabbfd75b7174dfd21505765b62e02db9c663f355fa528438d1a1c50981ba` |
| 文件清单 SHA256 | `9560adbac223698a76e4b65dc1866fb4ca5429452dd1148537d2d9e2265c1796` |
| MySQL | 8.0.46，已有镜像 `sha256:d0304ed9fdb64a3f6c7ad11a5fb4f13abfc10e6dfa3f288d652e7320c34df7f9` |
| 测试依赖镜像 | 当前web镜像 `sha256:892a51169dacb03bc66549ba04546ac057f9ae77e92aa096150898b9a7e40c8f`，只读挂载新代码覆盖 `/app` |
| Python / Flask | 3.12.14 / 3.1.3 |
| SQLAlchemy / Alembic / PyMySQL | 2.0.52 / 1.19.2 / 1.2.0 |
| LiteLLM | 1.100.0（模型调用全部 mock） |
| 新迁移 head | `d472ac9e6102`，只在隔离库执行 |

未构建新候选镜像，未拉取镜像/安装依赖。**未来真正发布重新构建的候选镜像仍需复验**，不能把此处源码覆盖测试说成候选镜像已部署。

## 实跑用例

测试入口：`python -m unittest discover -s tests/integration -v`。

| 用例 | 结果 |
|---|---|
| 空库完整迁移到head、Alembic model comparison零差异 | 通过 |
| 已正确VARCHAR的用量列不重复ALTER | 通过 |
| 合法历史JSON、企业失败计数回填 | 通过 |
| 旧Enum用量/FK/费用保留，新增任务类型可写 | 通过 |
| 路由扩展后既有model/tasks保留，role=primary/priority=100 | 通过（包含于上一项） |
| 爬虫重复/重放不重复入库 | 通过 |
| 两个爬虫事务竞争相同身份 | 通过 |
| 爬虫晚期写失败整批回滚并结束日志 | 通过 |
| LLM独立账本不被业务父行写锁阻塞，重放不重复应用 | 通过 |
| LLM最终分类写失败：Article/Company/关系回滚，用量保留，重试成功 | 通过 |
| 两个LLM消费者同时收集，最终只保留一组业务结果/关系 | 通过 |

共10个 unittest 方法；路由历史保持断言属于旧Enum升级用例，不额外计数。并发用例使用屏障制造实际竞争，LLM测试 MySQL session 锁等待上限3秒，未跳过断言或接受部分提交。重复消费者可能仍重复付费，当前验证的是最终业务应用幂等。

清理后本地完整回归再次 **131 passed / 10 skipped**（20.59秒；10项skip是本地未启用MySQL，实机结果如上独立记录）。156个源文件逐一SHA256仍与已验证快照相同；下载的测试日志哈希、文档链接/围栏、`git diff --check`通过。Git HEAD未变、无暂存修改。

## 隔离与清理

- 独立资源前缀：`fsi-m05-20260906131354`；专用 internal Docker 网络，独立 MySQL 卷，无宿主端口，不加入业务网络。
- MySQL限768MiB/1CPU；测试runner限512MiB/1CPU、128 PIDs、UID/GID1000、只读rootfs/源码、cap-drop ALL/no-new-privileges，仅临时 `/tmp` 可写。
- 临时库固定 `m0-mysql/fsource_m0_validation`，fixture同时要求 `FSI_DESTRUCTIVE_TESTS=1`；DNS/socket仅允许该实例3306。未接入生产数据库/Redis/LLM凭据。
- 本次生成的测试密码通过受限文件使用，从不打印。`.env`、Git、dump、私钥未进入源归档；无真实爬取/LLM/邮件。
- 前后所有原有运行容器的 **ID、StartedAt、RestartCount逐行相同**。包括FSourceInsight MySQL/Redis/应用及同机其他Docker项目；未执行任何ai-router服务操作。
- 13:18 UTC按精确资源标签逐一删除两个测试runner、临时MySQL、卷和网络，删除测试临时目录及凭据。没有执行prune、业务卷删除、恢复旧dump或应用重启。
- 服务器checkout仍干净d91863f；公网 `/health` 返回 database/redis/status 均ok。

## 首次基础设施偏差（保留失败证据）

第一次runner在测试收集前exit1：

```text
ImportError: Start directory is not importable: 'tests/integration'
```

归档解压目录为ubuntu拥有的700/文件600；cap-drop ALL的root不再能绕过DAC读取它们。先更新计划并核对挂载/UID/权限，再将runner改为目录拥有者1000:1000；不放宽目录、不移除cap-drop/只读/网络隔离。原业务源码和测试断言没有修改。

第二次正确收集10项并全部通过，随后再次完整复跑10项通过。首次exit1不是业务red，也不是验收通过。

## 证据保存

- 服务器无敏感信息归档：`/home/ubuntu/fsourceinsight-validation/m05-20260906131354`（受限权限）。
- 包含source.tar.gz、SOURCE_SHA256SUMS、版本信息、首失败及两轮日志、exit文件、前后容器身份、删除记录和测试脚本；**不含runner.env/mysql-root.secret**。
- 首次成功日志 `tests-v2.log` SHA256：`55ccde3d13e37992c6d31356bfc50cd4cd53cfe5cad2f424bb8ae438b7f0b93c`。
- 复跑累计日志 `tests-rerun.log` SHA256：`dd4697b075097e34a7fde620aea679e85656c2958fb50ed7589fcf14bd3bd9fc`。
- 执行计划：[M0.5 MySQL验收](../superpowers/plans/2026-09-06-m05-mysql-validation.md)。

## 后续

本次隔离验收结束时M0.5尚未提交/部署；随后已获授权并完成候选镜像/备份/回滚门禁，发布结果见上方链接。下一开发阶段为M1：先建立新闻输出/声明式schema契约，再Safe Fetch、确定性抽取器与质量门禁。
