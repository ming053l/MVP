#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${PACKAGE_DIR}/.." && pwd)"
DEFAULT_OUTPUT_ROOT="${PACKAGE_DIR}/results"

ENV_NAME="logo_sam3"
RUN_NAME="run_$(date +%Y%m%d_%H%M%S)"
OUTPUT_ROOT="${DEFAULT_OUTPUT_ROOT}"
LIMIT=4
MODE=""
BRANDS=""
CATEGORIES=""
COLLECTION_ROOT=""
DEFAULT_SOURCE=""
DEFAULT_SOURCE_CHANNEL=""
METADATA_CSV=""
MANIFESTS=()
DEFAULT_LICENSE="unknown"
DRY_RUN=0
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
  Product collector mode:
    ./logo_data_engine/run_pipeline.sh --brands nike,adidas --categories shoes,apparel [options]
    ./logo_data_engine/run_pipeline.sh --all [options]

  External collection mode:
    ./logo_data_engine/run_pipeline.sh --collection-root /path/to/images [options]

  External manifest mode:
    ./logo_data_engine/run_pipeline.sh --manifest /path/to/manifest.json [--manifest /path/to/manifest2.json] [options]

Options:
  --run-name NAME                 Run folder name. Default: timestamp
  --output-root PATH              Parent output directory. Default: /raid/ming/logo/logo_data_engine/results
  --env-name NAME                 Conda env name. Default: logo_sam3
  --limit N                       Max records per brand/category pair in product mode. Default: 4
  --default-source NAME           Default source name in external collection mode
  --default-source-channel NAME   Default source_channel in external collection mode
  --metadata-csv PATH             Optional metadata CSV for external collection mode
  --default-license NAME          Default rights label for external inputs. Default: unknown
  --setup-env                     Run logo_data_engine/setup_env.sh before the pipeline
  --phase1-lite                  Convenience mode: disable heavy visual models, keep image download + text verification
  --with-sam3                     Run SAM3 segmentation and import masks
  --no-sam3                       Skip SAM3 segmentation
  --sam3-checkpoint PATH          Optional SAM3 checkpoint path
  --sam3-device DEVICE            Optional SAM3 device override (e.g. cuda, cpu)
  --object-first                  Run object-first GroundingDINO before logo detection (default)
  --no-object-first               Skip object-first stage (logo detection on full image)
  --skip-ocr                      Disable OCR enrichment
  --skip-detector                 Disable GroundingDINO proposal detection
  --skip-clip                     Disable CLIP quality gate
  --skip-prescreen                Disable YOLO logo prescreen gate
  --cuda-devices LIST             CUDA_VISIBLE_DEVICES override (e.g., 1 or 1,2,3)
  --use-vlm                       Enable LLaMA-style VLM caption/QA backend
  --no-vlm                        Skip VLM caption/QA backend
  --vlm-model-id ID               VLM model id (e.g., llava-hf/llava-1.5-7b-hf)
  --use-qwen-qa                   Enable Qwen knowledge QA enrichment
  --qwen-model-id ID              Qwen model id (e.g., Qwen/Qwen2.5-7B-Instruct)
  --dry-run                       Compute the workflow without writing DB/results
  --no-resume                     Do not pass --resume to phase1-workflow
  --help                          Show this help
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
    --all)
      MODE="products_all"
      shift
      ;;
    --brands)
      require_arg "$1" "${2:-}"
      MODE="products"
      BRANDS="$2"
      shift 2
      ;;
    --categories)
      require_arg "$1" "${2:-}"
      CATEGORIES="$2"
      shift 2
      ;;
    --collection-root)
      require_arg "$1" "${2:-}"
      MODE="external_collection"
      COLLECTION_ROOT="$2"
      shift 2
      ;;
    --manifest)
      require_arg "$1" "${2:-}"
      MODE="external_manifest"
      MANIFESTS+=("$2")
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
    --limit)
      require_arg "$1" "${2:-}"
      LIMIT="$2"
      shift 2
      ;;
    --default-source)
      require_arg "$1" "${2:-}"
      DEFAULT_SOURCE="$2"
      shift 2
      ;;
    --default-source-channel)
      require_arg "$1" "${2:-}"
      DEFAULT_SOURCE_CHANNEL="$2"
      shift 2
      ;;
    --metadata-csv)
      require_arg "$1" "${2:-}"
      METADATA_CSV="$2"
      shift 2
      ;;
    --default-license)
      require_arg "$1" "${2:-}"
      DEFAULT_LICENSE="$2"
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
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-resume)
      RESUME=0
      shift
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

if [[ -z "${MODE}" ]]; then
  echo "[error] choose one input mode: --all, --brands/--categories, --collection-root, or --manifest" >&2
  usage >&2
  exit 2
fi

if [[ "${MODE}" == "products" && ( -z "${BRANDS}" || -z "${CATEGORIES}" ) ]]; then
  echo "[error] product mode requires both --brands and --categories" >&2
  exit 2
fi

if [[ "${MODE}" == "external_manifest" && ${#MANIFESTS[@]} -eq 0 ]]; then
  echo "[error] external manifest mode requires at least one --manifest" >&2
  exit 2
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
FETCH_DIR="${RUN_DIR}/fetch"
BRAND_DIR="${RUN_DIR}/brand"
REVIEW_DIR="${RUN_DIR}/review"
EXPORT_DIR="${RUN_DIR}/export"
META_DIR="${RUN_DIR}/meta"
ANALYSIS_DIR="${RUN_DIR}/analysis"
SEGMENT_DIR="${RUN_DIR}/segment"

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

mkdir -p "${FETCH_DIR}" "${BRAND_DIR}" "${REVIEW_DIR}" "${EXPORT_DIR}" "${META_DIR}" "${ANALYSIS_DIR}" "${RUN_DIR}/engine" "${SEGMENT_DIR}"

DRY_RUN_FLAG=()
if [[ ${DRY_RUN} -eq 1 ]]; then
  DRY_RUN_FLAG+=(--dry-run)
fi

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

PREFLIGHT_CMD=(
  "${ENGINE_CMD[@]}"
  --db "${DB_PATH}"
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

if [[ "${MODE}" == "products" || "${MODE}" == "products_all" ]]; then
  COLLECT_CMD=(
    "${ENGINE_CMD[@]}"
    --db "${DB_PATH}"
    collector-fetch-products
    --output "${FETCH_JSON}"
    --image-dir "${FETCH_IMAGES}"
    --limit "${LIMIT}"
  )
  if [[ "${MODE}" == "products_all" ]]; then
    COLLECT_CMD+=(--all)
  else
    COLLECT_CMD+=(--brands "${BRANDS}" --categories "${CATEGORIES}")
  fi
  COLLECT_CMD+=("${DRY_RUN_FLAG[@]}")
  run_and_capture "${META_DIR}/collector.json" "${COLLECT_CMD[@]}"
elif [[ "${MODE}" == "external_collection" ]]; then
  COLLECT_CMD=(
    "${ENGINE_CMD[@]}"
    --db "${DB_PATH}"
    collector-prepare-external
    --collection-root "${COLLECTION_ROOT}"
    --output "${FETCH_JSON}"
  )
  if [[ -n "${DEFAULT_SOURCE}" ]]; then
    COLLECT_CMD+=(--default-source "${DEFAULT_SOURCE}")
  fi
  if [[ -n "${DEFAULT_SOURCE_CHANNEL}" ]]; then
    COLLECT_CMD+=(--default-source-channel "${DEFAULT_SOURCE_CHANNEL}")
  fi
  if [[ -n "${METADATA_CSV}" ]]; then
    COLLECT_CMD+=(--metadata-csv "${METADATA_CSV}")
  fi
  COLLECT_CMD+=(--default-license "${DEFAULT_LICENSE}")
  COLLECT_CMD+=("${DRY_RUN_FLAG[@]}")
  run_and_capture "${META_DIR}/collector.json" "${COLLECT_CMD[@]}"
elif [[ "${MODE}" == "external_manifest" ]]; then
  COLLECT_CMD=(
    "${ENGINE_CMD[@]}"
    --db "${DB_PATH}"
    collector-ingest-manifest
    --output "${FETCH_JSON}"
    --image-dir "${FETCH_IMAGES}"
    --default-license "${DEFAULT_LICENSE}"
  )
  for manifest in "${MANIFESTS[@]}"; do
    COLLECT_CMD+=(--manifest "${manifest}")
  done
  COLLECT_CMD+=("${DRY_RUN_FLAG[@]}")
  run_and_capture "${META_DIR}/collector.json" "${COLLECT_CMD[@]}"
fi

ONTOLOGY_CMD=(
  "${ENGINE_CMD[@]}"
  --db "${DB_PATH}"
  ontology-fetch-brands
  --product-records "${FETCH_JSON}"
  --output "${BRAND_JSON}"
  "${DRY_RUN_FLAG[@]}"
)
run_and_capture "${META_DIR}/ontology.json" "${ONTOLOGY_CMD[@]}"

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
    "${DRY_RUN_FLAG[@]}"
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

PHASE1_CMD=(
  "${ENGINE_CMD[@]}"
  --db "${DB_PATH}"
  phase1-workflow
  --records-json "${FETCH_JSON}"
  --brand-records "${BRAND_JSON}"
  --review-output "${REVIEW_JSON}"
  "${RESUME_FLAG[@]}"
  "${DRY_RUN_FLAG[@]}"
)
if [[ ${WITH_SAM3} -eq 1 ]]; then
  PHASE1_CMD+=(--segment-records "${SEGMENT_JSON}" --segment-enrich)
fi
if [[ ${SKIP_DETECTOR} -eq 1 ]]; then
  PHASE1_CMD+=(--skip-detector)
fi
if [[ ${SKIP_OCR} -eq 1 ]]; then
  PHASE1_CMD+=(--skip-ocr)
fi
if [[ ${SKIP_CLIP} -eq 1 ]]; then
  PHASE1_CMD+=(--skip-clip)
fi
if [[ ${SKIP_PRESCREEN} -eq 1 ]]; then
  PHASE1_CMD+=(--skip-prescreen)
fi
if [[ ${USE_VLM} -eq 1 ]]; then
  PHASE1_CMD+=(--use-vlm --vlm-model-id "${VLM_MODEL_ID}")
fi
if [[ ${USE_QWEN_QA} -eq 1 ]]; then
  PHASE1_CMD+=(--use-qwen-qa --qwen-model-id "${QWEN_MODEL_ID}")
fi
run_and_capture "${META_DIR}/phase1.json" "${PHASE1_CMD[@]}"

EXPORT_CMD=(
  "${ENGINE_CMD[@]}"
  --db "${DB_PATH}"
  export-kb
  --output "${EXPORT_JSON}"
  "${DRY_RUN_FLAG[@]}"
)
run_and_capture "${META_DIR}/export.json" "${EXPORT_CMD[@]}"

ANALYZE_CMD=(
  "${ENGINE_CMD[@]}"
  --db "${DB_PATH}"
  analyze-run
  --run-dir "${RUN_DIR}"
  --output-md "${ANALYSIS_MD}"
  --output-json "${ANALYSIS_JSON}"
)
run_and_capture "${META_DIR}/analyze.json" "${ANALYZE_CMD[@]}"

COVERAGE_CMD=(
  "${ENGINE_CMD[@]}"
  --db "${DB_PATH}"
  coverage-plan
  --output-md "${COVERAGE_MD}"
  --output-json "${COVERAGE_JSON}"
)
run_and_capture "${META_DIR}/coverage.json" "${COVERAGE_CMD[@]}"

METRICS_CMD=(
  "${ENGINE_CMD[@]}"
  --db "${DB_PATH}"
  metrics-report
  --output-md "${METRICS_MD}"
  --output-json "${METRICS_JSON}"
)
run_and_capture "${META_DIR}/metrics_report.json" "${METRICS_CMD[@]}"

SUMMARY_CMD=(
  "${ENGINE_CMD[@]}"
  --db "${DB_PATH}"
  summary
  --pretty
)
run_and_capture "${META_DIR}/summary.json" "${SUMMARY_CMD[@]}"

cat <<EOF

[done] Full pipeline finished.
run_dir: ${RUN_DIR}
db: ${DB_PATH}
records_json: ${FETCH_JSON}
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
