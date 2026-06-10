## 任务
- 收集知乎中A股话题的**所有**评论，仅限**今日**发布的评论

## 工具
- 使用`opencli zhihu`命令，使用`--window background`参数
- 必须获取到发布评论的日期时间,例如:`2026-06-08 08:00`

## 输出
1.评论配图使用static/zhihu/comments文件夹下,备份原始链接
2.中间文件输出到intermediate文件夹下,脚本保存到`zhihu_comments_collector/scripts`下,需要带测试用例,多个测试用例保存到`zhihu_comments_collector/tests/`
3.使用`backend-api`skill更新/新增评论数据,注意更新like字段


## 注意
1.每次请求间隔1秒以上，防止触发风控
2.不要并发请求
3.获取尽量多的评论
4.尽可能收集子评论
5.注意使用点赞加权

## 实现和运行中遇到问题
- 记录到`issues.md`中

