# M2-A/B1/B2a 当前成果受控生产发布

## 新授权与计划调整

用户在全部成果合入master后明确要求“部署一下生产”。允许本轮发布所需的提交/推送、SSH、备份、隔离候选验证、增量迁移及四应用切换。**这取代早期“完整M2后才部署”的安排，但只上线已完成A/B1/B2a**：保存候选、受控preview、私有证据/回放；人工审批/active路由/lease/outbox/统一调度/Agent仍不可用，不会切换日常爬虫入口。

保持主会话单写者，不用子代理。不读取/输出.env、私钥、备份正文；不运行旧安装/seed/dump恢复、down -v、prune或旧归档activate。额外新闻/模型/邮件调用不在授权内。

## 范围与固定边界

- 起点master@ae1fb87919c4ee252c2c4ec1f3bba5fa37283612，工作区clean；本地574/14、CI两job（含真实MySQL14）成功。真正候选仍需本轮验证。
- 生产预期应用M1@1052edf、checkout4477cfd、schema e6，须重新只读核实。
- 只切web/worker/worker_fast/beat；不重启MySQL/Redis/系统Caddy或同机项目。短停beat、排空worker后迁移/切换，保留准确旧ref/旧镜像和rollback overlay。
- 迁移e6→a731→b6只新增三表；失败检查实际schema，不盲目重复DDL。回滚应用保留扩展表，不downgrade/整库覆盖。
- B2a原文默认不保存。本轮拟添加**显式可选evidence Compose层**，仅web挂专用持久卷（4个Gunicorn进程共享），容器内路径在/app外、归实际应用UID、0700/文件0600；新卷初始化前核对空/所有权，既有目录不覆盖或擅改权限。普通preview仍需单独勾选才留原文。
- 清理依旧后台显式/下次保存触发，24h是可用期，不冒称即时物理删除；不加入未验收定时任务。主机挂载/锁/fsync/重启持久性用合成数据在隔离候选验证，生产卷不放测试原文。
- 合成HTTP/数据库/证据数据保持隔离；候选不带生产凭据，不派付费/邮件。线上HTTP仅本站health/登录/匿名权限检查，不登录后触发业务采集。

## 顺序

1. [complete] 本地/远端ref、CI与生产资源/容器/DB指纹只读预检；记录任何偏差后再行动。
2. [in_progress] 可选证据挂载Compose验收（沿用已批准运维seam，TDD），完整回归/静态检查，固定真正发布ref并推送/CI。
3. [pending] single-transaction备份、gzip/SHA256校验、旧镜像/ref/rollback配置保留。备份通过不等于恢复演练。
4. [pending] 构建四个真正候选；独立MySQL14项分别在web/worker实跑，四镜像模板/Admin/回放及新卷权限/锁/持久化smoke，无源码覆盖。
5. [pending] 停beat、worker排空/warm-stop，有限锁等待升级到b6；model diff/旧数据与LLM配置核对；切四应用，失败按阶段恢复旧服务。
6. [pending] health/worker/image/公网权限与证据挂载复核；其他容器ID/启动/重启数不变；精确清理临时测试资源、保留备份及持久证据卷，记录发布结果。

## 执行记录

- 只读预检：线上4477cfd clean、M1四镜像/容器未变、MySQL8.0.46/e6、无M2表、4模型配置指纹ff4b48c9…不变；10179 Article/38 sources/15317 logs。内存可用3792MiB、磁盘21GiB，health/Redis/Caddy正常。
- 新增可选evidence层，只给web挂外部专用卷；[运维说明](../../ops/private-crawl-evidence.md)。本轮全套576 passed/14 MySQL专用skip，154.31秒，业务Python未改变，两个新增Compose用例通过。
- 证据overlay两个Compose验收先因文件缺失red；增加后测试误将`--no-interpolate`的environment列表当字典，出现TypeError。先记录，按真实CLI输出规范化测试观察，不修改有效Compose配置、不算新业务red。
- 2026-09-09 14:49Z本地起点确认ae1fb87、clean。现有prod/caddy配置没有证据卷；仅部署镜像会使显式原文保留不可用，故先记录可选overlay与合成验收，不修改.env或默认开发配置。
