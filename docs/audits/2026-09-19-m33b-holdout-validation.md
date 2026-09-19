# M3.3b：HTML候选的有界留出验证（本地）

**局部功能实现，不是M3完成、部署或通用独立性保证。** 基线仍master `8bf2563`，此前M3改动和本轮新增均未提交。主会话执行，仅本地合成新闻/模型/数据库边界；没有子代理、SSH、实际新闻/付费LLM/SMTP或生产操作。

## 可见路径

1. Admin从保留证据的preview启动学习。`crawl-learning.v3`在训练成功保存候选时，同事务创建冻结验证记录；保留规则hash、学习身份、base规则、source/policy/engine及采样水位。
2. 学习详情提供原始base候选链接。管理员仍通过原有preview许可机制保留新的页面，验证本身不增加采集许可。
3. 点击“Validate frozen candidate”。服务端固定选择水位后该base**第一份保存的capture**；没有新capture时409，不消耗验证机会。已有第一份即使未保留原文、过期、失败或不足，也不跳去后来的好样本。
4. 私有文件和台账绑定检查通过后，提交选样及running身份，事务外真实M1回放，再重新核对权限、绑定、历史、污染和期限后保存结果。重复POST不重跑或换样本。
5. 详情展示当前`passed/failed/inconclusive/stale`和有限统计。通过仍是未发布candidate；学习执行状态与当前验证状态分开，不修改Article、不派文章LLM、不激活规则。

HTTP入口为`POST /admin/sources/<source_id>/crawl-config/learning/<identity>/validate`；只接受CSRF字段，不接受candidate/capture/recipe/quality/status选样控制。继承Admin权限及私有响应头。

## 检查标准与覆盖边界

当前成功路径：**一份无分页HTML列表、至少三份不同详情、全部候选详情模板被覆盖**。

- 用学习前base去掉详情规则后执行M1，得到采样清单；候选必须抽出相同文章集合。base不是正文真值，错误详情selector可以由学习修复后在新样本通过。
- 候选正文必须是M1判定的full，满足当前可信quality；内容来源指纹与对应详情快照及模板索引必须一致。标题/正文匹配、安全清理、抽取错误等继承M1。
- 不以模型声称成功作证据。过拟合训练页面、漏掉列表文章、错误详情质量均不通过；没有模板样本或不足三详情为inconclusive。
- 多列表、分页、RSS采样清单尚未支持为成功路径；不够证据就人工处理，不补抓、不用模型估计通过。
- 该检查是固定M1标准下的确定性质量/覆盖检验，不证明新闻事实真实或抽取语义完全正确。学习前清单自身有误/不可用时不能凭新候选自己建立真值。

## 独立性与保守历史

范围仅为**受控学习工作流**。跨来源的全部已记录学习暴露参与排除；所有较早验证选样也参与排除。比较原始字节SHA、规范化正文hash及请求/最终URLhash；详情旧URL不当新样本，列表同URL的新内容可以重新采样。相同正文或最终详情URL不能算多个独立详情。

`visible-text.v1`保持前一切片的精确定义，不是语义去重、部分复制或普遍污染检测。系统外模型、其他模型任务、外部人工发送及预训练仍不在这个覆盖证明内。不能把通过扩称为“任何模型都没看过”。

每个v3生成候选必须有冻结报告；控制行新增连续`selection_generation`，选样和计数同事务。缺报告、序列缺失/回退、绑定/文档损坏均fail-closed，且阻止新的学习付费。旧v1/v2候选不补冻结身份或验证结论。

较早选样排除后来的复用，不因后来一个被拒绝的重复验证而抹去原先独立结果；但**后来模型看过原留出**会使原passed显示stale。当前证据缺失/过期、来源ABA、撤权、历史或报告损坏也不能继续显示有效通过。

hash不是签名，不能防DB拥有者成套伪造或整个库一致回退。整库恢复/旧应用回滚仍需停止相关调用并另行审查。

## 期限与故障语义

与现有Admin replay一样是同步有界离线验证，不在HTTP内执行LLM循环。两次M1执行共享20秒检查点预算，持久截止最多30秒；不承诺HTTP/DB/进程硬deadline或全局并发租约。

运行中断保留已固定样本，既有`recover`每次最多收敛50份过期running验证为inconclusive，不自动重跑/换样本。实际恢复仍依赖启用的beat和消费者；停用、拥塞、数据库不可用时没有及时终态保证。SQL结果写失败保持running而非假通过。

选样hash绑定操作者和期限，结果状态必须与结果文档一致；仅改state不能把failed变passed。时间先规范化到整秒再写入，避免数据库低精度DATETIME舍入后破坏hash；期限不延长，旧历史不重新签名。该精度问题由SQLite触发器模拟外部DB行为复现，**不是实际MySQL证据**。

## 数据与迁移

新head **`e1c73d9b502a`**，父`d9b72a6e410c`。新增`crawl_validation_report`，同session及candidate各唯一；加state/deadline索引；控制行新增默认0的selection计数。没有旧候选/会话回填、没有伪造报告，保留旧历史/费用。禁止破坏性downgrade。

报告只保存绑定、私有文件引用、指纹与受限结果，不复制原文；详情不展示原始URL/文件路径/正文或私有SQL参数。raw仍受原有0700/0600、容量、24h和清理约束。结果、选样不可经HTTP覆盖；不自动删除历史来腾额度。

## 验证进度

- 新增42项离线Admin HTTP/故障/Alembic回归。
- 第一轮全套：836 passed / 19 dedicated-MySQL skipped / 7960 warnings / 428.34秒；日志`/tmp/fsi-m3-izjIZv/m33b-full-01.log`。这是精度修复前的结果。
- 精度边界red→green后相关14项通过；随后补了候选分页/额外列表未覆盖的两项red→green。最终全套：**839 passed / 19 dedicated-MySQL skipped / 8035 warnings / 436.47秒**，完整日志`/tmp/fsi-m3-izjIZv/m33b-full-02.log`，30秒faulthandler未触发。
- 静态：201份Python AST、48份Jinja模板、Alembic单head、指定flake8和git diff --check通过。
- 新head已同步实际MySQL空库/迁移/model-diff门禁；19项仍全部未运行，没有真实MySQL验证流程、broker/prefork或硬杀进程的通过声明。
- 收尾复现并修复：复用训练/旧验证样本、模板不足误标failed、缺过期收敛、丢旧报告后仍准入、state单列篡改误显示通过、操作者/期限未绑定、低精度时间hash，以及候选未覆盖的分页/额外列表分支误通过。其它既有保护直接通过，不冒称均为新red。
- fixture偏差：不支持的`:first-child`改为允许的合成`.first-card`；非管理员按已有拒绝跳转首页验证，不改权限实现。精确编辑冲突未落盘，重新定位后继续。

## 后续与启用限制

M3仍缺冷却/受控重试、完整可靠执行和真实服务门禁、专用worker Compose/共享证据/容量、企业发现迁LLM队列。通用RSS/分页/多列表独立验证及全系统暴露覆盖也未完成。M2人工审批/active/previous、日常schema路由调度仍独立待办。

当前生产私有卷仍仅web；本轮没有新增消费者、挂卷或启用真实学习。所有实际验证、提交和部署需另行授权；不能借历史发布证明新代码可部署。操作步骤见[学习说明](../ops/crawl-learning.md)，决策范围见[实施计划](../superpowers/plans/2026-09-18-m3-bounded-learning.md)。
