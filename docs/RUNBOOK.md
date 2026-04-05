# RUNBOOK

這份文件是 `logo_data_engine` 的保守執行手冊。  
目標不是一次把所有能力都開滿，而是用最穩定、最容易 debug 的方式，先確認整條資料閉環是健康的。

適用情境：

- 第一次驗證新環境
- 第一次驗證 `phase1-lite`
- 想快速確認 collector / ontology / gate / Qwen / verifier / review UI 是否正常
- 想避免直接跑大 batch 後不知道是哪一步出問題

本文所有指令都以目前 repo 內實際存在的 CLI 為準。

## 0. 前提

工作目錄：

```bash
cd /raid/ming/logo
```

建議環境：

```bash
cd /raid/ming/logo/logo_data_engine
./setup_env.sh logo_sam3
source /home/chiaming/anaconda3/etc/profile.d/conda.sh
conda activate logo_sam3
```

回到專案根目錄：

```bash
cd /raid/ming/logo
```

如果要避免 Qwen 跟別的程序搶 GPU，建議先指定 GPU：

```bash
export CUDA_VISIBLE_DEVICES=1
```

或在 shell script 模式用：

```bash
--cuda-devices 1
```

## 1. Smoke Test：單品牌 10 筆

這一步最穩，建議先跑。  
先挑不容易歧義的品牌，例如 `coca-cola`、`starbucks`、`nike`、`adidas`。

建立 run 變數：

```bash
cd /raid/ming/logo

RUN=smoke_cocacola_10
ROOT=/raid/ming/logo/logo_data_engine/results/$RUN
DB=$ROOT/engine/logo_engine.db

mkdir -p "$ROOT"/engine "$ROOT"/fetch "$ROOT"/brand "$ROOT"/review "$ROOT"/analysis "$ROOT"/export
```

### 1.1 建 DB

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db "$DB" \
  init-db
```

### 1.2 Preflight

這裡故意先關掉重型視覺模組，只測 `phase1-lite`。

```bash
cd /raid/ming/logo

CUDA_VISIBLE_DEVICES=1 python -m logo_data_engine \
  --db "$DB" \
  preflight \
  --skip-detector \
  --skip-ocr \
  --skip-clip \
  --skip-prescreen \
  --use-qwen-qa \
  --qwen-model-id Qwen/Qwen2.5-7B-Instruct
```

看輸出重點：

- `ready: true`
- `qwen_qa.available: true`
- 被 skip 的模組顯示 `enabled: false` 或 `error: "disabled"` 都是正常

如果 `ready: false`，先不要繼續。

### 1.3 抓資料

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db "$DB" \
  collector-fetch-products \
  --brands coca-cola \
  --categories mugs \
  --limit 10 \
  --output "$ROOT/fetch/records.json" \
  --image-dir "$ROOT/fetch/images"
```

### 1.4 建 ontology

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db "$DB" \
  ontology-fetch-brands \
  --product-records "$ROOT/fetch/records.json" \
  --output "$ROOT/brand/brand_records.json"

python -m logo_data_engine \
  --db "$DB" \
  seed-ontology \
  --brand-records "$ROOT/brand/brand_records.json"
```

### 1.5 Ingest + Gate

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db "$DB" \
  ingest-images \
  --records-json "$ROOT/fetch/records.json"

python -m logo_data_engine \
  --db "$DB" \
  gate \
  --all \
  --skip-clip \
  --skip-prescreen \
  --report
```

### 1.6 Annotate：text-only + Qwen

```bash
cd /raid/ming/logo

CUDA_VISIBLE_DEVICES=1 python -m logo_data_engine \
  --db "$DB" \
  annotate-db \
  --skip-detector \
  --skip-ocr \
  --skip-clip-retrieval \
  --skip-captioning \
  --use-qwen-qa \
  --qwen-model-id Qwen/Qwen2.5-7B-Instruct
```

### 1.7 看這一步是否健康

跑完後先產生兩個報表：

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db "$DB" \
  metrics-report \
  --output-md "$ROOT/analysis/metrics.md" \
  --output-json "$ROOT/analysis/metrics.json"

python -m logo_data_engine \
  --db "$DB" \
  coverage-plan \
  --target-per-pair 1 \
  --output-md "$ROOT/analysis/coverage.md" \
  --output-json "$ROOT/analysis/coverage.json"
```

這裡要看的重點：

- `metrics-report`
  - `verification_conflicts` 不要太多
  - `text_only_instances` 跟 `inserted_instances` 相同是正常
  - `review_bucket_counts` 不要全部都是 `must_review`
- `coverage-plan`
  - smoke test 一定要用 `--target-per-pair 1`
  - 不然 planner 會預設每個 pair 要 20 筆，對小測試沒有意義

## 2. 開 Review UI

```bash
cd /raid/ming/logo

python -m logo_data_engine.ui_server \
  --db "$DB" \
  --host 0.0.0.0 \
  --port 8000
```

瀏覽器打開：

```text
http://<server-ip>:8000
```

建議先人工看 3 到 5 筆，確認：

- 圖片跟商品 metadata 是否對得上
- `brand_record` 是否合理
- `knowledge` / `risk` 是否在亂講
- `verification` 的結論是否合理

## 3. 匯出 Review Queue

如果你要離線看 queue JSON：

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db "$DB" \
  review-queue \
  --output "$ROOT/review/review_queue.json"
```

如果你是直接在 UI 裡按 `reject / silver / gold`，通常不用額外跑 `review-apply`。  
只有你手動修改 `review_queue.json` 後，才需要：

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db "$DB" \
  review-apply \
  --decisions-json "$ROOT/review/review_queue.json"
```

## 4. 匯出與分析

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db "$DB" \
  export-kb \
  --output "$ROOT/export/knowledge_base.json"

python -m logo_data_engine \
  --db "$DB" \
  analyze-run \
  --run-dir "$ROOT" \
  --output-md "$ROOT/analysis/analysis.md" \
  --output-json "$ROOT/analysis/summary.json"
```

如果這一步都正常，代表最小閉環已通：

- collect
- ontology
- ingest
- gate
- annotate
- verify
- review
- export

## 5. 小型正式批次：30 筆

Smoke test 沒問題後，再跑小批量 batch。  
建議直接用新 `run-name`，不要覆蓋舊 run。

```bash
cd /raid/ming/logo

./logo_data_engine/run_multibrand_batch.sh \
  --phase1-lite \
  --cuda-devices 1 \
  --run-name batch_phase1_lite_30_v2 \
  --target-records 30 \
  --oversample-factor 2
```

跑完之後，報表會自動生成在：

```text
/raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30_v2/analysis/
```

包含：

- `analysis.md`
- `summary.json`
- `coverage.md`
- `coverage.json`
- `metrics.md`
- `metrics.json`

## 6. 已完成 run 的手動報表指令

如果 run 已經存在，要手動重產 coverage / metrics，請直接用真實 DB 路徑，不要用示意路徑。

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db /raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30/engine/logo_engine.db \
  metrics-report \
  --output-md /raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30/analysis/metrics.md \
  --output-json /raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30/analysis/metrics.json

python -m logo_data_engine \
  --db /raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30/engine/logo_engine.db \
  coverage-plan \
  --output-md /raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30/analysis/coverage.md \
  --output-json /raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30/analysis/coverage.json
```

如果你只跑到 staging，則用 staging DB：

```bash
cd /raid/ming/logo

python -m logo_data_engine \
  --db /raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30/staging/logo_engine.db \
  metrics-report \
  --output-md /raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30/analysis/staging_metrics.md \
  --output-json /raid/ming/logo/logo_data_engine/results/batch_phase1_lite_30/analysis/staging_metrics.json
```

## 7. 目前最推薦的保守執行順序

照這個順序最穩：

1. `preflight`
2. 單品牌 10 筆 smoke test
3. `metrics-report`
4. 開 UI 看幾筆
5. `export-kb` + `analyze-run`
6. 再跑 30 筆 batch
7. 確認 `coverage` / `metrics`
8. 之後再放大到更多品牌或更多 target

## 8. 常見錯誤

### 8.1 不要用示意路徑

這種不能直接跑：

```bash
python -m logo_data_engine --db /path/to/logo_engine.db ...
```

請改成真實路徑，例如：

```bash
/raid/ming/logo/logo_data_engine/results/<run_name>/engine/logo_engine.db
```

### 8.2 `ready: false`

如果 `preflight` 顯示：

- `qwen_qa.available: false`
- `ready: false`

代表當前設定不適合往下跑。  
最常見原因是 GPU OOM。建議：

```bash
export CUDA_VISIBLE_DEVICES=1
```

或：

```bash
./logo_data_engine/run_multibrand_batch.sh --cuda-devices 1 ...
```

### 8.3 `coverage-plan` 看起來全都在叫你 collect_more

這通常不是錯，而是因為：

- 你跑的是小 smoke test
- planner 預設 `target_per_pair = 20`

所以小測試時請改用：

```bash
--target-per-pair 1
```

### 8.4 Qwen parser 修正後，舊 run 不會自動變好

如果某批資料是在 parser 修正前產生的，舊 DB 內的 `json_decode_error` 不會自動消失。  
最穩的做法是：

- 用新的 `run-name` 重跑

## 9. 目前不建議一開始就做的事

先不要一開始就：

- 開 OCR
- 開 GroundingDINO
- 開 SAM3
- 開 CLIP retrieval
- 直接跑大於 100 的 target

先把 `phase1-lite` 跑順，再逐步接回視覺模組。
