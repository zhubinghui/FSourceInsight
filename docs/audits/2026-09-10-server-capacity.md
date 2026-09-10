# 当前VPS整体容量评估（只读）

## 结论

**以当前三个项目的实际负载，4 vCPU/8GB档位的服务器能承受fast上限1GiB、beat上限384MiB，暂无立即升级服务器的依据。** 这两项是上限，不是预分配/预留；不是一改配置就多占640MiB。

但这是**当前负载与明确余量假设下的判断**，不是全站并发最坏情况保证。其他项目没有内存硬上限、所有容器没有CPU quota，不能把FSI配置上限当全机资源上界。后续浏览器/学习Agent、更高并发或其他站增长须重新评估。

本轮仅SSH只读系统/cgroup/sar指标及本地报告；未改生产配置、安装监控、调整swap/并发、重启/部署/提交，也未调用新闻/模型/邮件。运行应用14dc6f1，checkout de80b81；发布之后约3小时观察窗口。

## 机器与当前负载

采样：2026-09-10 09:10:18–09:11:18 UTC，3个快照/60秒。

| 指标 | 结果 |
|---|---:|
| CPU | 4 vCPU，Haswell虚拟CPU型号 |
| 内核可见RAM | 7,751MiB，约7.57GiB |
| 可用内存MemAvailable | 3,871MiB，约3.78GiB |
| swap | 无 |
| CPU平均忙 | 2.84%（整机四核口径） |
| CPU idle / iowait / steal | 97.14% / 0.01% / 0% |
| load average | 0.21 / 0.14 / 0.10 |
| 内存/IO PSI avg10/60/300 | 0 |
| 60秒直接回收/kswapd扫描/新增OOM | 0 / 0 / 0 |
| 根盘 | 72G文件系统、剩余21G、使用率72%；inode用10% |

不能把MemFree约821MiB误当全部可用内存；MemAvailable已估算可回收缓存。也不能把Committed_AS超过CommitLimit解释为实际RAM已满：当前vm.overcommit_memory=0，为虚拟地址承诺口径，不是RSS/工作集。

### 所有容器实测

工作集采用memory.current减inactive_file，近似Docker stats展示；不是严格不可回收集。memory.peak为该cgroup生命周期峰值，包含文件缓存；不同容器峰值不可当作同时发生。

| 服务 | 当前工作集MiB | 当前cgroup计费MiB | 生命周期峰值MiB | 内存硬上限MiB |
|---|---:|---:|---:|---:|
| FSI web | 377 | 379 | 394 | 512 |
| FSI LLM worker | 834 | 837 | 839 | 1024 |
| FSI fast worker | 437 | 440 | 475 | 1024 |
| FSI beat | 245 | 248 | 249 | 384 |
| FSI MySQL | 665 | 754 | 1024 | 1024 |
| FSI Redis | 10 | 19 | 34 | **无限额** |
| researchassistant frontend | 109 | 116 | 130 | **无限额** |
| researchassistant backend | 136 | 152 | 155 | **无限额** |
| researchassistant postgres | 36 | 52 | 63 | **无限额** |
| viva-insight web | 117 | 123 | 144 | **无限额** |
| viva-insight worker | 86 | 97 | 101 | **无限额** |
| viva-insight api | 157 | 172 | 239 | **无限额** |
| viva-insight postgres | 111 | 145 | 200 | **无限额** |

FSI工作集合计约2.51GiB，另外两个项目约0.73GiB。新四应用没有memory.events OOM/max事件；MySQL生命周期max318/peak1GiB但oom/oom_kill均0，不能据此推断现在故障或知道发生时刻。

Celery不能简单累加进程RSS：LLM worker的RSS总计1413MiB，PSS分摊共享页后832MiB；fast为816/435MiB。PSS与cgroup统计差异正常，不能把共享库/fork共享页重复算成新预算。

Docker/containerd/Caddy也有成本：containerd cgroup约1105MiB，其中file约814MiB，anon约142MiB；这不是containerd进程独占1.1GiB不可回收RAM。用MemAvailable估算全机余量，而不是把服务cgroup缓存再重复叠加。

## 历史不只是一分钟

服务器已安装sysstat，直接读取已有sa03–sa10，**不安装新采集器**。9月3–9日7个完整日共1001个样本，加10日截至09:10的55个，共1056个；大致10分钟一次。

- 样本最低MemAvailable：**3462MiB（3.38GiB）**，9月3日07:00 UTC。
- 1056个样本无低于2GiB者。仅代表采样点，没有秒级瞬时峰值保证。
- 最高区间平均CPU忙约**12.97%**，最高1分钟load采样1.40；四核整体没有持续CPU饱和证据。
- 历史区间平均iowait曾到**12.13%**（9月6日00:40），不能说磁盘从未有压力，原因未在本轮归因。
- 昨晚fast OOM前8秒的23:00:11样本，整机仍有**3806MiB（3.72GiB）**可用；23:10为3868MiB。内核明确CONSTRAINT_MEMCG，支持当次为容器限额不足，而非整台RAM耗尽。
- 近7日读取的18个oom-kill事件均为MEMCG；其中8个可直接关联已知M1/上一轮fast容器ID，其他旧ID未全部做归属。不能将这些事件都归到当前新容器，也不能忽略旧任务曾反复被杀。

新1GiB fast尚未经历完整夜间周期，因此还不能宣称彻底解决峰值/增长问题。已有历史很多时段使用旧上限，不能据此推出放开上限后的任意高峰仍安全。

## 容量预算：什么时候可以、什么时候不宜叠加

FSI五个有硬上限的服务合计：512+1024+1024+384+1024 = **3968MiB（3.875GiB）**。**不包含没有cgroup硬限的Redis**；Redis的`maxmemory 256mb`是内部数据/淘汰预算，不等于进程/持久化fork/连接缓冲总上限，也不能拿它当整个FSI硬上限。

按当前工作集到各上限的差额估算，五个服务还可能增加约1410MiB。以下是假设其他用量不变的算术余量，不是压力测试：

| 情景 | 估算剩余可用 |
|---|---:|
| 当前实测 | 3.78GiB |
| FSI五个受限服务同时用到上限，其他仍当前规模 | **约2.40GiB** |
| 上一行再叠768MiB测试MySQL+512MiB runner，按满预算 | **约1.15GiB** |
| 再叠其他两个项目工作集翻倍 | **约0.42GiB** |

最后一行尚未算Redis额外增长、构建/备份峰值、更多请求和内核开销，因此不能视为安全。这解释了：**普通运行可承受，不适合在全业务高峰同时跑多套构建/测试/浏览器。** 本轮提高fast/beat上限总计640MiB，相对历史最低采样余量仍有约2.76GiB，但历史采样/负载差异不构成绝对保证。

## 建议（本轮未实施）

1. **保留fast1GiB、beat384MiB，不回退到已确认不足的512/256；暂不因这两项升级16GB服务器。** fast1GiB不会主动吃满。beat常驻245MiB，256仅剩约11MiB，384较合理。
2. **下一优先项是LLM worker与并发/进程回收**：启动后约575MiB，现约834MiB/1GiB。可能是正常预热/任务保留，也可能持续增长，现有证据不诊断为泄漏。代码目前LLM并发4、fast2、Gunicorn4；未显式配置worker_max_tasks_per_child/worker_max_memory_per_child。宜实测LLM并发降至2与任务后进程回收的吞吐/内存收益，而非继续盲加2GiB。回收限制不是任务进行中的硬RSS沙箱。
3. **全机资源治理而非只管FSI**：为两个其他项目和Redis规划可测的内存/CPU预算，分阶段验证，不能未经该项目峰值/数据库持久化评估就随意加低硬限。当前13个容器全部cpu.max=max，没有硬CPU份额隔离；现在CPU很闲，但潜在并发不受总预算约束。
4. **错峰维护**：部署/隔离MySQL前建议MemAvailable至少3GiB，维持测试串行，预留不少于1.5GiB给宿主与同机突发。不要把测试环境当常驻；新浏览器/Agent上线前单独算预算。
5. **低成本监控**：现有sar可保留趋势，建议补1分钟MemAvailable/各cgroup current、peak、events、CPU/IO PSI。可用内存<1.5GiB持续5分钟告警、<1GiB立即关注；任意oom_kill增加立即告警，不能只看restart。告警阈值是运维建议，不是硬安全保证。
6. **swap可选，不自动开启**：1–2GiB作为紧急缓冲可另评估，但不是新增吞吐容量，不保证消除容器硬限OOM，也可能损害MySQL/网页延迟。当前没有为了正常运行必须立即加swap的证据。

证据：本地`/tmp/fsi-capacity-20260910.jsonl`、`/tmp/fsi-capacity-host-20260910.txt`、`/tmp/fsi-capacity-extra.txt`、`/tmp/fsi-capacity-sar09.json`、`/tmp/fsi-capacity-history.jsonl`。读取脚本经stdin执行，无服务器新增文件、定时任务或后台采样进程。没有重放付费/夜间生产任务或做压力测试。
