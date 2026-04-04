# Logo Data Engine

`logo_data_engine` 是一個可重跑、可審核、可交付的 logo dataset 建置引擎。  
它把多來源圖片、品牌 ontology、quality gate、GroundingDINO、SAM3、OCR、captioning、Qwen 知識推理，以及人工 review，全部收斂到同一套資料流與 schema。

核心 schema：

- `ImageRecord`
- `LogoInstance`
- `BrandRecord`

可信度狀態用 `tier` 管理：

- `proposal`
- `silver`
- `gold`

## 目錄入口

- CLI: [__main__.py](/raid/ming/logo/logo_data_engine/__main__.py)
- 主流程 script: [run_pipeline.sh](/raid/ming/logo/logo_data_engine/run_pipeline.sh)
- 多品牌批次 script: [run_multibrand_batch.sh](/raid/ming/logo/logo_data_engine/run_multibrand_batch.sh)
- Review UI: [ui_server.py](/raid/ming/logo/logo_data_engine/ui_server.py)
- 安裝腳本: [setup_env.sh](/raid/ming/logo/logo_data_engine/setup_env.sh)
- 依賴: [requirements.txt](/raid/ming/logo/logo_data_engine/requirements.txt)
- JSON 血緣與歸屬表: [JSON_LINEAGE.md](/raid/ming/logo/logo_data_engine/docs/JSON_LINEAGE.md)
- 詳細 PDF/HTML 文件: [data_engine_guide_latex.pdf](/raid/ming/logo/logo_data_engine/docs/data_engine_guide_latex.pdf)

## 快速開始

### 1. 安裝環境

```bash
cd /raid/ming/logo/logo_data_engine
./setup_env.sh logo_sam3
source /home/chiaming/anaconda3/etc/profile.d/conda.sh
conda activate logo_sam3
```

### 2. 跑單次流程

```bash
cd /raid/ming/logo
./logo_data_engine/run_pipeline.sh \
  --run-name quickstart \
  --brands coca-cola \
  --categories mugs \
  --limit 1
```

### 3. 跑多品牌批次

```bash
cd /raid/ming/logo
./logo_data_engine/run_multibrand_batch.sh \
  --run-name batch_500 \
  --target-records 500
```

說明：

- `run_pipeline.sh` 適合單次實驗、外部資料匯入、指定品牌/類別
- `run_multibrand_batch.sh` 適合正式 batch 建集，會先 oversample，再 quality gate，再平衡抽樣到目標筆數
- 兩支 script 都會先自動跑 `preflight`

## 流程總覽

主流程如下：

1. `preflight`
2. `collector`
3. `ontology-fetch-brands`
4. `seed-ontology`
5. `ingest-images`
6. `gate`
7. `segment-sam3`（可選）
8. `phase1-workflow`
9. `review-queue`
10. `export-kb`
11. `analyze-run`（batch）

資料流核心原則：

- 所有資料最後都進 SQLite + 同一套 export schema
- 中間 JSON 檔案都放在 `results/<run_name>/...`
- `proposal -> silver -> gold` 只改狀態，不重構資料表

## 輸出目錄

每次執行輸出到：

```text
/raid/ming/logo/logo_data_engine/results/<run_name>/
```

主要資料夾：

- `meta/`
  存放各步驟的 summary / 中間 JSON / 診斷資訊
- `fetch/`
  存放最終進主流程的 `records.json` 與下載圖片
- `brand/`
  存放 `brand_records.json`
- `segment/`
  存放 SAM3 segmentation JSON / mask / visualization
- `review/`
  存放 reviewer queue
- `export/`
  存放最終 `knowledge_base.json`
- `analysis/`
  存放 run analysis
- `engine/`
  正式 SQLite DB
- `staging/`
  batch 前半段使用的暫存 DB

## 最重要的 JSON 檔

最常用的幾個：

- `meta/raw_records.json`
  collector 原始抓取結果
- `meta/candidate_records.json`
  batch 重平衡後的候選池
- `meta/passed_records.json`
  quality gate 後通過的集合
- `fetch/records.json`
  最終真正進入 annotation / segmentation / export 的資料
- `brand/brand_records.json`
  ontology / brand knowledge
- `segment/records_with_logo_masks.json`
  GroundingDINO + SAM3 結果
- `review/review_queue.json`
  待審核 queue
- `export/knowledge_base.json`
  最終整合輸出

完整檔案血緣請看：

- [JSON_LINEAGE.md](/raid/ming/logo/logo_data_engine/docs/JSON_LINEAGE.md)

## 主要參數

共同常用：

- `--run-name <name>`：輸出到 `results/<name>/`
- `--with-sam3` / `--no-sam3`：開關 SAM3 segmentation
- `--object-first` / `--no-object-first`：先找物件再找 logo
- `--use-vlm` / `--no-vlm`：開關 VLM caption/QA
- `--vlm-model-id <id>`：指定 VLM
- `--use-qwen-qa`：開啟 Qwen 多段式知識/風險推理
- `--qwen-model-id <id>`：指定 Qwen model
- `--skip-detector`：關閉 GroundingDINO proposal detector
- `--skip-ocr`：關閉 OCR
- `--cuda-devices 1,2,3`：指定 GPU

單次流程常用：

- `--brands nike,adidas`
- `--categories shoes,apparel`
- `--all`
- `--limit 4`
- `--collection-root /path/to/images`
- `--manifest /path/to/manifest.json`

批次流程常用：

- `--target-records 500`
- `--oversample-factor 3`

## 關閉特定模組

關閉 SAM3：

```bash
./logo_data_engine/run_pipeline.sh \
  --run-name demo_no_sam3 \
  --brands coca-cola \
  --categories mugs \
  --limit 1 \
  --no-sam3
```

關閉 detector：

```bash
./logo_data_engine/run_pipeline.sh \
  --run-name demo_no_detector \
  --brands coca-cola \
  --categories mugs \
  --limit 1 \
  --skip-detector
```

關閉 OCR：

```bash
./logo_data_engine/run_pipeline.sh \
  --run-name demo_no_ocr \
  --brands coca-cola \
  --categories mugs \
  --limit 1 \
  --skip-ocr
```

## Qwen 知識推理

Qwen 目前不是一次問完整大題，而是多段式推理：

- `grounding`
- `recognition`
- `world_knowledge`
- `risk`
- `ambiguity`

輸出 schema：

- [qwen_logo_intelligence.schema.json](/raid/ming/logo/logo_data_engine/schemas/qwen_logo_intelligence.schema.json)
- [qwen_knowledge.schema.json](/raid/ming/logo/logo_data_engine/schemas/qwen_knowledge.schema.json)
- [qwen_risk.schema.json](/raid/ming/logo/logo_data_engine/schemas/qwen_risk.schema.json)

落地欄位：

- `logo_instances.attribution_json`
- `logo_instances.knowledge_json`
- `logo_instances.risk_json`

## Review UI

啟動方式：

```bash
cd /raid/ming/logo
python -m logo_data_engine.ui_server \
  --db /raid/ming/logo/logo_data_engine/results/<run_name>/engine/logo_engine.db \
  --host 0.0.0.0 \
  --port 8000
```

功能：

- 看原圖
- 看 bbox / mask overlay
- 看 `attribution / knowledge / risk / raw_json`
- 一鍵改成 `proposal / silver / gold / rejected`

## 品牌決策邏輯

目前品牌合併優先順序是：

1. trusted metadata / OCR
2. caption / VLM
3. fallback similarity
4. CLIP retrieval 只做診斷訊號，不主導最終品牌

## 擴充品牌來源

`--all` 會載入擴充品牌 catalog，目前包含：

- US 30 brands
- EU 30 brands
- CN 30 brands
- JP 30 brands
- KR 30 brands

品牌/類別候選表在：

- [multi_brand_fetcher.py](/raid/ming/logo/multi_brand_fetcher.py)

## 開發備忘

- `results/` 內的 JSON 多數可重建，但 `review/` 內容建議保留
- 最終交付建議至少保留：
  - `engine/logo_engine.db`
  - `export/knowledge_base.json`
  - `brand/brand_records.json`
  - `review/review_queue.json`
  - `analysis/summary.json`
- 若要理解某個 JSON 的來源與下游用途，先看 [JSON_LINEAGE.md](/raid/ming/logo/logo_data_engine/docs/JSON_LINEAGE.md)
