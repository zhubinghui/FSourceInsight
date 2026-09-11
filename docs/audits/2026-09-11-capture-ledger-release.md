# B2b.2a采样台账生产发布

## 最终状态

- 应用：**`330d50b20c3bdfd25a94bfd91a9d246832854b87`**，已正常提交/推送master并部署。
- Schema：**`f2a67b904d31`**（c9→f2），model diff0。
- 2026-09-11 **09:04:25Z开始web切换，09:04:32Z健康恢复，09:04:54Z全部完成**；约7秒HTTP恢复窗口，beat在web/worker验收后最后启动。
- 本轮未触发回滚。只更新web/worker/worker_fast/beat，MySQL/Redis/Caddy及其他项目身份/启动/restart不变。
- 两worker仍并发2/prefork/50次尝试/393216KiB任务后回收；原web专用external证据卷UID0/0700保留，未改权或放入合成原文。
- 09:09:25Z最终health：database/redis/status全ok。临时资源/合成凭据已精确清理，旧镜像/备份保留。

用户明确授权“提交并部署”；单写者、无子代理，无额外生产新闻/付费模型/邮件，没有生产候选/策略/样本写入。普通后台任务恢复不等于手工触发业务。

这次只发布长期Admin预览采样台账，**不代表独立留出验证、人工规则审批、日常schema路由或可靠消息协议已经实现**。

## 验证

[功能CI34580807525](https://github.com/zhubinghui/FSourceInsight/actions/runs/34580807525) 精确对应330d50b，两job成功：

- 673 passed / 16专用MySQL skips，272.09s；此前本地673/16为209.01s。
- 独立MySQL **16/16**，22.729s，含新capture HTTP/裁剪/SQL失败原子性用例及新head metadata比较。
- 真实Admin→Redis→prefork任务完成后回收通过，RSS442648KiB；没有调用付费模型测吞吐。

实际构建image（只挂测试，不覆盖app源码、不借生产凭据）在同机独立internal网络的MySQL8.0.46上复验：

| 阶段 | 镜像 | 测试 | 秒 |
|---|---|---:|---:|
| 候选 | web | 16/16 | 33.958 |
| 候选 | worker | 16/16 | 33.263 |
| 部署后 | web | 16/16 | 32.851 |
| 部署后 | worker | 16/16 | 32.257 |

- 候选worker image完整真实broker生命周期通过：LLM pool2启动、100次已有任务后计数回收、fresh pool任务内不杀/结果返回后RSS回收/父进程存活/后续任务成功，RSS450992KiB。
- 四image各47模板编译、CSRF/Admin/API/HTML、真正离线回放与基础billiard→parser通过。
- 临时Docker卷跨容器capture→flock忙503→重建后replay→revoke409，台账仍tracked/sequence1；UID1000拒绝访问。不是在生产证据卷放测试数据。
- 回滚guard通过独立MySQL SQL/CLI正负控制：无追踪状态允许；tracked profile、非零capture marker但缺行、存在capture记录均拒绝；清理合成行后再次允许。此为门禁分支测试，不是本轮生产回滚演练。
- 公网匿名带有效CSRF仍被原变更入口拒绝，新`/captures`和`/captures/<id>`也要求Admin；health/login/www/API/HTML及运行image内SafeFetcher本站真实TLS通过。

实际image IDs：

```text
web         sha256:d94a55821d5adf1ce7e83ae9af5dabfa88870955c767e109cbe692bde34df184
worker      sha256:75013b13f6774a1d414fba9174691a328ee47fbf8c6ca8cc4bfe04cfe18bbb29
worker_fast sha256:c8b9194dc57b58837398de47892f2dfa33c2b3c5e4730084450f8b74db12e60e
beat        sha256:da7db7cc002fe36f8639c26e9462d11b4b80268d1fe91ace3422c8514c7e9b7b
```

## 备份与切换

备份`/home/ubuntu/fsourceinsight-backups/cl-20260911084734/database.sql.gz`，**19,177,150 bytes / mode600**，gzip/SHA256核实：

```text
2486a0b948c79460ddeaf1839fb2e48364ed5df0f8921ec242f0b507d966cbde
```

旧四image及完整argv固定于`rollback.compose.json`，四候选串行构建时13个原运行容器身份未变。切换前准确CI/候选门禁通过后才暂停beat、检查active/reserved/scheduled全0、TERM两worker并等待exit0，再正常停止web。迁移期间没有Admin并发写入；设置DDL lock_wait_timeout10，不downgrade/恢复整库。

迁移验证保留Article10284/source38/log15507及原四M2表（均0）；来源及M2旧投影hash不变，新增capture0，未自动设置tracked。4项LLM配置指纹仍`ff4b48c9f237d6974d8e5605bd9233d6f29215ab21ea157d5856fff3697faef1`。

旧14dc web不理解采样追踪：本轮恢复协议须先停止新web并只读确认无capture/非零marker/tracked档案，否则web停止、beat暂停并要求人工恢复，不能让旧程序静默绕过台账。回滚不删除扩展表/列/证据；warm-stop超时不强制重建运行任务。分支已准备和隔离测试，未在本次生产触发。

## 清理与边界

精确删除label`fsi.validation=fsi-cl-20260911084734`的**6个runner+MySQL+Redis+锁holder，共9容器**，internal网络、MySQL/evidence/state共3测试卷、临时目录及合成凭据。原生产卷保留；helper/state归档到备份`helpers/`（600），原执行入口删除。归档helper固定本轮SHA/路径，不能重跑作为下次发布。

仅选择性非敏感证据取回`/tmp/fsi-cl-evidence/`，没有取回数据库备份正文或凭据。没有远端发布故障；一次helper生成后的本地检查修正尚未执行的旧TEST常量，不是业务red或生产回滚。

新四应用短观察OOM false/restart0，memory.events max/oom/oom_kill全0。清理后MemAvailable约**4.30GiB**；web348.9MiB、LLM366MiB、fast365.8MiB、beat245.1MiB。下降包含重启效应，不能据此宣布长期容量/泄漏已解决。

本报告及进度收尾是纯文档提交，服务器只ff-only同步，不重启镜像。文档提交的CI按其准确SHA另核对，不用功能CI冒充；发布源代码/image仍330d50b。真正MySQL并发、完整投递恢复、长期压力和真实源留出验收仍属后续。
