# 第 6 章 · Agent 的評估

> 把表現變成可比較訊號：評估環境、指標、統計顯著性、評估驅動選型

← [返回主目錄](../docs/zh-TW/README.md) · 📖 [讀本章正文](../book/chapter6.md)

## 配套專案

| 專案 | 型別 | 一句話說明 |
| --- | :--: | --- |
| `terminal-bench/` | 📖 | 測試 Agent 在真實終端機環境的端到端能力（編譯/訓練/部署），約 100 任務 + 執行框架 |
| `SWE-bench/` | 📖 | 評估 LLM 解決真實 GitHub 問題的能力，含 SWE-bench/Lite/Verified/Multimodal 多個版本 |
| `GAIA/` | 📖 | 評估下一代 LLM 的工具/搜尋/自主能力，450+ 個答案明確的非平凡問題，分 3 級難度 |
| `OSWorld/` | 📖 | 評估 Agent 在完整 OS 環境執行複雜任務的能力：檔案管理、應用操作、系統設定 |
| `android_world/` | 📖 | 評估 Agent 在 Android 環境的應用導覽、UI 互動與任務完成能力 |
| `tau2-bench/` | 📖 | 專注評估 Agent 使用工具進行複雜推理（計算、搜尋、資料處理）的能力 |
| [elo-leaderboard](elo-leaderboard/) | ✅ | 基於 ELO 評分的 Agent 效能排行榜，透過對戰比較相對能力 |
| [model-benchmark](model-benchmark/) | ✅ | 對多家 OpenAI 相容 API 橫向壓測 TTFT、p50/p95 延遲、吞吐與成功率，一條命令出對比表 |
| [agent-cost-analysis](agent-cost-analysis/) | ✅ | 多輪 Agent 任務（客服退款）全鏈路成本拆解 + KV-cache 友善設計/上下文壓縮的 A/B 節省量化 |
| [tts-quality-eval](tts-quality-eval/) | ✅ | 多種 TTS 設定合成挑戰文字，LLM-as-a-Judge 按 Rubric 逐維度打分，輸出可復現對比表 |

> 📖 第 6 章全部為外部評測基準倉庫，克隆命令見文末《附錄 · 外部倉庫取得》。[`chapter6/android-world/`](android-world/)（連字號命名）並非基準程式碼，而是本書對 T3A Agent 在 android_world 上失敗案例的分析筆記（`t3a*.md`），可作為閱讀材料參考。

## 專案型別說明

| 圖示 | 型別 | 含義 |
| :--: | --- | --- |
| ✅ | **可獨立執行** | 本倉庫自帶完整程式碼，設定好 API Key 即可執行 |
| 📖 | **復現指南** | 依賴需自行 `git clone` 的**外部倉庫**（訓練框架、評測基準等） |
| 🚧 | **設計文件** | 僅包含架構與實現方案，可執行程式碼仍在完善中 |
