## 任务
- 收集社交平台财经博主**近期**发布的**所有视频**里的评论
- **近期**时间范围由用户决定，默认是今天
- 需要下载评论配图

## 社交平台
### B站
- 使用`opencli bilibili`
- 跳过黑名单up主

### 小红书
- 使用`opencli xiaohongshu`命令行
- 使用`mmx-cli`理解笔记和评论图片
- 预设数据`data/xiaohongshu-finance-up.md`
- 注意评论发布时间转化为时间戳

### 雪球
- 使用`opencli xueqiu`命令行
- 预设数据`data/xiaohongshu-finance-up.md`
- 预设数据`data/sections/{CPO,laodeng}.md`

## 输出
0.每个不同平台保存成不同的json结果文件,保存到comments文件夹下
1.配图使用本地链接,备份原始链接
2.中间文件输出到intermediate文件夹下
3.使用backend/SKILL.md更新数据,注意更新like字段

## 注意
0.必须获取到发布评论的日期
1.每次请求间隔1秒以上，防止触发风控
2.不要并发请求
3.获取尽量多的评论
4.尽可能收集子评论
5.注意使用点赞加权