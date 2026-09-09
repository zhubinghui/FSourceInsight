# 可选：后台原始证据持久卷

M2-A/B1/B2a仅保存候选、preview与回放；不是审批/自动schema路由。默认preview不保留原文。

生产需要原文保留时，在prod（以及使用系统Caddy时的caddy层）之后显式加`docker-compose.evidence.yml`。它只给web挂载外部卷`fsourceinsight_crawl_evidence_data`到`/var/lib/fsource-evidence`，并设置`CRAWL_EVIDENCE_DIR`；worker/worker_fast/beat不需要访问原文。

该卷必须提前受控建立：核对实际web镜像UID、确认新卷为空后，将根目录设为该UID拥有/0700；已有目录先核对数据/所有权，不覆盖、不为通过检查而放宽权限。配置文件不会自动创建external卷。不要将代码目录、static、备份目录或混有其他文件的卷用作证据库，不向nginx/Caddy/浏览器沙箱共享。

```bash
# 在已初始化并验证证据卷的部署中，使用以下层顺序。
# 不要遗漏evidence层后重新创建web，否则证据功能将禁用（卷本身仍保留）。
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.caddy.yml -f docker-compose.evidence.yml \
  up -d --no-deps --no-build web worker worker_fast beat
```

后台仍须管理员明确填写本次主机许可/质量标准并勾选保留。文件0600，最多6文档/2MiB body、3MiB bundle、32文件/64MiB总额，24小时后不可回放。到期不是即时物理删除：下一次保留preview或后台“Clean expired evidence (all sources)”才清理过期文件/孤儿。没有清理cron，也不能据hash/回放ready直接审批。

原文敏感且未加密。共享目录/flock只为同一主机受信POSIX文件系统提供有界存储，不是分布式锁/OS沙箱。运行UID/卷/文件系统变化后须重新验收权限、锁、fsync与重启持久性。

应用回滚用原四镜像并保留扩展数据库表及证据卷，不downgrade、删卷或整库恢复。M1旧应用不需要此卷；切回旧层顺序即可，但卷中的原文仍需受控保留/清理。
