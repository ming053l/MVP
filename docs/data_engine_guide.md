# Logo Data Engine 使用說明與資料流規格

本文件說明 `/raid/ming/logo/logo_data_engine` 的完整使用方式、資料輸出流，以及各檔案與 schema 的格式細節。文件對應目前實作的 pipeline 與實際輸出路徑。

## 1. 快速開始

### 1.1 環境與依賴

```bash
cd /raid/ming/logo
./logo_data_engine/setup_env.sh logo_sam3
```

此腳本會：
- 建立 `logo_sam3` conda env
- 安裝 requirements
- 下載或更新 SAM3 到 `logo_data_engine/sam3`
- `pip install -e` 安裝 SAM3

### 1.2 一鍵多品牌批次

```bash
cd /raid/ming/logo
./logo_data_engine/run_multibrand_batch.sh \
  --run-name batch_10 \
  --target-records 10 \
  --with-sam3 \
  --use-vlm \
  --vlm-model-id llava-hf/llava-1.5-7b-hf
```

指定 GPU：

```bash
./logo_data_engine/run_multibrand_batch.sh \
  --run-name batch_10 \
  --target-records 10 \
  --with-sam3 \
  --cuda-devices 1,2,3
```

### 1.3 單次 Pipeline（特定品牌/類別）

```bash
cd /raid/ming/logo
./logo_data_engine/run_pipeline.sh \
  --run-name quickstart \
  --brands nike,adidas \
  --categories shoes,apparel \
  --limit 5 \
  --with-sam3 \
  --use-vlm
```

## 2. Pipeline 入口與預設行為

### 2.1 入口腳本

- `run_multibrand_batch.sh`：多品牌、多類別、多來源批次。預設先 oversample，經過 quality gate 之後才平衡到目標數。
- `run_pipeline.sh`：單次 pipeline，可用於特定品牌/類別或外部資料。

### 2.2 預設 preflight

每次執行 pipeline 都會先跑 `preflight`，檢查模型是否能載入：

- GroundingDINO
- PaddleOCR
- CLIP logo gate
- CLIP retrieval
- BLIP caption
- VLM (LLaVA)
- YOLO prescreen
- SAM3

結果輸出：

```
results/<run_name>/meta/preflight.json
```

## 3. 非常詳實的資料輸出流

以下以 **多品牌 batch** 為例，完整資料流如下：

1. **Collector**
   - 輸入：品牌/類別設定
   - 輸出：
     - `meta/raw_records.json`
     - `fetch/images/`（下載圖）

2. **Balance (candidate)**
   - 輸入：`meta/raw_records.json`
   - 輸出：`meta/candidate_records.json`

3. **Ontology Fetch**
   - 輸入：`meta/candidate_records.json`
   - 輸出：`brand/brand_records.json`

4. **Seed Ontology**
   - 輸入：`brand/brand_records.json`
   - 寫入：`DB.brand_records (tier = silver)`

5. **Ingest Images**
   - 輸入：`meta/candidate_records.json`
   - 寫入：`DB.image_records`
   - 內部動作：pHash 去重、外部 key 去重

6. **Quality Gate**
   - 輸入：`DB.image_records`
   - 輸出：
     - `meta/passed_records.json`
     - `DB.image_records.quality_status`

7. **Balance (final)**
   - 輸入：`meta/passed_records.json`
   - 輸出：`fetch/records.json`（目標筆數）

8. **SAM3 Segmentation**
   - 輸入：`fetch/records.json`, `brand/brand_records.json`
   - 輸出：
     - `segment/records_with_logo_masks.json`
     - `segment/masks/`
     - `segment/visualizations/`

9. **Phase1 Annotate**
   - 輸入：
     - `fetch/records.json`
     - `brand/brand_records.json`
     - `segment/records_with_logo_masks.json`（如有 SAM3）
   - 寫入：`DB.logo_instances`
   - 輸出：`review/review_queue.json`

10. **Export**
    - 輸入：DB tables
    - 輸出：
      - `export/knowledge_base.json`
      - `analysis/analysis.md`
      - `analysis/summary.json`

## 4. Quality Gate 參數與評分邏輯

Quality Gate 依序執行，所有 gate 的結果會寫入 `DB.image_records.quality_status`。

### Gate 1: Size / Format
- 判斷：`min_width >= 256` 且 `min_height >= 256`
- 失敗原因：`too_small`

### Gate 2: Blur
- 量測：Laplacian variance
- 閾值：`blur_threshold = 45.0`
- 失敗原因：`too_blurry`

### Gate 3: pHash Dedup
- 量測：pHash distance
- 閾值：`phash_distance_threshold = 6`
- 失敗原因：`duplicate`

### Gate 4: CLIP Logo Score
- 模型：`openai/clip-vit-base-patch32`
- Prompt：`"a photo with a brand logo"`
- 閾值：
  - `clip_threshold = 0.22`（硬門檻）
  - `clip_soft_floor = 0.08`（可信來源 soft pass）
- 失敗原因：`low_clip_logo_score`

### Gate 5: YOLO Prescreen
- 模型：YOLO-World
- Labels：`["logo", "brand logo", "company logo"]`
- 閾值：`prescreen_threshold = 0.3`
- 失敗原因：`no_logo_prescreen_detection`

## 5. SAM3 Two-Stage 流程

預設為 object-first：

1. **GroundingDINO object**
   - object prompts 由 `category` 與 `object_terms` 決定
2. **GroundingDINO logo**
   - 在物件 crop 上找 logo bbox
3. **SAM3 mask**
   - 使用 logo bbox 在全圖產生 mask

輸出欄位：
- `object_grounding_bbox_xyxy`
- `object_grounding_label`
- `logo_grounding_bbox_xyxy`
- `logo_mask_path`
- `logo_segmentation_status`

關閉 object-first：

```bash
./logo_data_engine/run_multibrand_batch.sh \
  --run-name batch_10_no_object_first \
  --target-records 10 \
  --with-sam3 \
  --no-object-first
```

## 6. Annotator 與 Attribution 輸出

在 `DB.logo_instances` 與 `export/knowledge_base.json` 中包含：

- `ocr_text`
- `ocr_confidence`
- `clip_score`
- `caption_text`
- `caption_model`
- `attribution_json`

其中 `attribution_json` 會保留：
- CLIP retrieval 結果
- BLIP captioning
- VLM captioning
- merge_signals 最終判斷

完整的 OCR 行與 caption payload 可在：
- `logo_instances.provenance_json`

## 7. Schema 說明

### 7.1 ImageRecord

主要欄位：
- `image_id`
- `external_key`
- `image_url`
- `local_image_path`
- `quality_status`
- `image_phash`
- `raw_json`

### 7.2 LogoInstance

主要欄位：
- `instance_id`
- `image_id`
- `brand_id`
- `bbox_json`
- `mask_path`
- `ocr_text`
- `clip_score`
- `caption_text`
- `caption_model`
- `attribution_json`
- `tier`

### 7.3 BrandRecord

主要欄位：
- `brand_id`
- `display_name`
- `industry`
- `country`
- `tier`

## 8. 主要輸出路徑整理

```
results/<run_name>/
  meta/
    preflight.json
    raw_records.json
    candidate_records.json
    passed_records.json
  fetch/
    records.json
    images/
  brand/
    brand_records.json
  segment/
    records_with_logo_masks.json
    masks/
    visualizations/
  review/
    review_queue.json
  export/
    knowledge_base.json
  analysis/
    analysis.md
    summary.json
```

## 9. 常見問題

### 9.1 SAM3 不可用
- 確認 `/raid/ming/logo/logo_data_engine/sam3` 存在
- `preflight.json` 會顯示詳細錯誤

### 9.2 OCR / VLM 無輸出
- 檢查 `preflight.json`
- 注意 GPU 記憶體不足可能造成 VLM OOM

---

文件版本：v1.0
