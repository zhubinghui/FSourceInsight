# Ecosystem 地图：现状校验与需求（2026-09-19）

状态：**只读审计，未改任何代码或数据**。逐条判定表见
`docs/audits/data/2026-09-19-ecosystem-validation.csv`（746 行）。

## 1. 数据来源与方法

- 线上数据（v1）：最初 SSH 只读 SQL 被会话权限策略拒绝，先抓取公开页面
  `https://fsourceinsight.eu/companies/`（地图，746 家）和 `?view=list` 262 页（全库 7835 家）。
  v2 在用户明确授权后补做了生产库只读 SQL（见 §2），两者总数一致。
- 仓库数据：`scripts/seed_companies.py`（43）、`scripts/data/grenoble_ecosystem.json`（509，含前者）。
- 外部事实：fixture 中 390 家的 `website` 是 Minalogic 会员目录页；逐页抓取并解析了
  地址/邮编、Type of Organization、成立年份、Themes（359 家有地址，31 家页面无地址）。
- 限制：Minalogic 地址是会员登记地址（通常是总部），公司可能在 Grenoble 另有站点；
  Linksium/CEA 来源的 75 家和生产新增的约 40 家未做外部核验；`spinoff_origin` 未核验。

## 2. 校验结果（v2：生产库只读导出 + 已确认的范围决定）

v2 更新：用户授权后对生产库做了只读 SQL（`company` / `sector_group` / `startup_source`，READ ONLY 事务，导出留在会话 scratchpad，未入库）。
总数与公开页面一致：全库 7835 家，`is_grenoble=1` 746 家，`is_auto_created=1` 7792 家。746 家中只有 43 家有 `headquarters`，420 家的 `website` 是 Minalogic 目录页（全部已抓取核验），218 家无 website。

已确认的决定（2026-09-19）：
1. 范围 = **Isère 省（38）**，不限 Grenoble 盆地。
2. 总部在外地但在 Isère 有站点的公司**保留**。
3. 学校和科研机构**单独成组**。
4. 授权生产库只读 SQL。

| 判定 | 数量 | 含义 |
|---|---|---|
| DELETE_JUNK | 199 | 页面碎片被存成 research_institute（按月：4 月 122、5 月 11、6 月 10、7 月 17、8 月 34、9 月 13 —— 仍在持续产生）+ 2 条 Minalogic 垃圾 |
| UNFLAG_ISERE | 232 | Minalogic 登记地址不在 Isère。**执行前需逐条确认在 Isère 没有站点**（决定 2） |
| KEEP | 197 | 地址在 Isère，或 43 家人工 seed |
| KEEP_UNVERIFIED | 75 | Linksium/CEA 来源，未做外部核验 |
| REVIEW | 43 | 无地址 / 邮编与城市矛盾 / 生产新增未核验 / 真实名称但类型错误（Floralis、TIMC、TECHTERA…） |

CSV 新增 `entity_type_proposed` 列（来自 Minalogic 的 Type of Organization）：company 338、corporate 27、research_education 27、ecosystem_support 37（银行、律所、地方政府、CCI、集群），其余待定。

**漏标**：`docs/audits/data/2026-09-19-isere-missing-candidates.csv` 列出 31 个在库、有文章、但 `is_grenoble=0` 的 Isère 实体
（Inovallée 58 篇、SPINTEC 29、Université Grenoble Alpes 25、Institut Néel 18、Verkor 9、HRS 9、Vencorex 10…）。
注意：该表的地点来自模型常识而非外部核验，`confidence` 列已标注，执行前需复核。

**生产发现来源**：26 个 `startup_source` 全部 active；其中 23 个是 `research_lab`（含后来在 Admin 添加的 carnot、uga-floralis、MIAI、UGA news、invest grenoble alpes）——这些就是垃圾的来源。

**NER 质量（地图之外）**：文章数最多的"公司"是媒体自身（FW.MEDIA 392、Maddyness 357、Silicon.fr 307、VIPress.net 274），
另有产品/法规/人名被当作公司（ChatGPT、Kubernetes、NIS2、AI Act、Elon Musk、"Mentioned" 17 篇）。

分类问题：
- 192 家 `company_stage=startup` 与事实不符（银行、律所、Métropole、大学、CHU、Huawei、Thales、Capgemini、KPMG…；或 2014 年前成立的 SME）。
- "Semiconductor" 组 159 家，其中 61 家的 Minalogic Themes 不含微纳电子（EURONEXT、POMA、VOGO、Leyton、Grenoble Ecole de Management…）。**更正（同日）**：最初归因于 `_infer_sector` 平票取第一项 Semiconductor，用 Minalogic Themes 对 311 家做了检验后不成立——平票归为 Semiconductor 的 43 家里 32 家确有 Microelectronics 主题（74%），明确命中的 77 家里 48 家（62%），平票并不更差。Themes 是会员自选的多选标签，只是粗参照。更可能的原因是初始分析只有公司名作输入、prompt 带 "Grenoble semiconductor cluster" 框架而产生的幻觉文本（未单独验证）。因此未改推断逻辑。
- "Uncategorized" 145 家（sector 为空，或 `Robotics / Automation`、`IT Services` 等无关键词匹配）。
- 子串匹配导致错分：`MedTech / AI` → AI & Computing（Diabeloop、Pixyl）；Manpower → Energy；Legal Insight → IoT。
- 线上存在一个名称损坏的分组 `Embodied AI & Roboticsgrid`（仅 Yona Robotics）。
- 重复 24 条：Microlight 3D/MICROLIGHT3D、Orioma/ORIOMA SAS、Lancey Energy Storage/Lancey Storage Energy、Dolphin Design/Dolphin Semiconductor、eLichens/Lichens、Innova/Innova Advanced Technologies、Inria/Inria Grenoble、Schneider Electric/…Industries、CEA-Leti/CEA Grenoble、Torso da Livorno/Livourno。
- 655/746 家没有任何关联文章。
- **漏标（已确认）**：Grenoble 地区重点公司在全库里存在、有文章，但 `is_grenoble=False` 所以不在地图上：Verkor（9 篇）、HRS（9 篇）、Renaissance Fusion（2）、Waga Energy（2）、Air Liquide Advanced Technologies（Sassenage）。地图上 88% 的卡片 0 篇文章，而真正有新闻的本地公司反而缺席。
- 全库 NER 表也有垃圾，例如公司名为 "The post Entre Hugging Face et NVIDIA… appeared first on Silicon.fr."。7089 家非地图公司本次未逐条校验。

## 3. 收集逻辑现状（根因）

1. **没有"是否 Grenoble"的判断**：`startup_discovery.py:227` 与 `seed_grenoble_ecosystem.py:56-58,77` 硬编码 `is_grenoble=True`；
   后者每次运行还会把管理员取消的标记重新打上。模型里只有自由文本 `headquarters`（466/509 为空），没有城市/邮编。
2. **没有实体类型**：startup 类来源抓到的一律 `stage='startup'`，research_lab 来源一律 `research_institute`。
3. **抽取策略产生垃圾**：策略 3（`^Name[,:] description` 正则，`startup_discovery.py:119-151`）把任意页面文本当公司；
   对 17 个实验室主页每天 02:30 扫描、每源最多新增 20 条 → 线上已积累约 200 条垃圾，且删除后会被重新发现（无 tombstone/blocklist）。
   链接策略把目录页 URL 存为 `website`，AI Refresh 又把它当作"公司官网"喂给模型。
4. **无审核门**：发现即公开上地图，先于分析、无 pending/approved 状态。
5. **sector 是自由文本，三套词表**（seed 36 种、`_infer_sector` 10 种、SectorGroup 9 种），靠子串关键词对齐，顺序敏感。
6. **初始分析几乎没有证据**（只有名称），产生幻觉（"Thales 总部位于格勒诺布尔"），sector 又从幻觉文本推断。
7. **NER 新公司永远不上地图也不被分析**；本地新创公司从新闻里出现后无法自动进入地图。
8. 去重只有精确 slug/alias；合并丢失 sector/HQ/analysis；seed 别名过宽（"CEA"、"UGA"、"ST"、"HP"）。
9. 自动刷新整体覆盖 `ai_analysis`（与 prompt 承诺的"空值保留旧值"相反）。
10. 无任何测试覆盖地图分组、`_infer_sector`、发现抽取质量；仓库跟踪了完整 SQL dump `scripts/data/fsourceinsight_full.sql.gz`（违反 CLAUDE.md）。

## 4. 需求（建议）

**R1 数据清理（一次性，需备份 + 授权后执行）**：按 CSV 执行 DELETE_JUNK / UNFLAG / 合并重复 / 修正 stage；执行前先停用 research_lab 来源的扫描，否则垃圾次日重现。

**R2 模型**：新增 `city`、`postcode`、`entity_type`（startup / sme / corporate / research_lab / university / cluster / public_body / investor / service）、
`review_status`（pending / approved / rejected / hidden）、`location_evidence_url`；`sector` 改为 SectorGroup 外键（或受控枚举）；rejected 作为 tombstone 阻止重新发现。

**R3 地域判定规则**：范围为 Isère（邮编 38xxx）或在 Isère 有站点（`local_site`），证据来自目录页或官网，不再硬编码。

**R4 发现流程**：去掉策略 3；research_lab 来源不再产生公司；抓取目录详情页取地址/类型/官网；新实体进入 pending，不直接上地图；地图只显示 approved。

**R5 分类**：单一词表；LLM 分类需带证据（官网摘录/目录 Themes），去掉 prompt 中的 Grenoble-semiconductor 框架；保留人工覆盖优先。

**R6 NER → 地图通路**：NER 新公司若文章上下文显示位于 Isère，进入 pending 审核队列。

**R7 去重**：规范化名称（法律后缀、大小写、空格、词序）候选提示；合并时字段级保留。

**R8 测试**：地图分组、词表一致性、抽取夹具、fixture 完整性；seed loader 不得覆盖管理员修正。

## 5. 分组方案（按决定 3）

- 行业分组（现有 9 个）只放 `entity_type in (company, corporate)`。
- 新增分组 **Schools & Research**（学校和科研机构）：`entity_type = research_education`，替代现在混杂的 "Research & Ecosystem"。
- 修复/删除名称损坏的 `Embodied AI & Roboticsgrid`（id 11）；`Uncategorized`（id 10）不应作为真实分组存在。

## 6. 仍待确认

1. 银行、律所、地方政府、CCI、集群（`ecosystem_support`，37 家）：决定 3 只提到学校和科研机构。这一类是放进同一组、另设 "Ecosystem support" 组，还是从地图隐藏？
2. 232 家 UNFLAG_ISERE 的"本地站点"核验方式：人工过一遍，还是先全部取消标记、之后按新闻证据加回？

## 7. 执行记录（2026-09-19）

决定：UNFLAG_ISERE 采用"先全部取消标记，之后按新闻/官网证据加回"；清理前先停用 23 个 `research_lab` 发现来源。

- 20:18 UTC：一次性全库备份 `~/fsourceinsight-backups/eco-20260919*/full.sql.gz`（0600，19.9MB，gzip 校验通过，dump 完整结束）。
- **发现：每日备份自 2026-05-13 起失效**。cron 仍指向 `/home/ubuntu/backup_fsourceinsight.sh`，该文件已不存在，
  `/var/log/fsourceinsight-backup.log` 每天记录 `not found`。之后只有各次发布时的手工备份目录（最近 `cl-20260911084734`）。需要单独修复。
- 停用 research_lab 来源：**未执行**。通过 SSH 在 web 容器内用 ORM 写入被会话权限策略（Remote Shell Writes）拒绝，未绕过。
  待用户自行执行（Admin → Ecosystem Sources 逐个取消 Active，或在会话中用 `!` 运行等价命令）。生产数据至此无任何改动。
