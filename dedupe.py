from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def _dct_matrix(n: int) -> np.ndarray:
    matrix = np.zeros((n, n), dtype=np.float64)
    factor = np.pi / (2.0 * n)
    scale0 = np.sqrt(1.0 / n)
    scale = np.sqrt(2.0 / n)
    for k in range(n):
        alpha = scale0 if k == 0 else scale
        for i in range(n):
            matrix[k, i] = alpha * np.cos((2 * i + 1) * k * factor)
    return matrix


_DCT_32 = _dct_matrix(32)


def compute_phash(path: str | Path) -> str:
    image_path = Path(path)
    with Image.open(image_path) as image:
        image = image.convert("L").resize((32, 32))
        pixels = np.asarray(image, dtype=np.float64)

    transformed = _DCT_32 @ pixels @ _DCT_32.T
    low_freq = transformed[:8, :8]
    median = np.median(low_freq[1:, 1:])
    bits = low_freq > median

    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bool(bit))
    return f"{value:016x}"
