# 实现和运行中遇到的问题

## 2026-06-10 初始化

- 创建采集脚本、搜索词列表、SKILL.md
- 数据库 schema 需添加 `zhihu` 到 platform CHECK 约束
- 中国时区偏移: Zhihu created_at 返回 UTC，需要转换为北京时间过滤

## 2026-06-10 首轮采集

- 搜索词26个，命中59个去重答案，其中8个答案有今日评论，共41条评论
- Windows subprocess 中文编码问题: `subprocess.list2cmdline` + `shell=True` 会破坏中文字符，改用 `powershell -NoProfile -Command` 包装解决
- 部分答案无评论 (`EMPTY_RESULT`)，属正常情况
- 图片下载功能已实现但首轮未启用 (`--no-import` 模式排除)
- DB 迁移脚本 (`db/migrate_add_zhihu.py`) 需要手动运行以更新 SQLite CHECK 约束
- [2026-06-10 23:39:41] 采集为空: 0 答案, 无今日评论
- [2026-06-10 23:57:15] 采集成功: 8 答案, 41 评论
