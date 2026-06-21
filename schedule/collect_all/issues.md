# Schedule/collect_all — Issues (2026-06-21)

Time window: 2026-06-19T15:00:00+08:00 ~ 2026-06-23T09:30:00+08:00

## 2026-06-21 22:31 — 知乎 06-19 hang 再次发生,杀死了 run_all 整条流水线

- 同样的"opencli zhihu answer-comments 永久 hang"问题,06-21 这次 900s timeout 后 `subprocess.run` 抛 `TimeoutExpired`,因为 `run_all.py::main()` 没有 try/except 包裹,**直接中断了后续的 import / sentiment / generate_report**,issues.md 也只写到了 header(没机会追加 issue)。
- 处置:本次手动分阶段执行:
  1. `python schedule/collect_all/scripts/run_all.py --import-only`(雪球 275 + 小红书 10 入库,顺带 import 阶段自带的 sentiment 灌进小红书新增 10 条)
  2. `python -u db/update_sentiment.py`(分析新增 275 雪球评论)
  3. 跳过 06-19 知乎(已知 hang、DB 已有 20 条),**直接** `python jobs/zhihu_comments_collector/scripts/collect_zhihu.py --date 2026-06-20` + `--date 2026-06-21`(06-20 0 命中,06-21 100 条入库)
  4. `python -u db/update_sentiment.py`(分析 06-21 知乎 100 条)
  5. `python schedule/collect_all/scripts/generate_report.py --date 2026-06-21 --window-start ... --window-end ...`
- 根因:知乎 `answer-comments` 在某些 answer 上不退出(stdout 不返回);`subprocess.run(timeout=120)` 在子进程里生效,但父进程 `subprocess.run(timeout=900)` 在 15 分钟后整体抛 `TimeoutExpired`。
- 建议修复:
  1. `run_all.py::collect_zhihu` 加 DB 短路:`SELECT COUNT(*) FROM comments WHERE platform='zhihu' AND date(datetime(created_at, '+8 hours'))=target_date` ≥ 1 时 skip 采集(沿用 06-19 现有 20 条即可)
  2. `run_all.py::main()` 改用 `try/except` 包裹每个 step,失败 step 跳过下一 step,确保 import / sentiment / report 总能跑
  3. `run_all.py::collect_zhihu` 每 day 单独 `try/except TimeoutExpired` 容错,某一天 hang 不影响其他日期

## 2026-06-21 22:16 — 雪球采集 22 分钟(limit=100 retry × 29 标的)

- `collect_xueqiu.py --date 2026-06-21 --limit 100` 实际跑了 22 分钟(21:54 → 22:16):其中 2 个标的 (SZ000858 / SZ300750) opencli 报 `Page not found: stale page identity` + `AUTH_REQUIRED` 触发 2x60s 重试,把单标的耗时从 1.5s 拉高到 120s;`--limit` 实际未生效(`collect_xueqiu.py` 的 main 只把 `--limit` 写到 stdout,不传给 opencli),所以增量主要是 1.5s × 29 ≈ 45s + 失败重试 ~5 分钟。
- 结果:269 今日 / 267 来自非博主 / 2 博主;中间文件 `xueqiu_2026-06-21.partial.json` 531KB;最终 275 条入库(DB 06-19 15:00 ~ 06-23 09:30 窗口 969 条 xueqiu 评论)。
- 处置:本次采集器未做改动(沿用 06-20 相同的 22 分钟开销)。
- 建议:把 `collect_xueqiu.py` 的 `--limit` 真的传 `opencli xueqiu comments` (`--limit` 已经传入,问题在于 step3 整理时只保留 "今日"评论,limit 增大主要是抓更多前几日评论,实际有效率有限;但仍可避免 29 个 opencli 串行调用时雪球风控触发 stale page)

## 2026-06-21 21:48 — B 站 `import_to_db.py` 自带 `SentimentAnalyzer` 跑 144 条分析(成功)

- 不同于 06-19 之前版本,目前 `bilibili_collect_today.py` 自带 `SentimentAnalyzer`,本批 144 条新评论情绪全部分析成功(0 pending)。
- B 站窗口内 311 条(2026-06-19 15:00 ~ 2026-06-23 09:30),平均得分 0.402(偏多),正面 35.0%,负面 10.9%。

## 2026-06-21 22:08 — 小红书 18/29 博主 `Malformed user snapshot: user store was not found`(沿用 06-20 问题)

- `opencli xiaohongshu user` 在 18/29 个博主上报 `Malformed Xiaohongshu user snapshot: user store was not found`,无法绕过。
- 本次窗口内新增 10 条入库(其中 06-20 笔记 4 条评论,06-21 笔记 2 条评论,其他日期 0 命中);平均得分 0.409(偏多),正面 36.4%,负面 0.0%。

## 结果概览(窗口 2026-06-19 15:00 ~ 2026-06-23 09:30 CST)

| 平台 | 入库(窗口内) | 正面% | 中性% | 负面% | 平均得分 |
|------|--------|-------|-------|-------|----------|
| bilibili | 311 | 35.0% | 54.0% | 10.9% | 0.402 |
| xiaohongshu | 44 | 36.4% | 63.6% | 0.0% | 0.409 |
| xueqiu | 969 | 29.2% | 46.1% | 24.7% | 0.041 |
| zhihu | 116 | 12.9% | 47.4% | 39.7% | -0.226 |
| **合计** | **1440** | **29.4%** | **48.5%** | **22.2%** | **0.109** |

- 综合得分 0.109 → 整体偏多(差值 7.2 个百分点),较 06-19 的 0.144 略低但仍正向。
- B 站 311 条(比 06-20 的 167 条多 144 条新采集),正面 35.0% 较上次 39.5% 微降但仍偏多。
- 雪球 969 条(本次新采集 275 条入库),平均得分 0.041 维持微正。
- 知乎 116 条(本次新采集 100 条),39.7% 负面 — 显著拉低整体得分,符合"知乎偏空"的常见模式。
- 小红书 44 条(本次新增 10 条入库,小样本 0% 负面,继续偏多)。

详细报告:`schedule/collect_all/output/sentiment-report-2026-06-21.{md,xlsx,html}`
汇总 JSON:`schedule/collect_all/output/sentiment-summary-2026-06-21.json`
