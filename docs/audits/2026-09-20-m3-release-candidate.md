# M3累计内容发布候选（尚未部署）

## 当前结论

用户授权全部提交并部署。已提交并推送`release/m3-bounded-learning-20260919`，**生产切换尚未执行**；没有本轮生产迁移/备份/停服/真实模型或采集/邮件验收。未把“继续”当作允许默默暂停付费功能。

候选应用`1becae8`：包含原M3累计内容、已发布生态功能、后续`e6469ba` Admin安全修复及M3审计关联删除防护。唯一schema head为`c7f21a9d680e`。本地工作树在应用提交后clean；本文件是后续证据，不是新业务代码。

执行来源：[发布计划](../superpowers/specs/2026-09-19-m3-current-release.md)。M3整体仍未完成，learning默认关闭。

## 提交与兼容

- `751ac51`：98文件基础M3及发布计划，首次独立release分支，不覆盖同时上线的生态版本。
- `76d0e60`：合并生态`23de19e`，保留pending审核、rejected墓碑、lab不扫描、结构化优先/同host详情事实、XSS和Admin能力；保留M3 SafeFetcher/原子Company+job/LLM队列及费用保护。
- `startup-analysis.v2`绑定review/geography及ORM代次，旧v1不自动重签。详情HTTP在业务事务之外准备，最多20个候选，各自15秒，不谎称受列表30秒总预算约束。
- `c7f21a9d680e`只合并b3生态与b5 M3两条迁移历史；不重写已有DDL或审计、不认证旧计费上界。
- `1002789`修正新增MySQL旧公司造数的非空字段；`7f6e9f8`整合生态收尾文档，曾通过完整CI。
- `1becae8`合入`e6469ba`：不丢失自锁/密码/历史删除/每日爬取小时修复；额外保护无usage的reservation配置、学习创建/retry/validation申请人及对账actor。DELETE外键拒绝回滚并给固定提示，不删除历史。既有MySQL门禁扩展真实Admin删除与对账保护，测试数仍22。

## 验证与保留失败

环境：临时Python3.12 venv；本地Docker socket仍不可用。真实MySQL及Redis/prefork来自独立GitHub CI，不是生产，也不是待部署web/worker镜像。

- `1becae8`本地完整：**1075 passed /22 dedicated-MySQL skipped /10768 warnings /613.70s**；`admin-merge-full-01.log`。
- 新Admin合并关联：108通过/876警告/39.37s；7个新增公共HTTP回归，先实际red再green。最初detached登录/选样fixture错误单独保留，不冒称产品缺陷。
- 静态：243 Python AST/49模板；指定文件无新E9/F问题，两条历史F401保留；diff检查通过。
- `7f6e9f8`的**CI35510122656成功**：1060离线/22skip；真实MySQL22通过（95.025s）；真实broker100次完成后回收、RSS450652KiB完成后回收、下一任务正常，`WORKER_LIFECYCLE_OK`。
- `1becae8`的**CI35517521638完整成功**：1075离线/22skip/789.37s；实际MySQL22通过40.850s（包括扩展Admin删除/对账保护）；真实broker100次任务后回收及RSS452980KiB完成后回收、下一任务成功，`WORKER_LIFECYCLE_OK`。这不是复用7f的绿。应用内容随后不变，仅追加本发布候选审计/状态文档。

失败记录：
1. CI35472655051：1014通过/5 Compose失败；CI2.38.2即使no-env-resolution仍检查必需.env。官方同版本校验后临时目录可复现，改测试复制公开Compose+空.env；未读写真实.env，旧断言保留，v2五项通过。
2. 合并回归141/2失败是遗漏旧网络mock/CLI stdout捕获；完整1059/1失败进一步证明capsys不能接住Alembic预绑定stdout。改真正独立Flask CLI（testing/禁dotenv）后通过。
3. 300s组合工具超时：35完成，无残留；下一项单独通过，完整回归未复现。根因未知，日志不覆盖。
4. CI35497160720：离线成功、真实MySQL21/1错误；新增b3迁移fixture漏非空字段，不是迁移丢数据。补全且增加失败计数保留断言，再次CI通过。
5. 两次gh watch本机网络/工具期限中断，直接查询确认CI终态，不把watch退出当测试结论。
6. Admin关联初轮107/1失败仅提示文案不兼容，恢复上游usage history措辞并补充reservations，没有削弱断言。

日志均保留于`/tmp/fsi-m3-izjIZv/`，不提交原始控制日志/密钥/dump。上游CRLF CSV证据字节未改；默认cached diff曾报尾部空白，另按cr-at-eol检查，不虚报原始默认检查全绿。

## 生产阻断与下一步

1. **计费审核/明确选择**：旧NULL上界会拒绝新的付费LLM调用。需要审核实际endpoint、账户服务层/区域费、完整价格和全部计费token上界；或者用户明确接受暂停新付费LLM。不能猜数或偷偷制造功能停摆。[官方资料审核输入](2026-09-20-m3-billing-review-inputs.md)不是生产合同确认。
2. 重新核主干/生产refs/容器及其他发布者，协调单写者窗口。本轮期间另一工作树多次推进，未修改/提交其未提交内容。
3. 实际候选镜像/隔离MySQL/服务/卷/模型差异验收及容量核对；新备份、停止旧付费调用方、扩展迁移、受控应用切换、只读健康验收。不可复用旧CI或SQLite冒称完成。
4. 不启用learning，不改变真实模型/来源授权，不运行整库恢复、seed、破坏性downgrade或非目标服务重启。即便后续普通应用上线，M3全部学习/容量/恢复门禁仍不能宣布完成。
