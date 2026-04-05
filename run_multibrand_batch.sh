#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${PACKAGE_DIR}/.." && pwd)"
DEFAULT_OUTPUT_ROOT="${PACKAGE_DIR}/results"

ENV_NAME="logo_sam3"
RUN_NAME="batch_$(date +%Y%m%d_%H%M%S)"
OUTPUT_ROOT="${DEFAULT_OUTPUT_ROOT}"
TARGET_RECORDS=500
OVERSAMPLE_FACTOR=3
RESUME=1
SETUP_ENV=0
PHASE1_LITE=0
WITH_SAM3=1
SAM3_CHECKPOINT=""
SAM3_DEVICE=""
USE_VLM=1
VLM_MODEL_ID="llava-hf/llava-1.5-7b-hf"
USE_QWEN_QA=0
QWEN_MODEL_ID="Qwen/Qwen2.5-7B-Instruct"
OBJECT_FIRST=1
SKIP_OCR=0
SKIP_DETECTOR=0
SKIP_CLIP=0
SKIP_PRESCREEN=0
CUDA_DEVICES=""

usage() {
  cat <<'EOF'
Usage:
  ./logo_data_engine/run_multibrand_batch.sh [options]

Options:
  --target-records N    Target batch size after balancing. Default: 500
  --oversample-factor N Candidate pool multiplier before quality gate. Default: 3
  --run-name NAME       Run folder name. Default: timestamp
  --output-root PATH    Parent output directory. Default: /raid/ming/logo/logo_data_engine/results
  --env-name NAME       Conda env name. Default: logo_sam3
  --setup-env           Run logo_data_engine/setup_env.sh before the batch
  --phase1-lite         Convenience mode: disable heavy visual models, keep image download + text verification
  --with-sam3           Run SAM3 segmentation and import masks
  --no-sam3             Skip SAM3 segmentation
  --sam3-checkpoint PATH Optional SAM3 checkpoint path
  --sam3-device DEVICE  Optional SAM3 device override (e.g. cuda, cpu)
  --use-vlm             Enable LLaMA-style VLM caption/QA backend
  --no-vlm              Skip VLM caption/QA backend
  --vlm-model-id ID     VLM model id (e.g., llava-hf/llava-1.5-7b-hf)
  --use-qwen-qa         Enable Qwen knowledge QA enrichment
  --qwen-model-id ID    Qwen model id (e.g., Qwen/Qwen2.5-7B-Instruct)
  --object-first        Run object-first GroundingDINO before logo detection (default)
  --no-object-first     Skip object-first stage (logo detection on full image)
  --skip-ocr            Disable OCR enrichment
  --skip-detector       Disable GroundingDINO proposal detection
  --skip-clip           Disable CLIP quality gate
  --skip-prescreen      Disable YOLO logo prescreen gate
  --cuda-devices LIST   CUDA_VISIBLE_DEVICES override (e.g., 1 or 1,2,3)
  --no-resume           Do not pass --resume to phase1-workflow
  --help                Show this help
EOF
}

require_arg() {
  local flag="$1"
  local value="${2:-}"
  if [[ -z "${value}" ]]; then
    echo "[error] ${flag} requires a value" >&2
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-records)
      require_arg "$1" "${2:-}"
      TARGET_RECORDS="$2"
      shift 2
      ;;
    --oversample-factor)
      require_arg "$1" "${2:-}"
      OVERSAMPLE_FACTOR="$2"
      shift 2
      ;;
    --run-name)
      require_arg "$1" "${2:-}"
      RUN_NAME="$2"
      shift 2
      ;;
    --output-root)
      require_arg "$1" "${2:-}"
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    --env-name)
      require_arg "$1" "${2:-}"
      ENV_NAME="$2"
      shift 2
      ;;
    --setup-env)
      SETUP_ENV=1
      shift
      ;;
    --phase1-lite)
      PHASE1_LITE=1
      shift
      ;;
    --with-sam3)
      WITH_SAM3=1
      shift
      ;;
    --no-sam3)
      WITH_SAM3=0
      shift
      ;;
    --sam3-checkpoint)
      require_arg "$1" "${2:-}"
      SAM3_CHECKPOINT="$2"
      shift 2
      ;;
    --sam3-device)
      require_arg "$1" "${2:-}"
      SAM3_DEVICE="$2"
      shift 2
      ;;
    --use-vlm)
      USE_VLM=1
      shift
      ;;
    --no-vlm)
      USE_VLM=0
      shift
      ;;
    --vlm-model-id)
      require_arg "$1" "${2:-}"
      VLM_MODEL_ID="$2"
      shift 2
      ;;
    --use-qwen-qa)
      USE_QWEN_QA=1
      shift
      ;;
    --qwen-model-id)
      require_arg "$1" "${2:-}"
      QWEN_MODEL_ID="$2"
      shift 2
      ;;
    --no-resume)
      RESUME=0
      shift
      ;;
    --object-first)
      OBJECT_FIRST=1
      shift
      ;;
    --no-object-first)
      OBJECT_FIRST=0
      shift
      ;;
    --skip-ocr)
      SKIP_OCR=1
      shift
      ;;
    --skip-detector)
      SKIP_DETECTOR=1
      shift
      ;;
    --skip-clip)
      SKIP_CLIP=1
      shift
      ;;
    --skip-prescreen)
      SKIP_PRESCREEN=1
      shift
      ;;
    --cuda-devices)
      require_arg "$1" "${2:-}"
      CUDA_DEVICES="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "[error] unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ${PHASE1_LITE} -eq 1 ]]; then
  WITH_SAM3=0
  USE_VLM=0
  USE_QWEN_QA=1
  SKIP_OCR=1
  SKIP_DETECTOR=1
  SKIP_CLIP=1
  SKIP_PRESCREEN=1
fi

source "${HOME}/anaconda3/etc/profile.d/conda.sh"

if [[ ${SETUP_ENV} -eq 1 ]]; then
  "${PACKAGE_DIR}/setup_env.sh" "${ENV_NAME}"
fi

conda activate "${ENV_NAME}"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}:${PACKAGE_DIR}/sam3${PYTHONPATH:+:${PYTHONPATH}}"
export SAM3_DIR="${PACKAGE_DIR}/sam3"
if [[ -n "${CUDA_DEVICES}" ]]; then
  export CUDA_VISIBLE_DEVICES="${CUDA_DEVICES}"
fi

RUN_DIR="${OUTPUT_ROOT%/}/${RUN_NAME}"
DB_PATH="${RUN_DIR}/engine/logo_engine.db"
STAGING_DB_PATH="${RUN_DIR}/staging/logo_engine.db"
META_DIR="${RUN_DIR}/meta"
FETCH_DIR="${RUN_DIR}/fetch"
BRAND_DIR="${RUN_DIR}/brand"
REVIEW_DIR="${RUN_DIR}/review"
EXPORT_DIR="${RUN_DIR}/export"
ANALYSIS_DIR="${RUN_DIR}/analysis"
STAGING_DIR="${RUN_DIR}/staging"
SEGMENT_DIR="${RUN_DIR}/segment"

RAW_JSON="${META_DIR}/raw_records.json"
PLAN_JSON="${META_DIR}/batch_plan.json"
CANDIDATE_JSON="${META_DIR}/candidate_records.json"
PASSED_JSON="${META_DIR}/passed_records.json"
FETCH_JSON="${FETCH_DIR}/records.json"
FETCH_IMAGES="${FETCH_DIR}/images"
BRAND_JSON="${BRAND_DIR}/brand_records.json"
REVIEW_JSON="${REVIEW_DIR}/review_queue.json"
EXPORT_JSON="${EXPORT_DIR}/knowledge_base.json"
ANALYSIS_MD="${ANALYSIS_DIR}/analysis.md"
ANALYSIS_JSON="${ANALYSIS_DIR}/summary.json"
COVERAGE_MD="${ANALYSIS_DIR}/coverage.md"
COVERAGE_JSON="${ANALYSIS_DIR}/coverage.json"
METRICS_MD="${ANALYSIS_DIR}/metrics.md"
METRICS_JSON="${ANALYSIS_DIR}/metrics.json"
SEGMENT_JSON="${SEGMENT_DIR}/records_with_logo_masks.json"
SEGMENT_MASKS="${SEGMENT_DIR}/masks"
SEGMENT_VIZ="${SEGMENT_DIR}/visualizations"

mkdir -p "${RUN_DIR}/engine" "${STAGING_DIR}" "${META_DIR}" "${FETCH_DIR}" "${BRAND_DIR}" "${REVIEW_DIR}" "${EXPORT_DIR}" "${ANALYSIS_DIR}" "${SEGMENT_DIR}"

RESUME_FLAG=()
if [[ ${RESUME} -eq 1 ]]; then
  RESUME_FLAG+=(--resume)
fi

run_and_capture() {
  local output_file="$1"
  shift
  echo "[run] $*"
  "$@" | tee "${output_file}"
}

ENGINE_CMD=(python -m logo_data_engine)
CANDIDATE_TARGET=$(( TARGET_RECORDS * OVERSAMPLE_FACTOR ))

PREFLIGHT_CMD=(
  "${ENGINE_CMD[@]}"
  --db "${STAGING_DB_PATH}"
  preflight
)
if [[ ${WITH_SAM3} -eq 1 ]]; then
  PREFLIGHT_CMD+=(--with-sam3)
fi
if [[ ${USE_VLM} -eq 1 ]]; then
  PREFLIGHT_CMD+=(--use-vlm --vlm-model-id "${VLM_MODEL_ID}")
fi
if [[ ${USE_QWEN_QA} -eq 1 ]]; then
  PREFLIGHT_CMD+=(--use-qwen-qa --qwen-model-id "${QWEN_MODEL_ID}")
fi
if [[ ${OBJECT_FIRST} -eq 0 ]]; then
  PREFLIGHT_CMD+=(--no-object-first)
fi
if [[ ${SKIP_DETECTOR} -eq 1 ]]; then
  PREFLIGHT_CMD+=(--skip-detector)
fi
if [[ ${SKIP_OCR} -eq 1 ]]; then
  PREFLIGHT_CMD+=(--skip-ocr)
fi
if [[ ${SKIP_CLIP} -eq 1 ]]; then
  PREFLIGHT_CMD+=(--skip-clip)
fi
if [[ ${SKIP_PRESCREEN} -eq 1 ]]; then
  PREFLIGHT_CMD+=(--skip-prescreen)
fi
run_and_capture "${META_DIR}/preflight.json" "${PREFLIGHT_CMD[@]}"

run_and_capture "${PLAN_JSON}" \
  "${ENGINE_CMD[@]}" \
  --db "${STAGING_DB_PATH}" \
  batch-plan \
  --target "${CANDIDATE_TARGET}"

LIMIT_PER_PAIR="$(python - <<'PY' "${PLAN_JSON}"
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print(payload["recommended_limit_per_pair"])
PY
)"

run_and_capture "${META_DIR}/collector.json" \
  "${ENGINE_CMD[@]}" \
  --db "${STAGING_DB_PATH}" \
  collector-fetch-products \
  --all \
  --limit "${LIMIT_PER_PAIR}" \
  --output "${RAW_JSON}" \
  --image-dir "${FETCH_IMAGES}"

run_and_capture "${META_DIR}/balance.json" \
  "${ENGINE_CMD[@]}" \
  --db "${STAGING_DB_PATH}" \
  balance-records \
  --input "${RAW_JSON}" \
  --output "${CANDIDATE_JSON}" \
  --target "${CANDIDATE_TARGET}"

run_and_capture "${META_DIR}/ontology.json" \
  "${ENGINE_CMD[@]}" \
  --db "${STAGING_DB_PATH}" \
  ontology-fetch-brands \
  --product-records "${CANDIDATE_JSON}" \
  --output "${BRAND_JSON}"

run_and_capture "${META_DIR}/staging_seed.json" \
  "${ENGINE_CMD[@]}" \
  --db "${STAGING_DB_PATH}" \
  seed-ontology \
  --brand-records "${BRAND_JSON}"

run_and_capture "${META_DIR}/staging_ingest.json" \
  "${ENGINE_CMD[@]}" \
  --db "${STAGING_DB_PATH}" \
  ingest-images \
  --records-json "${CANDIDATE_JSON}" \
  "${RESUME_FLAG[@]}"

run_and_capture "${META_DIR}/staging_gate.json" \
  "${ENGINE_CMD[@]}" \
  --db "${STAGING_DB_PATH}" \
  gate \
  --all \
  $( [[ ${SKIP_CLIP} -eq 1 ]] && echo --skip-clip ) \
  $( [[ ${SKIP_PRESCREEN} -eq 1 ]] && echo --skip-prescreen ) \
  --report

run_and_capture "${META_DIR}/export_passed.json" \
  "${ENGINE_CMD[@]}" \
  --db "${STAGING_DB_PATH}" \
  export-image-records \
  --quality-status passed \
  --output "${PASSED_JSON}"

run_and_capture "${META_DIR}/balance_passed.json" \
  "${ENGINE_CMD[@]}" \
  --db "${STAGING_DB_PATH}" \
  balance-records \
  --input "${PASSED_JSON}" \
  --output "${FETCH_JSON}" \
  --target "${TARGET_RECORDS}"

PASSED_COUNT="$(python - <<'PY' "${FETCH_JSON}"
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print(len(payload))
PY
)"

if [[ "${PASSED_COUNT}" -lt "${TARGET_RECORDS}" ]]; then
  echo "[error] only ${PASSED_COUNT} quality-passed records available after gating; target was ${TARGET_RECORDS}" >&2
  echo "[error] try a higher --oversample-factor or broaden sources before treating this as a gold-ready batch" >&2
  exit 1
fi

if [[ ${WITH_SAM3} -eq 1 ]]; then
  SEGMENT_CMD=(
    "${ENGINE_CMD[@]}"
    --db "${DB_PATH}"
    segment-sam3
    --input-records "${FETCH_JSON}"
    --output "${SEGMENT_JSON}"
    --mask-dir "${SEGMENT_MASKS}"
    --viz-dir "${SEGMENT_VIZ}"
    --brand-records "${BRAND_JSON}"
  )
  if [[ -n "${SAM3_CHECKPOINT}" ]]; then
    SEGMENT_CMD+=(--checkpoint-path "${SAM3_CHECKPOINT}")
  fi
  if [[ -n "${SAM3_DEVICE}" ]]; then
    SEGMENT_CMD+=(--device "${SAM3_DEVICE}")
  fi
  if [[ ${OBJECT_FIRST} -eq 0 ]]; then
    SEGMENT_CMD+=(--no-object-first)
  fi
  run_and_capture "${META_DIR}/segment.json" "${SEGMENT_CMD[@]}"
fi

run_and_capture "${META_DIR}/phase1.json" \
  "${ENGINE_CMD[@]}" \
  --db "${DB_PATH}" \
  phase1-workflow \
  --records-json "${FETCH_JSON}" \
  --brand-records "${BRAND_JSON}" \
  --review-output "${REVIEW_JSON}" \
  $( [[ ${WITH_SAM3} -eq 1 ]] && echo --segment-records "${SEGMENT_JSON}" --segment-enrich ) \
  $( [[ ${SKIP_DETECTOR} -eq 1 ]] && echo --skip-detector ) \
  $( [[ ${SKIP_OCR} -eq 1 ]] && echo --skip-ocr ) \
  $( [[ ${SKIP_CLIP} -eq 1 ]] && echo --skip-clip ) \
  $( [[ ${SKIP_PRESCREEN} -eq 1 ]] && echo --skip-prescreen ) \
  $( [[ ${USE_VLM} -eq 1 ]] && echo --use-vlm --vlm-model-id "${VLM_MODEL_ID}" ) \
  $( [[ ${USE_QWEN_QA} -eq 1 ]] && echo --use-qwen-qa --qwen-model-id "${QWEN_MODEL_ID}" ) \
  "${RESUME_FLAG[@]}"

run_and_capture "${META_DIR}/export.json" \
  "${ENGINE_CMD[@]}" \
  --db "${DB_PATH}" \
  export-kb \
  --output "${EXPORT_JSON}"

run_and_capture "${ANALYSIS_DIR}/analyze.json" \
  "${ENGINE_CMD[@]}" \
  --db "${DB_PATH}" \
  analyze-run \
  --run-dir "${RUN_DIR}" \
  --output-md "${ANALYSIS_MD}" \
  --output-json "${ANALYSIS_JSON}" \
  --target-records "${TARGET_RECORDS}"

run_and_capture "${ANALYSIS_DIR}/coverage_run.json" \
  "${ENGINE_CMD[@]}" \
  --db "${DB_PATH}" \
  coverage-plan \
  --output-md "${COVERAGE_MD}" \
  --output-json "${COVERAGE_JSON}"

run_and_capture "${ANALYSIS_DIR}/metrics_run.json" \
  "${ENGINE_CMD[@]}" \
  --db "${DB_PATH}" \
  metrics-report \
  --output-md "${METRICS_MD}" \
  --output-json "${METRICS_JSON}"

run_and_capture "${META_DIR}/summary.json" \
  "${ENGINE_CMD[@]}" \
  --db "${DB_PATH}" \
  summary \
  --pretty

cat <<EOF

[done] Multi-brand batch finished.
run_dir: ${RUN_DIR}
target_records: ${TARGET_RECORDS}
oversample_factor: ${OVERSAMPLE_FACTOR}
raw_records_json: ${RAW_JSON}
candidate_records_json: ${CANDIDATE_JSON}
passed_records_json: ${PASSED_JSON}
balanced_records_json: ${FETCH_JSON}
brand_records_json: ${BRAND_JSON}
review_queue_json: ${REVIEW_JSON}
knowledge_base_json: ${EXPORT_JSON}
analysis_md: ${ANALYSIS_MD}
analysis_json: ${ANALYSIS_JSON}
coverage_md: ${COVERAGE_MD}
coverage_json: ${COVERAGE_JSON}
metrics_md: ${METRICS_MD}
metrics_json: ${METRICS_JSON}
EOF
