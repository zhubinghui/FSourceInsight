# B2b.2a采样台账提交与生产发布

## 授权与范围

用户2026-09-11明确要求“提交并部署”。允许本轮allowlist正常提交/推送、SSH、备份、隔离候选验证、c9→f2扩展迁移和应用发布；不额外采集真实新闻、调用模型/邮件、建立生产候选/策略或样本。主会话单写者，无子代理。

起点master@9c531e4，23项已知本地变更，暂存为空。本地673/16 skip，新MySQL第16项必须在独立环境补齐，旧版本15/15不可代替。原有回收并发配置保持；本轮有源码/迁移，不能复用旧14dc web镜像冒称上线。

## 安全边界

- 四应用web/worker/worker_fast/beat使用新源码一致镜像；不重启MySQL、Redis、Caddy及其他项目，不更改配额、模型路由或旧采集路由。
- 固定base→prod→caddy→evidence，保留原web专用external私有卷/UID0/0700，不覆盖或改权，不放合成原文。
- 不输出.env/容器Env/私钥/凭据/备份正文；不seed、恢复整库、downgrade、down -v、prune、force push/reset/stash，不运行历史固定SHA的归档activate。
- 新备份+旧image/argv固定；隔离MySQL768MiB、Redis64MiB，MySQL runner512MiB、生命周期runner1GiB串行运行，进入前MemAvailable至少3.5GiB。无生产凭据/host端口，精确label管理。
- 切换前暂停beat、检查两worker active/reserved/scheduled为0，TERM/warm-stop并等待。为固定迁移期间Admin输入，随后也正常停止web；迁移/切换期间预计短暂HTTP不可用。超时不强杀任务、不强制重建；保持beat暂停并报告。
- 新迁移仅新增台账表/profile两列；验证model diff0、旧计数/来源/候选/报告/策略投影hash及LLM配置不变，旧档案capture_generation=0/history_complete=False，不伪补历史。
- 回滚保留f2表/列/证据，不整库覆盖。旧14dc理解policy但不理解采样追踪：停止新版web后只读核无capture行且无tracked档案，才允许恢复旧web；有新追踪记录/档案或读取不确定则web保持停止、beat暂停并请求人工恢复，不静默绕过新台账。新worker回滚也先warm-stop，不强制重建。

## 阶段

1. [complete] 本地差异/静态、远端只读预检（refs/容器/内存/磁盘/schema/元数据/证据卷），确认无未知更改。
2. [complete] allowlist正常提交推送固定candidate，准确SHA CI全部成功；新备份/回滚image和argv保留，远端ff-only后串行构建，不切换运行容器。
3. [complete] 实际web/worker各16项独立MySQL；新image真实Admin/Redis/prefork生命周期；四镜像模板/HTTP/基础prefork与临时卷跨容器capture/flock/replay门禁。失败先更新计划，保持线上不切换。
4. [complete] 新helper固定ref/镜像/备份与阶段恢复；暂停/排空/正常停止，lock_wait_timeout10迁移c9→f2并验证；仅四应用切换，web/worker先就绪再启动beat。
5. [complete] 公网health/login/匿名新路由权限、实际argv/镜像/证据卷/非目标身份核对；部署后实际web/worker独立MySQL各16复验。
6. [complete] 精确清理9个本轮临时容器/网络/3卷/合成凭据，归档helper并删除原执行入口；保留备份/旧image/生产证据。发布报告已完成；收尾纯文档提交后按准确SHA核CI并仅ff-only同步，不重复部署。

## 证据与偏差

- 2026-09-11T08:42:58Z核本地master@9c531e4、23项已知变更/暂存空，diff检查通过。前一开发文件日期保留原始记录，本次发布单列09-11。
- 08:44:55Z远端9c531e4 clean，四应用running/OOM false/restart0；原卷UID0/0700/空，health全ok。MemAvailable约3993MiB、磁盘21GiB；LLM554MiB、fast412MiB、web403MiB、beat243MiB，无需扩大本轮资源限额。
- 只读c9元数据：Article10284/source38/log15507、四M2表均0、4模型配置指纹ff4b48c9…不变；两worker完整argv仍并发2/prefork/50/393216。后台正常数据增长，不是旧审计计数损坏。
- 330d50b正常提交/推送24文件；CI34580807525两job成功（含16项MySQL与生命周期）。备份cl-20260911084734/database.sql.gz为19,177,150 bytes/600，gzip/SHA256核实，旧四image/完整argv保留。远端ff-only/串行构建时原13容器身份不变。
- 实际候选web/worker各16项通过（33.958/33.263s）；候选worker真实Admin/Redis/prefork回收通过，RSS450992KiB。四镜像47模板/HTTP/基础prefork通过；临时卷真实capture/跨容器flock503/重建replay/revoke与UID1000拒绝通过，台账仍tracked且sequence1。
- 新回滚guard在准确隔离MySQL执行正/负控制：无追踪状态允许；tracked profile、丢行但非零capture marker、存在capture行均拒绝；移除合成测试行后再次允许。不是生产回滚演练。helper生成后的本地核对修正一个尚未执行的旧TEST常量，无远端失败或切换。
- 09:04:25Z开始web切换，09:04:32Z健康恢复，09:04:54Z全部完成（beat最后启动）；本轮没有触发回滚。c9→f2、model diff0、旧元数据/4模型指纹保持，新capture0，无授予追踪/规则许可。四应用OOM/restart0，memory.events全部0。
- 部署后准确image独立MySQL：web16/16（32.851s）、worker16/16（32.257s）。公网匿名新capture入口和原权限、health、实际SafeFetcher本站TLS、argv/卷/限额通过。
- 09:09:25Z清理收尾完成：六runner/MySQL/Redis/锁holder共9容器、internal网络/3卷/临时合成凭据删除，helper归档600及旧执行入口删除。原私有卷、其他容器/Caddy身份不变，health全ok，可用4.30GiB。非敏感证据已精确取回/tmp/fsi-cl-evidence，无备份正文/凭据。
