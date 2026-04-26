"""
combine_luts.py

Pre-bakes a chain of .cube 3D LUTs into a single equivalent .cube LUT.
This lets FFmpeg apply ONE lut3d filter instead of N, which roughly halves
the per-frame LUT cost at 4K with no perceptible quality difference.

Output sampling uses trilinear interpolation. The output grid size defaults
to the largest input LUT's size (preserving precision).

Usage:
    python combine_luts.py luts/A.cube luts/B.cube --output luts/combined.cube
    python combine_luts.py luts/A.cube luts/B.cube --output luts/combined.cube --size 65

It is also imported by assemble_video.py, which auto-generates a cached
combined LUT under .cache/luts/ keyed on input file paths/mtimes/sizes.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import numpy as np


def parse_cube(path: str):
    """Parse a .cube 3D LUT. Returns (lut_array[B,G,R,3], size, dmin, dmax)."""
    domain_min = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    domain_max = np.array([1.0, 1.0, 1.0], dtype=np.float64)
    size = None
    samples: list[list[float]] = []

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            upper = line.upper()
            if upper.startswith("TITLE"):
                continue
            if upper.startswith("LUT_3D_SIZE"):
                size = int(line.split()[-1])
                continue
            if upper.startswith("LUT_1D_SIZE"):
                raise ValueError(f"1D LUTs are not supported: {path}")
            if upper.startswith("DOMAIN_MIN"):
                parts = line.split()[1:4]
                domain_min = np.array([float(x) for x in parts], dtype=np.float64)
                continue
            if upper.startswith("DOMAIN_MAX"):
                parts = line.split()[1:4]
                domain_max = np.array([float(x) for x in parts], dtype=np.float64)
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    samples.append([float(parts[0]), float(parts[1]), float(parts[2])])
                except ValueError:
                    continue

    if size is None:
        raise ValueError(f"No LUT_3D_SIZE in {path}")
    if len(samples) != size ** 3:
        raise ValueError(
            f"Sample count mismatch in {path}: got {len(samples)}, expected {size**3}"
        )

    arr = np.asarray(samples, dtype=np.float64)
    # .cube ordering: R varies fastest, then G, then B. So reshape as [B, G, R, 3].
    arr = arr.reshape(size, size, size, 3)
    return arr, size, domain_min, domain_max


def apply_lut_trilinear(rgb: np.ndarray, lut: np.ndarray, size: int,
                         dmin: np.ndarray, dmax: np.ndarray) -> np.ndarray:
    """Apply a 3D LUT to an RGB array (..., 3) via trilinear interpolation."""
    span = dmax - dmin
    span = np.where(span == 0, 1.0, span)
    norm = (rgb - dmin) / span
    idx = np.clip(norm * (size - 1), 0.0, size - 1)

    i0 = np.floor(idx).astype(np.int32)
    i1 = np.minimum(i0 + 1, size - 1)
    f = idx - i0

    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
    r1, g1, b1 = i1[..., 0], i1[..., 1], i1[..., 2]
    fr = f[..., 0:1]
    fg = f[..., 1:2]
    fb = f[..., 2:3]

    # lut is indexed [B, G, R]
    c000 = lut[b0, g0, r0]
    c001 = lut[b0, g0, r1]
    c010 = lut[b0, g1, r0]
    c011 = lut[b0, g1, r1]
    c100 = lut[b1, g0, r0]
    c101 = lut[b1, g0, r1]
    c110 = lut[b1, g1, r0]
    c111 = lut[b1, g1, r1]

    c00 = c000 * (1 - fr) + c001 * fr
    c01 = c010 * (1 - fr) + c011 * fr
    c10 = c100 * (1 - fr) + c101 * fr
    c11 = c110 * (1 - fr) + c111 * fr

    c0 = c00 * (1 - fg) + c01 * fg
    c1 = c10 * (1 - fg) + c11 * fg

    return c0 * (1 - fb) + c1 * fb


def write_cube(path: str, lut: np.ndarray, size: int,
               dmin: np.ndarray, dmax: np.ndarray, title: str = "Combined") -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'TITLE "{title}"\n')
        f.write(f"LUT_3D_SIZE {size}\n")
        f.write(f"DOMAIN_MIN {dmin[0]:.6f} {dmin[1]:.6f} {dmin[2]:.6f}\n")
        f.write(f"DOMAIN_MAX {dmax[0]:.6f} {dmax[1]:.6f} {dmax[2]:.6f}\n")
        # Flatten with R fastest, then G, then B (matches our [B,G,R,3] layout).
        flat = lut.reshape(-1, 3)
        for rgb in flat:
            f.write(f"{rgb[0]:.6f} {rgb[1]:.6f} {rgb[2]:.6f}\n")


def combine_lut_files(lut_paths: list[str], output_path: str,
                       output_size: int | None = None,
                       title: str | None = None) -> str:
    """Combine LUTs in order: out(x) = LUT_N(...LUT_2(LUT_1(x))). Returns output_path."""
    if not lut_paths:
        raise ValueError("No LUT files provided")

    parsed = [parse_cube(p) for p in lut_paths]
    dmin_out = parsed[0][2].copy()
    dmax_out = parsed[0][3].copy()
    out_size = int(output_size) if output_size else max(p[1] for p in parsed)

    axis = np.linspace(0.0, 1.0, out_size, dtype=np.float64)
    # Build identity grid in input domain. Index order [B, G, R, 3].
    bb, gg, rr = np.meshgrid(axis, axis, axis, indexing="ij")
    grid01 = np.stack([rr, gg, bb], axis=-1)
    grid = dmin_out + grid01 * (dmax_out - dmin_out)

    current = grid
    for lut, size, dmin, dmax in parsed:
        current = apply_lut_trilinear(current, lut, size, dmin, dmax)

    if title is None:
        title = "Combined: " + " -> ".join(Path(p).stem for p in lut_paths)
    write_cube(output_path, current, out_size, dmin_out, dmax_out, title=title)
    return output_path


def cache_key_for_luts(lut_paths: list[str], output_size: int | None = None) -> str:
    """Stable hash over LUT path/mtime/size used to key the on-disk cache."""
    h = hashlib.sha256()
    for p in lut_paths:
        st = os.stat(p)
        h.update(os.path.abspath(p).encode("utf-8"))
        h.update(str(st.st_mtime_ns).encode("ascii"))
        h.update(str(st.st_size).encode("ascii"))
    if output_size:
        h.update(f"size={output_size}".encode("ascii"))
    return h.hexdigest()[:16]


def get_or_build_combined_lut(lut_paths: list[str],
                                cache_dir: str = ".cache/luts",
                                output_size: int | None = None) -> str:
    """Return path to a cached combined LUT, building it if missing or stale."""
    if len(lut_paths) <= 1:
        return lut_paths[0] if lut_paths else ""
    key = cache_key_for_luts(lut_paths, output_size)
    out_path = os.path.join(cache_dir, f"combined_{key}.cube")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path
    print(f"  > Pre-baking {len(lut_paths)} LUTs into a single cached LUT: {out_path}")
    combine_lut_files(lut_paths, out_path, output_size=output_size)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine .cube 3D LUTs into one.")
    parser.add_argument("luts", nargs="+", help="LUTs to combine, applied left-to-right.")
    parser.add_argument("--output", "-o", required=True, help="Output .cube path.")
    parser.add_argument("--size", type=int, default=None,
                        help="Output grid size (default: max of inputs).")
    args = parser.parse_args()
    out = combine_lut_files(args.luts, args.output, output_size=args.size)
    print(f"Wrote combined LUT: {out}")


if __name__ == "__main__":
    main()
