# JSON Lineage and Ownership

這份文件用來回答三件事：

1. 這個 JSON 是誰產生的
2. 下一步誰會讀它
3. 它是暫存、中間產物，還是交付物

## Run Root

所有 run 結果都在：

```text
/raid/ming/logo/logo_data_engine/results/<run_name>/
```

## 一覽表

| Path | Producer | Primary Owner | Consumed By | Stage | Type |
|---|---|---|---|---|---|
| `meta/preflight.json` | `preflight` | runtime/model-check | human, debugging | pre-run | diagnostic |
| `meta/collector.json` | `collector-*` wrapper output | collector | human, debugging | collect | diagnostic |
| `meta/ontology.json` | `ontology-fetch-brands`, `seed-ontology` wrapper output | ontology | human, debugging | ontology | diagnostic |
| `meta/segment.json` | `segment-sam3` wrapper output | segmentation | human, debugging | segment | diagnostic |
| `meta/phase1.json` | `phase1-workflow` wrapper output | workflow | human, debugging | annotate/review | diagnostic |
| `meta/export.json` | `export-kb` wrapper output | export | human, debugging | export | diagnostic |
| `meta/summary.json` | `summary` wrapper output | db/export | human | final | diagnostic |
| `meta/batch_plan.json` | `batch-plan` | batch planner | `run_multibrand_batch.sh` | batch planning | intermediate |
| `meta/raw_records.json` | `collector-fetch-products --all` | collector | `balance-records`, ontology | collect | intermediate |
| `meta/candidate_records.json` | `balance-records` | batch balancer | ontology, ingest, gate | candidate pool | intermediate |
| `meta/passed_records.json` | `export-image-records --quality-status passed` | quality gate | `balance-records` | post-gate | intermediate |
| `fetch/records.json` | collector direct or post-balance final set | fetch set owner | `phase1-workflow`, `segment-sam3`, export lineage | final input set | core |
| `brand/brand_records.json` | `ontology-fetch-brands` | ontology | `seed-ontology`, `phase1-workflow`, `segment-sam3` | ontology | core |
| `segment/records_with_logo_masks.json` | `segment-sam3` | segmentation | `phase1-workflow --segment-records` | segment | core |
| `review/review_queue.json` | `review-queue` | human review | reviewer, `review-apply` | review | core |
| `export/knowledge_base.json` | `export-kb` | export/schema | downstream training, analytics, delivery | export | deliverable |
| `analysis/summary.json` | `analyze-run` | reporting | dashboards, human | analysis | deliverable |
| `analysis/analysis.md` | `analyze-run` | reporting | human | analysis | deliverable |

## 血緣圖

### `run_pipeline.sh`

```text
preflight
  -> meta/preflight.json

collector
  -> fetch/records.json
  -> fetch/images/
  -> meta/collector.json

ontology-fetch-brands
  -> brand/brand_records.json
  -> meta/ontology.json

segment-sam3 (optional)
  -> segment/records_with_logo_masks.json
  -> segment/masks/
  -> segment/visualizations/
  -> meta/segment.json

phase1-workflow
  consumes:
    fetch/records.json
    brand/brand_records.json
    segment/records_with_logo_masks.json (optional)
  writes:
    engine/logo_engine.db
    review/review_queue.json
    meta/phase1.json

export-kb
  consumes:
    engine/logo_engine.db
  writes:
    export/knowledge_base.json
    meta/export.json

summary
  -> meta/summary.json
```

### `run_multibrand_batch.sh`

```text
preflight
  -> meta/preflight.json

batch-plan
  -> meta/batch_plan.json

collector-fetch-products --all
  -> meta/raw_records.json
  -> fetch/images/
  -> meta/collector.json

balance-records
  raw_records.json -> candidate_records.json

ontology-fetch-brands
  candidate_records.json -> brand/brand_records.json

seed-ontology + ingest-images + gate
  candidate_records.json -> staging/logo_engine.db

export-image-records --quality-status passed
  staging/logo_engine.db -> meta/passed_records.json

balance-records
  passed_records.json -> fetch/records.json

segment-sam3 (optional)
  fetch/records.json -> segment/records_with_logo_masks.json

phase1-workflow
  fetch/records.json + brand/brand_records.json + segment records(optional)
  -> engine/logo_engine.db
  -> review/review_queue.json
  -> meta/phase1.json

export-kb
  engine/logo_engine.db -> export/knowledge_base.json

analyze-run
  -> analysis/analysis.md
  -> analysis/summary.json

summary
  -> meta/summary.json
```

## 每個 JSON 的具體歸屬

### `meta/preflight.json`

- Owner: runtime / model activation layer
- 目的: 確認模型是否能載入
- 典型內容:
  - `grounding_dino.available`
  - `paddleocr.available`
  - `sam3.available`
  - `vlm.available`
  - `qwen_qa.available`
- 是否交付: 否
- 是否可重建: 是

### `meta/raw_records.json`

- Owner: collector
- 來源: 大量抓取後的原始候選
- 特性:
  - 可能重複
  - 尚未經過 quality gate
  - 尚未平衡
- 下游:
  - `balance-records`
  - `ontology-fetch-brands`
- 是否交付: 否
- 是否可重建: 是

### `meta/candidate_records.json`

- Owner: batch planner / balancer
- 來源: `raw_records.json` 平衡後候選池
- 特性:
  - 比 `raw_records.json` 更接近正式樣本
  - 尚未經過最終 gate 篩選
- 下游:
  - `ontology-fetch-brands`
  - `ingest-images`
- 是否交付: 否
- 是否可重建: 是

### `meta/passed_records.json`

- Owner: quality gate
- 來源: DB 中 `quality_status = passed` 的 image records 匯出
- 特性:
  - 是 batch 抽最終集之前的「乾淨池」
  - 還不是最終交付集
- 下游:
  - `balance-records`
- 是否交付: 否
- 是否可重建: 是

### `fetch/records.json`

- Owner: fetch set / final input set
- 來源:
  - 單次流程：collector 直接產生
  - 批次流程：由 `passed_records.json` 再平衡產生
- 特性:
  - 真正送進 `phase1-workflow` 的圖片集合
  - 是最重要的輸入 JSON 之一
- 下游:
  - `segment-sam3`
  - `phase1-workflow`
- 是否交付: 建議保留
- 是否可重建: 通常可以，但不建議只留上游後刪掉它

### `brand/brand_records.json`

- Owner: ontology
- 來源: `ontology-fetch-brands`
- 特性:
  - 包含 brand id、顯示名稱、knowledge、aliases、country、industry 等
- 下游:
  - `seed-ontology`
  - `phase1-workflow`
  - `segment-sam3` prompt context
- 是否交付: 建議保留
- 是否可重建: 可以，但 ontology 是知識資產，建議保留版本

### `segment/records_with_logo_masks.json`

- Owner: segmentation
- 來源: `segment-sam3`
- 特性:
  - 含 object-first / logo grounding / mask 路徑 / visualization 路徑
  - 是 SAM3 結果的主 JSON
- 下游:
  - `phase1-workflow --segment-records`
  - reviewer / debug
- 是否交付: 建議保留
- 是否可重建: 取決於模型與環境，建議保留

### `review/review_queue.json`

- Owner: human review
- 來源: `review-queue`
- 特性:
  - reviewer 操作入口
  - 不是原始模型輸出，而是 DB 中 logo instances 的待審核視圖
- 下游:
  - `review-apply`
  - UI reviewer
- 是否交付: 建議保留
- 是否可重建: 可以，但如果人工已做編輯，應保留

### `export/knowledge_base.json`

- Owner: export/schema layer
- 來源: `export-kb`
- 特性:
  - 整合 `image_records + logo_instances + brand_records`
  - 是目前最重要的對外交付 JSON
- 下游:
  - 模型訓練
  - 資料分析
  - 標註平台
  - 知識查詢
- 是否交付: 是，主要交付物
- 是否可重建: 可以，但建議視為正式輸出保存

### `analysis/summary.json`

- Owner: reporting
- 來源: `analyze-run`
- 特性:
  - 整批 run 的統計摘要
  - 適合 dashboard / 追蹤實驗
- 是否交付: 是，輔助交付物
- 是否可重建: 是

## 可刪 / 建議保留

建議保留：

- `engine/logo_engine.db`
- `fetch/records.json`
- `brand/brand_records.json`
- `review/review_queue.json`
- `segment/records_with_logo_masks.json`（如果有跑 segmentation）
- `export/knowledge_base.json`
- `analysis/summary.json`

通常可刪但可重建：

- `meta/preflight.json`
- `meta/collector.json`
- `meta/ontology.json`
- `meta/phase1.json`
- `meta/export.json`
- `meta/summary.json`
- `meta/batch_plan.json`
- `meta/raw_records.json`
- `meta/candidate_records.json`
- `meta/passed_records.json`

注意：

- `review/review_queue.json` 如果已經被 reviewer 編輯，不建議刪
- `segment/masks/` 與 `segment/visualizations/` 若 reviewer 需要看 overlay，也建議保留

## DB 對應

核心對應如下：

- `fetch/records.json` -> `image_records.raw_json`
- `brand/brand_records.json` -> `brand_records`
- `segment/records_with_logo_masks.json` -> `logo_instances`（若走 `segment-enrich`）
- `review/review_queue.json` <- `logo_instances`
- `export/knowledge_base.json` <- `image_records + logo_instances + brand_records`

## 讀檔建議順序

如果你要理解一個 run，建議照這個順序讀：

1. `meta/preflight.json`
2. `analysis/summary.json`
3. `fetch/records.json`
4. `brand/brand_records.json`
5. `segment/records_with_logo_masks.json`（若有）
6. `review/review_queue.json`
7. `export/knowledge_base.json`
8. `engine/logo_engine.db`
