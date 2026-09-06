# OVH 首批 M0 修复：SQL 验证与受控发布

## 授权与范围
- 用户允许登录其 OVH 部署环境验证 SQL，验证完成可提交部署；后续开发必须 TDD。
- 本次发布仅现有首批 M0 修复，不把未实现的 M0.5/schema/Agent 标为完成。
- 单写者主会话，不使用子代理。验证接口沿用已确认的 Alembic upgrade、Crawler.run、HTTP/Compose 公共接口。
- 旧 2026-04-27 OVH 文档仅作为主机/路径线索，不执行安装、旧 dump 恢复、重新建管理员、Caddy 重配或 down -v。
- 预期主机 ubuntu@149.56.142.99，目录 /home/ubuntu/FSourceInsight；真实状态先核对，不将旧文档当现状。
- 密钥仅允许既有服务/部署工具在运行时使用，不读取或输出密钥值；备份仅服务器内保存，不查看内容或进 Git。

## 阶段与停止条件
1. [complete] 只读盘点：SSH 主机校验、repo/ref/dirty 状态、Docker/Compose、服务端口、可用内存/磁盘、MySQL 版本/当前迁移和相关列类型。
   - SSH/权限/工作区/资源与预期不符先更新计划。禁止关闭 StrictHostKeyChecking、覆盖远端修改或影响 ai-router。
2. [complete] 隔离 MySQL 验证：优先专用临时 MySQL 容器（无宿主端口、独立卷/网络、限资源），使用已在服务器存在的 MySQL 镜像，不把 test fixture 指向业务库。
   - 如资源不足，仅在确认权限边界后创建独立临时数据库和专用用户，绝不 drop/create 业务库。
   - 空库至 head；人造旧数据至 head；保持 usage 旧类型与新任务值；model diff；BaseCrawler 重复/回滚/并发边界。
   - 新发现缺陷先写失败回归，再修改并复跑；测试不得连接真实 HTTP/SMTP/LLM。
3. [in_progress] 发布准备：本地完整回归、检查本批 diff 与敏感文件排除、明确源代码 commit/ref、只提交本批文件并正常推送（不 force）。
   - 备份业务库至服务器受限目录，检查命令退出、gzip 完整性/大小，不查看数据；保存旧 ref/镜像 ID/配置哈希。
   - 不执行通用 scripts/deploy.sh 或 restore_db.sh，不导入仓库旧 dump。
4. [pending] 受控发布：按确认的 Caddy 三层配置构建应用镜像；保留当前 MySQL/Redis/Caddy/ai-router。
   - 先构建，不先停服务。需要短暂停 beat/应用 worker 及数据库 DDL 锁时先说明窗口；长耗时/影响范围不明先询问。
   - 前向迁移 c821b4f7d901；只重建 web/worker/worker_fast/beat，不重启数据库，不修改公开入口。
   - 新凭证会话格式会使已有用户重新登录；无密码用户保留记录但禁止仅凭邮箱管理。
5. [pending] 冒烟/记录：health、首页/登录/匿名受保护页面、端口、任务注册/进程状态、迁移版本；不触发真实爬取/LLM/邮件。
   - 失败回到保留的应用镜像/代码，保留 expand-only VARCHAR(50)；禁止缩回旧 Enum、down -v 或删业务数据。
   - 临时资源按本次创建的精确身份清理；不使用 prune 或通配删除。

## 当前状态
- 本地 HEAD bf9cc61，18 个 tracked 文件修改及新增审查/测试/迁移/CI资料；未暂存/提交。
- 原有本地 49 项回归通过；MySQL 实机尚待本次验证。
- 首次连接 `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes ... ubuntu@149.56.142.99` 返回 exit 255：`Permission denied (publickey)`，远程脚本未执行、服务器无改动。下一步仅核对本机 SSH 别名/有效身份配置及 ssh-agent 可用性，不读取私钥、不关闭主机校验；若无可用身份则向用户确认。
- 被动 SSH 配置检查发现同一主机已有别名 `france-vps`（ubuntu@149.56.142.99，指定 ovh_ed25519）；直接 IP 未匹配该 IdentityFile。按此明确配置用别名重试，保留 BatchMode 与 StrictHostKeyChecking，不尝试其他主机/用户。
- 别名 SSH 成功：vps-babefee9 / ubuntu；远端 master@bf9cc61，工作区干净。Docker 29.4.1、Compose 5.1.3，FSourceInsight 6 服务正常，web 仅 127.0.0.1:8800；同机另有多项目，不改其服务。
- 资源实测：可用内存约 3.6 GiB、磁盘 15 GiB。隔离 MySQL 限 768 MiB/1 CPU、测试应用限 512 MiB/1 CPU；不暴露宿主端口，用当前已部署镜像，先验证后清理测试资源再构建。
- 只读 SQL 确認：MySQL 8.0.46、revision fd3132082a6b；task_type 已是 varchar(50) NOT NULL，company JSON/counter 类型正确；usage 约 16 万行。先更新计划：新增已是目标类型的迁移幂等测试，避免线上无意义 ALTER；在 isolated DB red 后实现在线类型检查，离线 DDL 仍保留升级语句。
- 隔离验证 7/7 通过，生产只读 model diff=0。本地49通过/7远程专用skip；CI已补MySQL service job。已正确VARCHAR不重写的回归先red后green。
- 测试目录 /home/ubuntu/fsi-m0-verify.EYVS00；资源 fsi-m0-20260906100910-net/data/mysql。传输源包遇到 macOS xattr 警告但内容可读；后续用无扩展元数据打包，不改服务器文件兼容设置。
- 正式构建完成后，在候选运行镜像上再跑同一组 MySQL 测试/模板和匿名权限检查；依赖无锁定，不能只用旧镜像验证就断定新镜像一致。
- 提交前远程 ref 核对发现 GitHub master 实际为 93830196d85f932e08ef73d914de760e839c6776，并非本地/生产 bf9cc61。先记录偏差：暂停提交/发布，fetch 后只读检查新增提交及与本批重叠；不 force push、不 reset、不把未经复核的远程改动带到生产。必要时向用户确认集成/发布范围。
- 已复核远程新增仅 README 署名增加 LiRuxin，不涉及本批代码/迁移且无重叠；以 ff-only 接入保留作者改动，再提交本批（不会重写历史）。测试业务基线仍等价于 bf9cc61。
- 已将 TDD 规则写入 CLAUDE.md。后续开发仍按 TDD 和动态爬虫分阶段计划推进。
