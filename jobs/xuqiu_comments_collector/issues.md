# 雪球评论采集问题记录

## 2026-06-09

### 1. CPO板块股票代码解析问题
- **问题**: CPO.md 中股票代码格式为 `名称(代码)`，如 `中际旭创(300308)`，不含SH/SZ前缀
- **影响**: 首次采集只获取了13只laodeng板块股票，遗漏了11只CPO股票
- **解决**: 修改 `collect_xueqiu.py` 的 `load_stock_symbols()` 增加对纯数字代码的解析，自动添加SH/SZ前缀

### 2. Repository字段名不一致
- **问题**: `CommentRepository.insert()` 接受 `likes`（非 `like_count`），首次导入时用了错误字段名
- **影响**: 348条评论导入后 likes=0, symbol=None, created_at=None
- **解决**: 删除错误数据，使用正确字段名重新导入

### 3. 热门动态缺少时间戳
- **问题**: `opencli xueqiu hot` 返回的热门动态没有 `created_at` 字段
- **影响**: 8条热门动态评论的 created_at 为 None
- **状态**: 已知限制，暂无法解决

### 4. 博主个人动态无法直接采集
- **问题**: `opencli xueqiu` 没有按用户ID获取动态的命令（API endpoint `user_timeline.json` 存在但未暴露）
- **影响**: 无法直接获取 xueqiu-finance-up.md 中29位博主的个人发帖
- **可能的解决方案**: 后续可考虑通过 API 直接调用 `v4/statuses/user_timeline.json?user_id=<uid>` 采集博主动态

### 5. 子评论无法采集
- **问题**: `opencli xueqiu comments` 只返回股票下的讨论帖，无法获取帖子下的子评论
- **影响**: 只能采集一级评论，无法获取回复
- **状态**: 当前 opencli adapter 不支持子评论采集

## 2026-06-14

### 6. 定量分析采集
- **结果**: --date 2026-06-14, 29只股票, 1304条stock_comments, 10条hot. 筛选06-12至06-14共707条(612:185, 613:226, 614:296). 导入717条(含10条hot).
- **备注**: 本次为全平台定量分析，时间范围覆盖上个交易日收盘后至周一开盘前
