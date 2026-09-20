# M3付费连续性：标准请求合同与发布配置

## 状态

用户明确要求保留付费LLM并部署剩余内容。本文件记录审核依据；**累计实现已于17:39:41Z发布83813e2/c7，付费功能保留**，见[完整发布证据](2026-09-20-m3-paid-release.md)。学习仍关闭，全部M3尚未完成。本轮未采用暂停付费、取消预算、提高日预算或旧调用旁路。

执行：[连续性计划](../superpowers/specs/2026-09-20-m3-paid-continuity.md)。发布起点e6469ba/schema b3，现已升至c7f21a9d680e；本请求兼容切片本身无新DDL，发布应用了此前累计迁移。下列为审核过程，最终实际应用/镜像/清理见发布证据。

## 只读事实与审核选择

16:28Z生产只读：两活跃配置为OpenAI mini(id1)/nano(id5)，max_tokens4096，temperature0.3；无自定义端点或HTTP代理环境覆盖，明确API key存在但不输出值。日预算$5，旧日28条usage、unknown cost0、账面估计$0.001578。mini旧单价每千$0.0025/$0.010，nano旧$0.00015/$0.0006，不等于当前官方标准价。

采用可验证的标准文本合同，保留模型/任务/role/priority/default/active/key/温度和每日$5：

| 配置 | 显式端点 | 输入上界 | 输出上界 | 每千输入/输出 | 每次预留 |
| --- | --- | ---: | ---: | --- | ---: |
| mini id1 | https://api.openai.com/v1 | 400000 | 4096 | $0.000750 / $0.004500 | $0.318432 |
| nano id5 | https://api.openai.com/v1 | 400000 | 4096 | $0.000200 / $0.001250 | $0.085120 |

- [mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)、[nano](https://developers.openai.com/api/docs/models/gpt-5.4-nano)官方页：400000总上下文、128000模型最大输出及上述标准文本价；两者区域端点有10%附加费。因此本批明确用全球官方端点，不适用于其他网关/区域/工具或模态费用。
- [官方OpenAI SDK v2.54.0固定源码](https://raw.githubusercontent.com/openai/openai-python/v2.54.0/src/openai/types/chat/completion_create_params.py)：`max_completion_tokens`是包含可见输出及reasoning的总生成上界；`service_tier=default`明确使用标准价格/性能。不是根据参数名字推测。
- [Priority/Fast官方指南](https://developers.openai.com/api/docs/guides/priority-processing)：省略tier可继承Project Fast。本切片显式指定default，排除此隐式收费层，而非猜测Project当前设置。
- LiteLLM1.101.0实际SDK出站合成HTTP已验证：两个当前模型均向官方chat/completions发送`max_completion_tokens=4096`、`service_tier=default`，不发送旧max_tokens、tools/modalities。完整400000输入界来自供应商模型合同，不是tokenizer估算。4096不是用可见文本长度冒充隐藏输出界。

日预算5不提高；单请求及现有两LLM执行槽位的最坏预留能容纳。接近日预算/有未知费用时仍应拒绝新的付款，这是保留预算保护，不等于选择暂停模式上线。供应商违约、税费/另行合同费用不是应用能保证的最终发票上界，不能把此审核说成账户账单核销。

旧usage不重写/伪造新关联，不认证为最终发票：它们继续按原日志估计参与既有legacy成本规则，旧价格误差是历史局限。停用DeepSeek/Claude不启用、不填未经审核上界。

## 最小变更与回归

- 仅对provider=openai、实际模型路由仍openai、显式全球官方端点请求default。自定义网关/其他provider及未显式端点的旧接口保留原参数协议。
- 有效tier纳入响应缓存键；历史相同输入/端点但auto层的持久缓存不冒充default层结果。其他路由的键不变。
- Admin表单说明该端点语义；没有增加test-only API、DB字段或内部授权绕过。
- 新8个离线用例通过既定公共LLMClient/真实Admin及外部HTTP/Redis/SDK边界：实际SDK标准层/总输出界/付款前可见预留/含reasoning结算/正常缓存、legacy auto缓存隔离、界面说明、其他四类路由兼容。
- 真正red分别记录paid-transport-red-01（两模型缺tier）、paid-cache-red-01（误复用auto缓存）、paid-ui-red-01（未说明语义）。四个其他路由保护直接green，不冒称red。
- 关联161通过/23专用MySQL skip/1773 warnings/32.17s；244 AST及选定E9/F、diff通过。随后1083本地、准确CI35523984792、两实际image各23实库前后复验均通过。
- 新增一个实际MySQL门禁，总数23：b3旧配置→完整head→Admin审核→两个模型真实SDK/合成HTTP付费成功，审核前不付款。已在CI及实际候选分别执行；本地skip不算通过。

## 发布时要求（已执行）

真实候选保持生产LiteLLM1.101.0/OpenAI2.54.0，不能重建时偷偷升级浮动依赖。准确全套/CI/两镜像23项MySQL及服务门禁通过后，新备份/停止旧调用方和Admin写入、b3→c7、原配置CAS核对后一次性更新上表两行，确认无未审核的活跃付费路由，再启动一致新应用。

学习仍默认关闭，无crawl_schema模型/来源新授权；上述宽输入合同不符合学习20000累计token的准入限制，不能为了开启学习擅自缩小上界。当前切片解决现有普通付费工作流，不宣称全部学习/恢复/容量已完成。
