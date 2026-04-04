#!/usr/bin/env bash
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="${1:-logo_sam3}"
SAM3_DIR="${PACKAGE_DIR}/sam3"

source "${HOME}/anaconda3/etc/profile.d/conda.sh"

if ! conda env list | awk '{print $1}' | grep -Fxq "${ENV_NAME}"; then
  conda create -y -n "${ENV_NAME}" python=3.12
fi

conda activate "${ENV_NAME}"

python -m pip install --upgrade pip
python -m pip install "setuptools<81"
python -m pip install -r "${PACKAGE_DIR}/requirements.txt"
python -m pip install torch==2.10.0 torchvision --index-url https://download.pytorch.org/whl/cu128

if [ ! -d "${SAM3_DIR}" ]; then
  git clone https://github.com/facebookresearch/sam3.git "${SAM3_DIR}"
else
  git -C "${SAM3_DIR}" pull --ff-only
fi

python -m pip install -e "${SAM3_DIR}"
python -m pip install einops pycocotools psutil

python - <<'PY'
import importlib
import torch

mods = ["requests", "bs4", "huggingface_hub", "sam3", "ultralytics", "paddleocr"]
for name in mods:
    module = importlib.import_module(name)
    print(f"{name}: ok ({getattr(module, '__file__', 'built-in')})")

print("torch:", torch.__version__)
print("cuda_available:", torch.cuda.is_available())
print("cuda_device_count:", torch.cuda.device_count())
PY
