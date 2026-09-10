# Production worker并发与任务后回收发布

## 最终状态

- **配置发布commit：`81135d8cedfbc258bd1857e40d7685e56ba4d88a`**，正常合入master并推送。
- **运行应用镜像仍为`14dc6f1`、数据库仍为`c9e41a7b620f`**：运行源码、依赖、Dockerfiles无差异，未重建镜像、未执行DDL。
- 生产LLM并发4→**2**，fast仍**2**；两者明确prefork、每子进程**50次完成尝试**或任务完成后RSS高水位超过**393216KiB（384MiB）**回收。开发base保持原配置。
- 最终切换 **2026-09-10 13:53:30Z→13:53:54Z**。只有两个worker容器重建；beat短暂停后恢复原容器；web、MySQL、Redis、Caddy和另外两个项目未重建/重启。
- 首次切换遇到命令格式校验误判并自动恢复旧命令；修门禁、新备份后重试成功。不能将此写成“没有触发回滚”。
- 14:02:28Z公网home/www/login/health通过；数据库/Redis/status全ok；临时测试资源与合成凭据已删除，备份/旧镜像/私有证据保留。

用户明确授权实现、合入、部署。未触发生产新闻/付费模型/邮件，没有修改其他项目配额或swap。普通已配置业务调度仍按原语义工作。

## TDD与实际运行证据

### 配置red→green

1. 真实Compose CLI，dev直接通过；三个生产组合起初`4 != 2`失败，生产overlay最小修改后通过。
2. 增加prefork/回收阈值断言，三个生产组合因缺参数真实失败；补两worker命令后通过。
3. 原端口/源码挂载/私有证据卷/资源上限测试保持；运维文件10项通过。

本地全套：**643 passed、15专用MySQL skip**，184.44秒；指定flake8、AST、Markdown链接/围栏及diff检查通过。skip不是MySQL通过证据。

### 准确CI与独立MySQL

[CI34483808675](https://github.com/zhubinghui/FSourceInsight/actions/runs/34483808675) 对81135d8：

- test：643/15，238.98秒；仅导出真实四层Compose的worker命令artifact，无.env解析或完整配置泄露。
- mysql-integration：15/15，22.384秒；随后运行新的真实Redis/prefork生命周期检查，成功。

实际生产image的独立MySQL（未挂载覆盖app，只挂tests）：

| 阶段 | image | 结果 | 秒 |
|---|---|---:|---:|
| 切换前 | web | 15/15 | 30.023 |
| 切换前 | worker | 15/15 | 29.817 |
| 部署后 | web | 15/15 | 29.475 |
| 部署后 | worker | 15/15 | 28.779 |

这次为配置发布，前后image相同，不把重复验证包装成新构建或新迁移。

### 真实Admin→Redis→prefork回收

`tests/integration/check_worker_lifecycle.py` 使用实际应用与已有crawl任务，无新增测试任务/API；`tests/support/worker_environment.py`仅在测试worker进程/DNS/socket/TLS边界注入合成环境，不进入生产镜像。

- LLM真实pool启动，inspect确认并发2/50，不调用模型测吞吐。
- Admin POST真实发布100个停用来源任务，Celery结果全部完成；49次总完成时原PID仍在，100次时至少一个原子进程退出并被reap，父进程继续运行。
- **新fresh fast pool**执行真实RSS任务，在外部Popen边界实际touch 192MiB并保持任务阻塞。超过RSS阈值后，任务未完成时子进程仍存活；释放后任务成功返回，原PID退出/reap，父进程存活，后续任务成功，Article API总数0。
- fresh pool避免把50任务计数触发误当RSS触发。实际高水位：初次worker image450420KiB；补49断言后的fast image450720KiB；部署worker image复跑450672KiB；CI442648KiB。不是mock内存数值。
- 这是有界生命周期验证，不是生产付费吞吐、单任务峰值、夜间负载、长期泄漏或M2 lease/outbox/重投递恢复的完整验收。

## 备份、失败与重试

初始备份：`/home/ubuntu/fsourceinsight-backups/wr-20260910132339`，19,094,087 bytes/600；新重试备份：其`retry-2/database.sql.gz`，**19,094,088 bytes/600**，gzip与SHA256均核实：

```text
3caec629c1037c55aed52f3b2a4296a588490dfdb64f8271e74c48b636e9b681
```

旧image和**旧command**同时保留在`rollback.compose.json`，只pin image不能撤回新的命令overlay。未整库恢复或downgrade；gzip/hash不等于数据库恢复演练。

本轮三个运维差异均先记录、再按原流程修正：

1. 备份预检的Docker `label!=`过滤不受支持，报`invalid filter 'label!'`。当时只有refs/state元数据，尚未改生产。改为受支持的正向ID集合差，在精确partial状态匹配后恢复。
2. 首次13:48:28Z切换，实际两pool已是2/50，但门禁直接比较Compose字符串与Docker argv数组而误拒。自动warm-stop新worker、恢复旧image/旧command，注册就绪后13:49:13Z恢复beat；只读核实旧命令确实恢复、web原ID未变、四应用OOM false/restart0、health正常。修正仅用shlex规范字符串，完整等值断言保留，且负对照仍拒绝旧命令。13:53:02Z重新预检/新备份后再切换成功。
3. 清理前发现部署后MySQL日志名被随后lifecycle日志覆盖；**两个容器均exit0且尚未删除**。给lifecycle产物独立前缀、禁止覆盖，从准确label/exit0的原MySQL容器日志恢复原输出，复核15项后才清理。不是产品测试失败，也没有重跑生产任务。

第2项实际验证了**本轮空闲worker的命令恢复分支**，但不是繁忙/崩溃、消息可靠性或数据库恢复演练。warm-stop超时分支会保留beat暂停并报告，不强制重建正在执行任务的worker。

## 线上确认与边界

两worker实际Docker argv、1GiB限制、image均与固定候选一致；inspect两pool2/50；新worker memory.events的max/oom/oom_kill均0。私有external证据卷仍web独占、UID0/0700，未改权限、填入合成原文或清理生产证据。

切换期间DB元数据一致：Article10233、source38、CrawlLog15422、四M2表均0、schema c9；4项LLM配置指纹仍为`ff4b48c9f237d6974d8e5605bd9233d6f29215ab21ea157d5856fff3697faef1`。未seed或改变模型路由。

清理后约14:02Z：

| 项目 | 实测 |
|---|---:|
| MemAvailable | **4297MiB（4.20GiB）** |
| LLM worker | **365.7MiB/1GiB** |
| fast worker | **378.7MiB/1GiB** |
| web | 388.5MiB/512MiB |
| beat | 243.1MiB/384MiB |

实施前13:00Z LLM约852.6MiB，但下降包含重新启动释放旧保留内存，不能全部归因于减并发或据此宣布泄漏已治愈。Linux使用ru_maxrss高水位而不是PSS；RSS可能包含共享页。回收只在任务完成后，不限制执行中的峰值，也不处理父worker/beat增长。降低并发可能增加排队延迟，未做付费吞吐测量。

其他七个项目容器与FSI Redis仍无cgroup内存硬限、全部无CPU quota；未新增监控、swap、全局预算。保留后续整机资源治理、夜间/长期观测需求，不声称完整M2验收。

## 资源收尾

精确删除label`fsi.validation=fsi-wr-20260910132339`的7个测试runner、独立MySQL/Redis、internal网络及测试MySQL卷，移除临时目录/合成凭据。保留两份备份、旧image/tag、现有生产卷。逐项比较原容器清单：web和所有非目标容器ID/启动/restart不变，beat原ID恢复；Caddy启动时间不变。

本轮helper/state已归档初始备份的`helpers/`（600），原执行入口删除。**归档脚本固定本轮SHA/路径，不可作为下次入口重跑。** 合成测试stdout/exit保存在`validation/`；本地选择性证据在`/tmp/fsi-wr-evidence/`，未取回数据库备份正文。

本报告及进度更新为纯文档提交；服务器随后仅ff-only同步文档，不重建/重启应用。文档head的CI需另行按准确SHA确认，不用配置提交CI冒充。
