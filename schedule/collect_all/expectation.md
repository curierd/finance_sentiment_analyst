# 任务
1,确定全平台登陆状态
2.定量分析全平台评论并入库，注意收集配图
- 先按like加权平均单个视频评论的score,再按视频热度加权平均score作为平台得分
- 视频/笔记热度定义：视频/笔记的播放量+评论量+点赞量
3.时间范围
- 查看各个平台最新评论时间，然后收集至今的所有评论

## skills
- jobs\bilibili_comments_collector\SKILL.md
- jobs\xiaohongshu_comments_collector\SKILL.md
- jobs\xuqiu_comments_collector\SKILL.md
- jobs\zhihu_comments_collector\SKILL.md
- 使用`jobs\sentiment_analyzer\SKILL.md`分析评论情绪

## 输出
1.脚本放到scripts里，中间文件放在intermediate里
2.本次定量分析报告`excel`和`html`

## 实现和运行中遇到问题
- 记录到`issues.md`中