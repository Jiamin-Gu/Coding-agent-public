# SWE-bench Lite 子集

10 道来自 pytest、flask 的真实 issue（依赖轻、测试不需要联网），环境在 Docker 沙箱里搭建，agent 只看到 issue 描述，修完后套上官方测试补丁判分。每道题的目录里有各模型交出的补丁。

| 题目 | deepseek-v4-flash | kimi-k2.7-code | glm-5.2 | qwen3.7-plus | minimax-m3 |
|---|---|---|---|---|---|
| [pallets__flask-4992](pallets__flask-4992/README.md) | ✅ | ✅ | ❌ | ❌ | ❌ |
| [pallets__flask-5063](pallets__flask-5063/README.md) | ✅ | ❌ | ✅ | ❌ | ✅ |
| [pytest-dev__pytest-11143](pytest-dev__pytest-11143/README.md) | ✅ | ✅ | ✅ | ✅ | ✅ |
| [pytest-dev__pytest-11148](pytest-dev__pytest-11148/README.md) | ✅ | ✅ | — | ✅ | ✅ |
| [pytest-dev__pytest-7373](pytest-dev__pytest-7373/README.md) | ✅ | — | — | ✅ | — |
| [pytest-dev__pytest-7432](pytest-dev__pytest-7432/README.md) | ✅ | — | — | ✅ | — |
| [pytest-dev__pytest-7490](pytest-dev__pytest-7490/README.md) | ✅ | — | — | — | — |
| [pytest-dev__pytest-8365](pytest-dev__pytest-8365/README.md) | ✅ | — | — | — | — |
| [pytest-dev__pytest-8906](pytest-dev__pytest-8906/README.md) | ✅ | — | — | — | — |
| [pytest-dev__pytest-9359](pytest-dev__pytest-9359/README.md) | ✅ | — | — | — | — |
| **解决 / 已跑** | **10/10** | **3/4** | **2/3** | **4/6** | **3/4** |

“—”表示这道题还没有这个模型的有效结果（没跑到，或者运行被服务商的额度限流打断）。
