# M3上线计费审核输入（初版历史记录）

> 后续实际审核与发布已完成：[固定标准层/SDK合同与TDD](2026-09-20-m3-paid-continuity.md)、[83813e2/c7发布](2026-09-20-m3-paid-release.md)。两活跃配置已应用官方全球端点/default层、400000/4096总计费界及标准价，原5美元预算/功能保留。下文记录初版未知项和条件算例，不是当前未部署状态或本次实际填写的输出上界。

2026-09-20，主会话查阅官方资料；没有调用模型、读取API key、修改生产配置或签署账单确认。用户已要求提交部署，但不能把缺少计费上界的旧配置当作透明升级。

## 官方资料能证明的内容

| 模型 | 标称上下文 | 标称最大输出 | 标准文本输入/百万token | 输出/百万token |
| --- | ---: | ---: | ---: | ---: |
| gpt-5.4-mini | 400,000 | 128,000 | $0.75 | $4.50 |
| gpt-5.4-nano | 400,000 | 128,000 | $0.20 | $1.25 |

来源：[mini模型页](https://developers.openai.com/api/docs/models/gpt-5.4-mini)、[nano模型页](https://developers.openai.com/api/docs/models/gpt-5.4-nano)、[发布说明](https://openai.com/index/introducing-gpt-5-4-mini-and-nano/)。两模型页另明确区域处理/data residency endpoint有10%附加费；工具调用可能另收费。不能只抄首页单价而忽略实际endpoint/服务类型。

[官方reasoning指南](https://developers.openai.com/api/docs/guides/reasoning)明确：不可见的reasoning tokens仍占上下文并按output tokens收费；没有可见答案也可能已经产生费用。

[官方Python SDK的ChatCompletion参数定义](https://github.com/openai/openai-python/blob/main/src/openai/types/chat/completion_create_params.py)明确：
- `max_completion_tokens`包含可见输出和reasoning tokens；`max_tokens`已经deprecated，不能凭相似名字假设每个适配器版本都有相同语义。
- 未指定`service_tier`时默认`auto`，使用Project配置；明确`default`才表示标准处理价格/性能。

[官方Fast/Priority说明](https://developers.openai.com/api/docs/guides/priority-processing)明确Project级别可默认Fast，未传`service_tier`的请求会使用该设置，Fast有额外单价。资料是动态网页/SDK main，不是固定快照合同或生产账户证明。

## 与当前代码的关系

`app/llm/client.py`通过LiteLLM传`max_tokens`，没有显式`service_tier`。[后续独立Admin发布](2026-09-20-admin-safety-release.md)已实际核实并保留生产LiteLLM1.101.0/OpenAI2.54.0（普通重建得到1.102.0，已拒绝）。这只确认版本，具体转换/账户Project配置仍需核实。仅知道DB里provider为OpenAI、model为mini/nano，不能证明没有网关、区域或Project级附加费。

`app/llm/budget.py:quote()`使用管理员审核的完整输入/输出计费上界及每千token单价预留，不使用prompt长度猜测。若**另经审核确认**标准费率/这些模型上界适用于实际端点，按400,000输入、128,000输出保守独立相加，数学预留分别为$0.876000和$0.240000。这只是条件计算，**不是建议直接填入生产或已经审核**。日预算/并发余量也需要复核。

如此宽的上界会超过学习流程20,000累计token上限；不能为让学习通过而擅自填更小估计。学习仍默认关闭，部署代码不等于模型/来源权限或M3完成。

## 后续技术审核（仍需发布门禁）

用户明确要求不暂停付费。已补[连续性审核与TDD](2026-09-20-m3-paid-continuity.md)：只读确认无端点/代理覆盖，拟显式全球官方端点+标准default层，固定SDK真实出站合成HTTP确认4096包含reasoning，输入采用400000供应商上下文上界，并纠正两活跃配置的旧价格。不是用估计替代合同；生产配置尚未更新，实际候选和切换门禁仍待。以下旧“可暂停”仅为初版备选，现已排除。

## 切换仍需要

1. 确认实际端点、模型/别名版本、账户服务层/区域及完整费率；不输出密钥或带secret的URL。
2. 审核总计费input/output（含隐藏reasoning）的可靠上界和实际适配器请求语义；不能拿`max_tokens=4096`或tokenizer估算代替供应商保证。
3. 将实际选择/审核人/依据记录到发布证据，经过正常Admin审核或明确批准的配置变更；现有NULL保持NULL直到完成。
4. 或者用户**明确接受暂时暂停新的付费LLM调用**后，以拒绝未审核调用的模式部署。缓存/既有数据可继续使用，但新翻译、摘要、洞察和企业分析等会受影响；不是透明无损上线。

当前没有生产配置变更/付费暂停授权。准确代码、CI、并行工作树和候选验收状态以[发布计划](../superpowers/specs/2026-09-19-m3-current-release.md)为准。
