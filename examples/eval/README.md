# 评测成果示例

Coding-agent 在评测中完成的任务。每个任务挑一次通过的运行，从轨迹重放出最终代码，并用隐藏测试复验。

| 任务 | 复验 | 模型调用 | 输入 tokens | 输出 tokens | 耗时 | 新建/修改的文件 | 评测 |
|---|---|---|---|---|---|---|---|
| [algo_expr_eval](algo_expr_eval/README.md) | ✅ | 14 | 56,743 | 4,552 | 24s | 1 | `20261002-024621-deepseek-flash` |
| [algo_lru_cache](algo_lru_cache/README.md) | ✅ | 12 | 42,812 | 3,648 | 20s | 2 | `20261002-024621-deepseek-flash` |
| [algo_merge_intervals](algo_merge_intervals/README.md) | ✅ | 4 | 6,694 | 626 | 6s | 1 | `20261002-024621-deepseek-flash` |
| [algo_roman](algo_roman/README.md) | ✅ | 8 | 25,955 | 3,371 | 16s | 1 | `20261002-024621-deepseek-flash` |
| [bug_config_types](bug_config_types/README.md) | ✅ | 8 | 19,451 | 1,683 | 10s | 1 | `20261002-024621-deepseek-flash` |
| [bug_shop](bug_shop/README.md) | ✅ | 9 | 23,009 | 1,568 | 9s | 2 | `20261002-024621-deepseek-flash` |
| [bug_stats](bug_stats/README.md) | ✅ | 8 | 17,866 | 1,231 | 8s | 1 | `20261002-024621-deepseek-flash` |
| [debug_csv_report](debug_csv_report/README.md) | ✅ | 6 | 15,603 | 1,792 | 10s | 1 | `20261002-024621-deepseek-flash` |
| [debug_duration_parser](debug_duration_parser/README.md) | ✅ | 11 | 101,473 | 8,816 | 41s | 2 | `20261002-024621-deepseek-flash` |
| [debug_perf_dedupe](debug_perf_dedupe/README.md) | ✅ | 17 | 102,560 | 6,755 | 34s | 1 | `20261002-024621-deepseek-flash` |
| [feature_log_parser](feature_log_parser/README.md) | ✅ | 4 | 9,297 | 1,484 | 7s | 1 | `20261002-024621-deepseek-flash` |
| [feature_todo_cli](feature_todo_cli/README.md) | ✅ | 11 | 35,058 | 2,152 | 15s | 1 | `20261002-024621-deepseek-flash` |
| [js_bug_task_queue](js_bug_task_queue/README.md) | ✅ | 7 | 28,326 | 3,416 | 27s | 2 | `20261011-211649-deepseek-v4-flash` |
| [js_feature_markdown](js_feature_markdown/README.md) | ✅ | 9 | 131,686 | 20,520 | 96s | 2 | `20261011-211649-deepseek-v4-flash` |
| [large_build_ledger](large_build_ledger/README.md) | ✅ | 21 | 623,100 | 35,256 | 171s | 9 | `20261008-144904-deepseek-flash` |
| [large_library_softdelete](large_library_softdelete/README.md) | ✅ | 18 | 244,969 | 11,697 | 56s | 19 | `20261008-144904-deepseek-flash` |
| [large_spec_shop](large_spec_shop/README.md) | ✅ | 33 | 1,223,273 | 48,291 | 312s | 23 | `20261008-163337-deepseek-v4-flash` |
| [long_refactor_logging](long_refactor_logging/README.md) | ✅ | 8 | 32,900 | 3,726 | 15s | 9 | `20261002-024621-deepseek-flash` |
| [long_spec_textkit](long_spec_textkit/README.md) | ✅ | 8 | 68,667 | 12,123 | 48s | 2 | `20261002-024621-deepseek-flash` |
| [multi_inventory_reservations](multi_inventory_reservations/README.md) | ✅ | 17 | 109,774 | 5,378 | 31s | 4 | `20261002-024621-deepseek-flash` |
| [multi_pricing_bugs](multi_pricing_bugs/README.md) | ✅ | 10 | 65,974 | 6,728 | 32s | 4 | `20261002-024621-deepseek-flash` |
| [refactor_rename](refactor_rename/README.md) | ✅ | 5 | 11,347 | 1,150 | 5s | 4 | `20261002-024621-deepseek-flash` |
