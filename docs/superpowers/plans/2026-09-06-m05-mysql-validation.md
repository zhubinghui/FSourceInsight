# M0.5 隔离 MySQL 验收（续轮）

## 授权与边界
- 用户在“下一步先完成隔离 MySQL 验收”后确认“OK，继续”。本轮只做远端隔离验收和必要的 TDD 修复，**不提交/部署 M0.5，不迁移生产库，不重启线上服务**。
- 主会话单写者，不使用子代理。沿用 `france-vps` SSH 别名、BatchMode、StrictHostKeyChecking；不读 `.env`/私钥/数据库备份。
- 本地 HEAD `d91863fcc0f0a9cb3e6d0302ed834847c2ee4d5e`，工作区是上一轮 M0.5 未提交代码。保留这些修改，不 reset/stash/覆盖。
- 生产预期 checkout d91863f，运行首批858a14b镜像，schema c821；本轮不执行生产数据库命令。旧部署脚本/备份只作历史参考，不重跑。

## 执行步骤
1. [complete] 2026-09-06 13:11Z盘点：vps-babefee9/ubuntu，repo干净d91863f；可用RAM3981MiB、磁盘22GiB。现有web镜像892a5116…、MySQL镜像d0304ed9…，所有服务正常。无需拉镜像或重启服务。
2. [complete] 在 /home/ubuntu/fsi-m05-verify.f0f48N 独立mode700目录传输156文件源快照，SHA256=6dacabbfd75b7174dfd21505765b62e02db9c663f355fa528438d1a1c50981ba，逐文件核对通过。使用 allowlist 源快照（app、migrations、tests、celery_app.py），排除 .env/.git/dump；生成文件 SHA256 清单，保留可核对版本证据。
3. [complete] 资源前缀fsi-m05-20260906131354；用已存在的 MySQL8 镜像、独立 internal 网络/专用卷启动临时服务，无宿主端口、不加入业务网络，精确唯一前缀和 label。MySQL 最多768MiB/1CPU，测试进程512MiB/1CPU。使用仅本次生成的临时密码，不输出值。
4. [complete] v2测试runner以UID1000运行，10/10实跑通过（15.672秒、exit0），MySQL8.0.46，Python3.12.14/SQLAlchemy2.0.52/Alembic1.19.2/LiteLLM1.100.0。以现有应用镜像依赖 + 只读源快照跑 `python -m unittest discover -s tests/integration -v`；仅允许 m0-mysql/fsource_m0_validation，FSI_DESTRUCTIVE_TESTS=1。10项须实跑，包括新迁移model diff、LLM独立账本/FK、最终写失败回滚、重复消费者。
5. [complete] 首次基础设施权限失败已保留日志并修正，未改业务代码/测试断言。如失败，保留准确日志/exit code；区分fixture、基础设施和业务错误，先记录偏差，再最小修复并复跑。不得放宽断言接受部分业务提交；不把容器退出0误报为tests通过。
6. [complete] 完整复跑10/10（15.639秒）通过；原有容器ID/StartedAt/RestartCount逐行相同，health正常。已按标签删除全部临时资源/凭据，日志和源快照保存至 /home/ubuntu/fsourceinsight-validation/m05-20260906131354；本地全套复跑结果见验收报告。

## 偏差与处理
- 首次测试容器exit1，unittest尚未收集：`ImportError: Start directory is not importable: 'tests/integration'`。实测目录700/文件600归ubuntu(1000)所有，cap-drop ALL的root无法读取。改runner为1000:1000后10项通过；保留cap-drop、只读挂载、目录权限和网络隔离，不将基础设施失败算业务red。

## 证据与限制
- 上轮本地131 passed/10 skipped；本轮新代码MySQL两次10/10通过。正式证据见 [实机验收记录](../../audits/2026-09-06-m05-mysql-validation.md)。
- 本轮是源快照在已部署依赖镜像中的验证，不等于未来重新构建候选镜像验证；未来发布仍需候选复验/备份/回滚门禁。
- 不触发真实爬取、LLM或邮件。测试socket限制只允许临时MySQL；没有生产数据库、Redis或LLM凭据接入。
- 预算硬预留、lease/outbox、Redis故障/半开探针及Safe Fetch仍不在此次验收完成声明内。
