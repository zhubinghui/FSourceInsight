# 当前M2成果提交并合入主干

## 授权与范围

用户要求“目前所有部分都提交并合入主干”。允许提交/推送当前已完成的M2-A、B1、B2a代码、测试、迁移与全部配套架构/计划/审计文档；不扩展为生产部署、SSH、真实新闻爬取、付费模型或邮件授权。

M2b持久policy/独立验证/审批/CAS、可靠运行/调度及M3/M4仍未完成，不能把合入主干解释为整个M2交付或生产已升级。保留所有既有改动，不reset/stash/force push。

## 预检事实

- 当前分支master，起点4477cfda77f42c15fd1ab304bbd309a22e105397。
- `git fetch origin`成功，HEAD与origin/master领先/落后均0；当前已经在主干，无需人为制造合并提交。
- 暂存区为空，dirty均为既有M2及文档；无raw快照、env、私钥或备份纳入候选。
- 当前工作流只有离线与独立CI MySQL测试，不包含部署。GitHub CI使用一次性m0-mysql，绝不指向生产。
- 临时Python3.12环境可用；最近证据574 passed/14 MySQL专用skip，需本轮复验。实际MySQL待推送后以该提交的CI结果核对，不借历史结果背书。

## 操作顺序

1. [complete] 完整本地回归、AST/模板/静态检查；核对明确文件allowlist、暂存diff与敏感文件边界。
2. [in_progress] 提交当前成果到master，正常push origin master；若远端并发变化先记录，再保留双方历史处理，不强推。
3. [pending] 核对远端ref、该提交的CI；失败时先记录，按真实失败处理，不降低测试或宣称CI通过。
4. [pending] 补充合入结果文档并提交，最终确认工作区clean、master与origin/master一致。生产不动。

## 验证记录

- 本轮全套574 passed / 14 MySQL专用skip / 3453 warnings，162.03秒；日志`/tmp/fsi-m2-mainline-tests.log`。
- 158 AST、43模板、指定flake8、Alembic单head b6、96个本地文档链接/围栏通过。
- 明确allowlist共34文件，与全部tracked dirty/untracked文件精确相等；仅.py/.md/.html普通文件。无env/raw快照/备份/私钥文件；常见凭据标记检查无命中（不是完整秘密审计保证）。空的未跟踪目录不纳入Git，不删除。
- 主会话复核关键模型/迁移接入、Admin权限与generation、预览/回放/私有证据范围；没有接入自动路由、发布或生产配置。
