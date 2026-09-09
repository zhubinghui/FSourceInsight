# M2-A：通过后台HTTP保存候选（本地切片）

后续：[M2-B1后台预览](2026-09-08-m2b1-admin-preview.md)也已本地完成；本报告保留A切片交付时的范围与测试证据，不代表当前只剩保存功能。

## 结论与范围

用户选择后台HTTP作为M2主要验收入口。已完成**保存候选 → 独立请求重读 → 查看历史版本**的第一条纵向切片，不另建测试API。

- 基于`4477cfd`工作区，保留此前架构/规划文档改动；本轮未提交、推送、SSH或部署。
- **不是整个M2完成**：尚无policy编辑、active/previous、预览/批准/拒绝/回滚、证据库、自动schema路由、lease/fencing、outbox或统一调度。
- 已有生产M1应用与数据库均未操作。不能去生产期待本次新页面已经可用。

## 用户可见功能

1. 来源列表增加`Crawl config`链接。
2. `GET/POST /admin/sources/<source_id>/crawl-config`展示候选列表或保存合法recipe。
3. `GET /admin/sources/<source_id>/crawl-config/versions/<version_id>`展示规范化规则、指纹、创建管理员/UTC时间、base generation与candidate状态。
4. 每次保存创建新版本，现有HTTP没有覆盖旧版本的操作；跨source访问版本返回404。
5. 页面明确说明仅保存候选，尚未验证/批准、不用于定时抓取。**“No active recipe”是本切片没有发布能力的说明，不表示已实现完整active指针状态机。**
6. 保存不访问新闻网站、不生成Article、不派Celery消息、不调用模型；旧registry/任务路由完全未改。

输入通过真正的M1 `validate_recipe()`，不mock自家校验：拒绝非法/重复key/超深/超大JSON、source不匹配、recipe越权字段；表单拒绝服务端元数据与重复recipe。页面继承父Admin权限/CSRF，JSON经Jinja转义，配置页/详情/响应均no-store、no-referrer。

## 数据与事务

- 新增`crawl_source_profile`：source归属、唯一source约束、generation。
- 新增`crawl_schema_version`：profile关联、recipe JSON/hash、base generation、candidate状态、创建管理员/时间。
- 当前“不可变”指现有业务HTTP只能新建版本、不能改写旧内容；没有数据库触发器级的防管理员SQL改写保证，也没有发布状态机。
- profile与candidate在同一次保存事务。数据库异常rollback并返回固定503/日志码，不打印SQLAlchemy错误中的私有recipe参数。
- commit前flush并保存返回ID，成功重定向不依赖commit后的ORM刷新；commit结果不确定时不声称一定没有保存。
- 新迁移`a731c9e25d80`下接e6，只创建两表与索引/FK，不回填来源、不改Article/旧日志/模型配置。downgrade主动拒绝，应用回退保留候选历史。
- 并发首次创建档案由唯一约束保护；冲突可能返回503让调用者重试。未声称CAS发布、运行认领或完整MySQL并发验收已经完成。

## TDD证据

| 行为 | 首轮观察 | 结果 |
|---|---|---|
| 后台保存并跨请求读取 | POST 404而非302 | 路由/存储/模板后通过 |
| 从来源列表发现入口 | 链接不存在 | 加入真实业务链接后通过 |
| 拒绝伪造服务端字段 | 6种字段被忽略，仍302 | 显式拒绝，400/零候选 |
| 拒绝重复recipe表单项 | 取第一项并302 | 拒绝多值歧义 |
| 敏感页面缓存/Referrer保护 | 响应头缺失 | 两种页面及重定向均受控 |
| SQL写失败可恢复且不泄密 | 真实SQLite trigger产生IntegrityError，私有参数进入异常 | 固定503/rollback，独立请求重读与重试通过 |
| commit后DB不可读 | 已保存却因ORM刷新返回503 | commit前保存ID，成功响应无额外读取 |
| MySQL迁移SQL应新增存储 | e6→head无CREATE TABLE | 新增迁移后通过 |

匿名/普通用户、CSRF、既有schema坏输入、XSS转义、历史版本保留、跨源绑定通过既有/首切片实现，**不冒充新red**。

SQLite迁移测试的首次downgrade断言误读`result.exception`（Flask-Migrate返回SystemExit(1)）；先记录计划偏差，再改从CLI output核对拒绝原因。不是迁移业务失败，未修改迁移来迁就测试。

## 验证结果

- **26项后台HTTP测试**：真实登录/CSRF/来源管理/候选操作；通过新的Flask应用上下文重读，避免复用ORM缓存/旧事务假装持久化。
- **2项候选迁移测试**：MySQL离线SQL；SQLite最小依赖旧库的行保留、唯一/FK约束、拒绝downgrade。后者不等于完整历史MySQL升级。
- 全套：**487 passed / 13 skipped / 2214 warnings，143.57秒**。13项是需要独立MySQL的专用用例，不是本轮通过。
- 新增MySQL HTTP候选回读用例（含é/汉字/四字节字符），迁移HEAD同步a731；环境未提供，**尚未实跑**。既有M1的12项历史成功不外推到本次改动。
- 152个Python AST、42个模板编译、指定flake8错误集、`git diff --check`通过；Alembic单head为a731。
- 新增业务测试合计28项离线通过，另1项MySQL待跑；相对原459/12为487/13。

执行命令：

```bash
env -i PATH='/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin' \
  HOME="$HOME" PYTHONDONTWRITEBYTECODE=1 \
  /tmp/fsource-audit-1XQuAg/venv/bin/python -m pytest tests/ \
  -q --disable-warnings -p no:cacheprovider --tb=short
```

完整测试输出位于本地`/tmp/fsi-m2a-tests.log`，不含生产数据。

## 代码与下一步

- [后台操作](../../app/web/views/crawl_config.py)
- [存储模型](../../app/models/crawl_schema.py)
- [迁移](../../migrations/versions/a731c9e25d80_crawl_schema_candidates.py)
- [HTTP验收](../../tests/test_web/test_crawl_config.py)
- [运维验收](../../tests/test_ops/test_crawl_candidate_migration.py)
- [M2细化计划](../superpowers/plans/2026-09-07-m2-versioned-runtime.md)

下一切片仍以真实HTTP为入口：管理员明确设置受控policy、运行只读preview、查看质量/样本；随后才是人工审批/CAS。发布能力与日常可靠运行未实现之前，不把当前切片单独部署为“完整动态爬虫”。
