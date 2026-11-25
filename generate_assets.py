"""
Генератор продвинутых 3D-ассетов для CS2 Tactical Realism Edition (Ursina + Panda3D).
Создаёт валидные бинарные 3D-модели glTF 2.0 (.glb), детализированные текстуры (.png),
богатый набор звуковых эффектов (.wav) и кириллический шрифт (.ttf) в папке assets/.
Любой файл в assets/ можно свободно заменить скачанным с Sketchfab / Kenney / Quaternius,
а при удалении файлов игра автоматически переключится на процедурные 3D-примитивы.
"""

from __future__ import annotations

import json
import math
import shutil
import struct
import wave
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


ROOT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = ROOT_DIR / "assets"
MODELS_DIR = ASSETS_DIR / "models"
TEXTURES_DIR = ASSETS_DIR / "textures"
SOUNDS_DIR = ASSETS_DIR / "sounds"
FONTS_DIR = ASSETS_DIR / "fonts"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ГЕНЕРАЦИЯ ДЕТАЛИЗИРОВАННЫХ GLTF 2.0 BINARY (.GLB) МОДЕЛЕЙ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _rotation_matrix_xyz(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
    rx, ry, rz = map(math.radians, (rx_deg, ry_deg, rz_deg))
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float32)
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float32)
    return mz @ my @ mx


def _make_box_geometry(
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    color_rgba: tuple[float, float, float, float],
    rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
    faces = [
        ([(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)], (0, 0, 1), 1.00),
        ([(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)], (0, 0, -1), 0.92),
        ([(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)], (1, 0, 0), 0.96),
        ([(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)], (-1, 0, 0), 0.88),
        ([(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)], (0, 1, 0), 1.08),
        ([(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)], (0, -1, 0), 0.72),
    ]

    rot = _rotation_matrix_xyz(*rot_deg)
    offset = np.array(center, dtype=np.float32)

    positions: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    colors: list[tuple[float, float, float, float]] = []
    indices: list[int] = []

    for face_idx, (verts, normal, ao_shade) in enumerate(faces):
        base_idx = face_idx * 4
        n_vec = rot @ np.array(normal, dtype=np.float32)
        n_norm = n_vec / max(float(np.linalg.norm(n_vec)), 1e-6)
        shaded_col = (
            min(1.0, color_rgba[0] * ao_shade),
            min(1.0, color_rgba[1] * ao_shade),
            min(1.0, color_rgba[2] * ao_shade),
            color_rgba[3],
        )
        for v in verts:
            p_vec = (rot @ np.array(v, dtype=np.float32)) + offset
            positions.append(p_vec)
            normals.append(n_norm)
            colors.append(shaded_col)
        indices.extend([base_idx, base_idx + 1, base_idx + 2, base_idx, base_idx + 2, base_idx + 3])

    return (
        np.array(positions, dtype=np.float32),
        np.array(normals, dtype=np.float32),
        np.array(colors, dtype=np.float32),
        np.array(indices, dtype=np.uint16),
    )


def export_glb(
    out_path: Path,
    boxes: Iterable[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float, float], tuple[float, float, float]]],
    metallic: float = 0.35,
    roughness: float = 0.55,
) -> None:
    all_pos: list[np.ndarray] = []
    all_norm: list[np.ndarray] = []
    all_col: list[np.ndarray] = []
    all_idx: list[np.ndarray] = []
    vert_offset = 0

    for center, size, col, rot in boxes:
        pos, norm, vcol, idx = _make_box_geometry(center, size, col, rot)
        all_pos.append(pos)
        all_norm.append(norm)
        all_col.append(vcol)
        all_idx.append((idx.astype(np.uint32) + vert_offset).astype(np.uint16))
        vert_offset += len(pos)

    positions = np.vstack(all_pos).astype("<f4")
    normals = np.vstack(all_norm).astype("<f4")
    colors = np.vstack(all_col).astype("<f4")
    indices = np.concatenate(all_idx).astype("<u2")

    pos_bytes = positions.tobytes()
    norm_bytes = normals.tobytes()
    col_bytes = colors.tobytes()
    idx_bytes = indices.tobytes()
    if len(idx_bytes) % 4 != 0:
        idx_bytes += b"\x00" * (4 - (len(idx_bytes) % 4))

    offset_pos = 0
    offset_norm = offset_pos + len(pos_bytes)
    offset_col = offset_norm + len(norm_bytes)
    offset_idx = offset_col + len(col_bytes)
    bin_blob = pos_bytes + norm_bytes + col_bytes + idx_bytes

    pos_min = positions.min(axis=0).tolist()
    pos_max = positions.max(axis=0).tolist()

    gltf_dict = {
        "asset": {"version": "2.0", "generator": "CS2-Python-Ursina-3D-Generator"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": out_path.stem}],
        "materials": [
            {
                "name": f"{out_path.stem}_mat",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                    "metallicFactor": metallic,
                    "roughnessFactor": roughness,
                },
                "doubleSided": True,
            }
        ],
        "meshes": [
            {
                "name": f"{out_path.stem}_mesh",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2},
                        "indices": 3,
                        "material": 0,
                    }
                ],
            }
        ],
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": offset_pos, "byteLength": len(pos_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": offset_norm, "byteLength": len(norm_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": offset_col, "byteLength": len(col_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": offset_idx, "byteLength": len(indices) * 2, "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": int(len(positions)),
                "type": "VEC3",
                "min": pos_min,
                "max": pos_max,
            },
            {"bufferView": 1, "componentType": 5126, "count": int(len(normals)), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": int(len(colors)), "type": "VEC4"},
            {"bufferView": 3, "componentType": 5123, "count": int(len(indices)), "type": "SCALAR"},
        ],
    }

    json_bytes = json.dumps(gltf_dict, separators=(",", ":")).encode("utf-8")
    if len(json_bytes) % 4 != 0:
        json_bytes += b" " * (4 - (len(json_bytes) % 4))

    total_len = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
    header = struct.pack("<III", 0x46546C67, 2, total_len)
    json_chunk = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
    bin_chunk = struct.pack("<II", len(bin_blob), 0x004E4942) + bin_blob

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(header + json_chunk + bin_chunk)


def generate_models() -> None:
    dark_steel = (0.15, 0.16, 0.18, 1.0)
    gunmetal = (0.25, 0.27, 0.30, 1.0)
    wood_walnut = (0.49, 0.26, 0.11, 1.0)
    wood_dark = (0.36, 0.18, 0.08, 1.0)
    bakelite_orange = (0.72, 0.31, 0.10, 1.0)
    chrome = (0.80, 0.83, 0.87, 1.0)
    polymer_black = (0.10, 0.11, 0.12, 1.0)
    olive_green = (0.22, 0.31, 0.19, 1.0)
    lens_cyan = (0.18, 0.72, 0.88, 1.0)
    gold_accent = (0.85, 0.68, 0.22, 1.0)
    crimson_blade = (0.78, 0.12, 0.16, 1.0)

    # 1. AK-47 (детализированный автомат с цевьём, газовой камерой, прицельной планкой и ДТК)
    export_glb(
        MODELS_DIR / "ak47.glb",
        boxes=[
            ((0.0, 0.0, 0.02), (0.054, 0.072, 0.34), dark_steel, (0, 0, 0)),
            ((0.0, 0.044, 0.00), (0.048, 0.026, 0.31), gunmetal, (0, 0, 0)),
            ((0.032, 0.022, 0.06), (0.022, 0.012, 0.035), chrome, (0, 0, 0)),
            ((0.0, 0.060, 0.14), (0.020, 0.014, 0.07), dark_steel, (0, 0, 0)),
            ((0.0, 0.004, 0.27), (0.058, 0.066, 0.20), wood_walnut, (0, 0, 0)),
            ((0.0, 0.038, 0.27), (0.050, 0.028, 0.18), wood_dark, (0, 0, 0)),
            ((0.0, 0.014, 0.50), (0.019, 0.019, 0.34), dark_steel, (0, 0, 0)),
            ((0.0, 0.038, 0.44), (0.015, 0.020, 0.21), gunmetal, (0, 0, 0)),
            ((0.0, 0.048, 0.63), (0.012, 0.052, 0.026), dark_steel, (0, 0, 0)),
            ((0.0, 0.014, 0.68), (0.023, 0.023, 0.040), gunmetal, (0, 0, 0)),
            ((0.0, -0.046, -0.25), (0.046, 0.086, 0.25), wood_walnut, (8, 0, 0)),
            ((0.0, -0.055, -0.37), (0.048, 0.092, 0.020), dark_steel, (8, 0, 0)),
            ((0.0, -0.095, -0.07), (0.036, 0.125, 0.050), wood_dark, (-18, 0, 0)),
            ((0.0, -0.048, -0.01), (0.016, 0.030, 0.060), dark_steel, (0, 0, 0)),
            ((0.0, -0.115, 0.10), (0.041, 0.14, 0.072), bakelite_orange, (18, 0, 0)),
            ((0.0, -0.205, 0.145), (0.040, 0.11, 0.070), bakelite_orange, (30, 0, 0)),
        ],
        metallic=0.48,
        roughness=0.44,
    )

    # 2. M4A1-S (тактический карабин с глушителем, планкой Пикатинни и коллиматором)
    export_glb(
        MODELS_DIR / "m4a1.glb",
        boxes=[
            ((0.0, 0.0, 0.02), (0.054, 0.078, 0.30), polymer_black, (0, 0, 0)),
            ((0.0, 0.048, 0.08), (0.032, 0.014, 0.36), gunmetal, (0, 0, 0)),
            ((0.0, 0.072, 0.02), (0.040, 0.038, 0.085), dark_steel, (0, 0, 0)),
            ((0.0, 0.076, 0.06), (0.030, 0.026, 0.010), lens_cyan, (0, 0, 0)),
            ((0.0, 0.008, 0.26), (0.056, 0.062, 0.22), gunmetal, (0, 0, 0)),
            ((0.0, -0.062, 0.27), (0.028, 0.090, 0.032), polymer_black, (0, 0, 0)),
            ((0.0, 0.012, 0.44), (0.021, 0.021, 0.18), dark_steel, (0, 0, 0)),
            ((0.0, 0.012, 0.64), (0.038, 0.038, 0.25), polymer_black, (0, 0, 0)),
            ((0.0, -0.012, -0.24), (0.046, 0.094, 0.22), polymer_black, (0, 0, 0)),
            ((0.0, -0.095, -0.06), (0.036, 0.125, 0.050), polymer_black, (-16, 0, 0)),
            ((0.0, -0.128, 0.09), (0.040, 0.185, 0.068), gunmetal, (8, 0, 0)),
        ],
        metallic=0.58,
        roughness=0.38,
    )

    # 3. AWP (легендарная зелёная снайперская винтовка CS2 с оптическим прицелом и сошками)
    export_glb(
        MODELS_DIR / "awp.glb",
        boxes=[
            ((0.0, 0.0, 0.04), (0.058, 0.082, 0.44), olive_green, (0, 0, 0)),
            ((0.0, 0.046, 0.02), (0.046, 0.032, 0.34), dark_steel, (0, 0, 0)),
            ((0.038, 0.042, -0.04), (0.042, 0.014, 0.016), chrome, (0, 0, -20)),
            ((0.0, 0.105, 0.02), (0.036, 0.036, 0.30), polymer_black, (0, 0, 0)),
            ((0.0, 0.105, 0.18), (0.052, 0.052, 0.07), polymer_black, (0, 0, 0)),
            ((0.0, 0.105, -0.13), (0.044, 0.044, 0.06), polymer_black, (0, 0, 0)),
            ((0.0, 0.105, 0.216), (0.042, 0.042, 0.008), lens_cyan, (0, 0, 0)),
            ((0.0, 0.068, 0.08), (0.024, 0.038, 0.028), gunmetal, (0, 0, 0)),
            ((0.0, 0.068, -0.05), (0.024, 0.038, 0.028), gunmetal, (0, 0, 0)),
            ((0.0, 0.028, 0.50), (0.022, 0.022, 0.54), dark_steel, (0, 0, 0)),
            ((0.0, 0.028, 0.79), (0.034, 0.028, 0.065), gunmetal, (0, 0, 0)),
            ((-0.028, -0.038, 0.32), (0.014, 0.014, 0.18), dark_steel, (0, 0, 0)),
            ((0.028, -0.038, 0.32), (0.014, 0.014, 0.18), dark_steel, (0, 0, 0)),
            ((0.0, -0.032, -0.28), (0.052, 0.105, 0.26), olive_green, (4, 0, 0)),
            ((0.0, -0.088, -0.09), (0.038, 0.115, 0.052), olive_green, (-14, 0, 0)),
            ((0.0, -0.078, 0.07), (0.042, 0.085, 0.095), dark_steel, (0, 0, 0)),
        ],
        metallic=0.45,
        roughness=0.42,
    )

    # 4. MP9 (компактный скорострельный пистолет-пулемёт со складным прикладом и передней рукоятью)
    export_glb(
        MODELS_DIR / "mp9.glb",
        boxes=[
            ((0.0, 0.01, 0.04), (0.050, 0.076, 0.28), polymer_black, (0, 0, 0)),
            ((0.0, 0.055, 0.04), (0.034, 0.018, 0.24), gunmetal, (0, 0, 0)),
            ((0.0, 0.012, 0.24), (0.032, 0.032, 0.14), dark_steel, (0, 0, 0)),
            ((0.0, -0.095, 0.00), (0.036, 0.14, 0.052), polymer_black, (-8, 0, 0)),
            ((0.0, -0.175, 0.005), (0.028, 0.16, 0.038), gunmetal, (4, 0, 0)),
            ((0.0, -0.062, 0.14), (0.026, 0.095, 0.030), polymer_black, (0, 0, 0)),
            ((0.0, 0.015, -0.18), (0.018, 0.022, 0.20), gunmetal, (0, 0, 0)),
            ((0.0, -0.015, -0.28), (0.036, 0.085, 0.020), polymer_black, (0, 0, 0)),
        ],
        metallic=0.52,
        roughness=0.42,
    )

    # 5. XM1014 (полуавтоматический боевой дробовик)
    export_glb(
        MODELS_DIR / "shotgun.glb",
        boxes=[
            ((0.0, 0.01, 0.02), (0.054, 0.078, 0.30), gunmetal, (0, 0, 0)),
            ((0.0, 0.032, 0.38), (0.024, 0.024, 0.46), dark_steel, (0, 0, 0)),
            ((0.0, 0.002, 0.35), (0.022, 0.022, 0.40), chrome, (0, 0, 0)),
            ((0.0, 0.008, 0.28), (0.058, 0.056, 0.22), polymer_black, (0, 0, 0)),
            ((0.0, -0.042, -0.24), (0.048, 0.090, 0.24), polymer_black, (7, 0, 0)),
            ((0.0, -0.092, -0.07), (0.038, 0.115, 0.050), polymer_black, (-18, 0, 0)),
        ],
        metallic=0.60,
        roughness=0.38,
    )

    # 6. FAMAS (штурмовая винтовка булл-пап с высокой рукояткой переноски)
    export_glb(
        MODELS_DIR / "famas.glb",
        boxes=[
            ((0.0, 0.0, 0.0), (0.056, 0.085, 0.42), polymer_black, (0, 0, 0)),
            ((0.0, 0.082, 0.04), (0.038, 0.024, 0.30), gunmetal, (0, 0, 0)),
            ((0.0, 0.055, 0.16), (0.034, 0.045, 0.032), polymer_black, (0, 0, 0)),
            ((0.0, 0.055, -0.08), (0.034, 0.045, 0.032), polymer_black, (0, 0, 0)),
            ((0.0, 0.015, 0.31), (0.020, 0.020, 0.22), dark_steel, (0, 0, 0)),
            ((0.0, -0.092, 0.04), (0.036, 0.12, 0.050), polymer_black, (-14, 0, 0)),
            ((0.0, -0.125, -0.14), (0.038, 0.18, 0.065), gunmetal, (6, 0, 0)),
        ],
        metallic=0.50,
        roughness=0.45,
    )

    # 7. USP-S (тактический пистолет спецназа с глушителем)
    export_glb(
        MODELS_DIR / "usp.glb",
        boxes=[
            ((0.0, 0.022, 0.05), (0.040, 0.048, 0.21), gunmetal, (0, 0, 0)),
            ((0.0, -0.012, 0.04), (0.038, 0.028, 0.19), polymer_black, (0, 0, 0)),
            ((0.0, 0.020, 0.25), (0.032, 0.032, 0.20), polymer_black, (0, 0, 0)),
            ((0.0, -0.090, -0.03), (0.036, 0.135, 0.056), polymer_black, (-14, 0, 0)),
            ((0.0, -0.038, 0.03), (0.016, 0.028, 0.058), polymer_black, (0, 0, 0)),
        ],
        metallic=0.55,
        roughness=0.38,
    )

    # 8. Desert Eagle (хромированный с золотистым стволом)
    export_glb(
        MODELS_DIR / "deagle.glb",
        boxes=[
            ((0.0, 0.022, 0.08), (0.048, 0.065, 0.27), chrome, (0, 0, 0)),
            ((0.0, 0.028, 0.10), (0.028, 0.045, 0.18), gold_accent, (0, 0, 0)),
            ((0.0, -0.015, 0.04), (0.044, 0.032, 0.22), dark_steel, (0, 0, 0)),
            ((0.0, -0.095, -0.03), (0.040, 0.145, 0.062), polymer_black, (-15, 0, 0)),
            ((0.0, -0.042, 0.04), (0.018, 0.032, 0.065), dark_steel, (0, 0, 0)),
            ((0.0, 0.058, 0.20), (0.012, 0.016, 0.022), polymer_black, (0, 0, 0)),
        ],
        metallic=0.84,
        roughness=0.22,
    )

    # 9. Glock-18 (пистолет T-стороны с переключателем очереди)
    export_glb(
        MODELS_DIR / "glock.glb",
        boxes=[
            ((0.0, 0.020, 0.05), (0.038, 0.044, 0.20), dark_steel, (0, 0, 0)),
            ((0.0, -0.012, 0.04), (0.037, 0.028, 0.19), olive_green, (0, 0, 0)),
            ((0.0, -0.088, -0.03), (0.035, 0.132, 0.054), olive_green, (-16, 0, 0)),
            ((0.0, -0.038, 0.03), (0.016, 0.026, 0.055), polymer_black, (0, 0, 0)),
        ],
        metallic=0.45,
        roughness=0.48,
    )

    # 10. Karambit / Tactical Crimson Knife
    export_glb(
        MODELS_DIR / "knife.glb",
        boxes=[
            ((0.0, -0.065, -0.10), (0.038, 0.038, 0.012), gunmetal, (0, 0, 0)),
            ((0.0, -0.03, -0.04), (0.030, 0.040, 0.13), polymer_black, (12, 0, 0)),
            ((0.0, -0.008, 0.03), (0.052, 0.068, 0.018), gunmetal, (10, 0, 0)),
            ((0.0, 0.012, 0.13), (0.010, 0.044, 0.18), crimson_blade, (4, 0, 0)),
            ((0.0, 0.032, 0.24), (0.008, 0.032, 0.10), chrome, (-18, 0, 0)),
        ],
        metallic=0.86,
        roughness=0.18,
    )

    # 11. C4 Explosive Pack
    c4_tan = (0.68, 0.62, 0.46, 1.0)
    c4_screen = (0.12, 0.34, 0.18, 1.0)
    c4_wire = (0.85, 0.18, 0.14, 1.0)
    export_glb(
        MODELS_DIR / "c4.glb",
        boxes=[
            ((-0.07, 0.04, 0.0), (0.12, 0.08, 0.28), c4_tan, (0, 0, 0)),
            ((0.07, 0.04, 0.0), (0.12, 0.08, 0.28), c4_tan, (0, 0, 0)),
            ((0.0, 0.085, 0.01), (0.14, 0.035, 0.16), polymer_black, (0, 0, 0)),
            ((0.0, 0.105, 0.04), (0.10, 0.010, 0.055), c4_screen, (0, 0, 0)),
            ((0.0, 0.065, -0.09), (0.18, 0.020, 0.025), c4_wire, (0, 0, 0)),
        ],
        metallic=0.25,
        roughness=0.65,
    )

    # 12. Explosive Red Barrel (бочка с горючим 0.7x1.15x0.7, низ в y=0)
    barrel_red = (0.78, 0.16, 0.14, 1.0)
    barrel_band = (0.90, 0.74, 0.16, 1.0)
    export_glb(
        MODELS_DIR / "barrel.glb",
        boxes=[
            ((0.0, 0.58, 0.0), (0.66, 1.14, 0.66), barrel_red, (0, 0, 0)),
            ((0.0, 0.58, 0.0), (0.66, 1.14, 0.66), barrel_red, (0, 45, 0)),
            ((0.0, 0.58, 0.0), (0.70, 0.18, 0.70), barrel_band, (0, 22.5, 0)),
            ((0.0, 1.12, 0.0), (0.70, 0.06, 0.70), dark_steel, (0, 22.5, 0)),
            ((0.0, 0.04, 0.0), (0.70, 0.06, 0.70), dark_steel, (0, 22.5, 0)),
        ],
        metallic=0.62,
        roughness=0.36,
    )

    # 13. Враг-бот повышенной детализации
    sand_jacket = (0.68, 0.56, 0.38, 1.0)
    kevlar_vest = (0.18, 0.20, 0.22, 1.0)
    cargo_pants = (0.26, 0.30, 0.24, 1.0)
    balaclava = (0.14, 0.14, 0.16, 1.0)
    visor_red = (0.88, 0.22, 0.16, 1.0)

    export_glb(
        MODELS_DIR / "enemy.glb",
        boxes=[
            ((-0.14, 0.42, 0.0), (0.19, 0.84, 0.22), cargo_pants, (0, 0, 0)),
            ((0.14, 0.42, 0.0), (0.19, 0.84, 0.22), cargo_pants, (0, 0, 0)),
            ((-0.14, 0.45, 0.11), (0.16, 0.14, 0.06), polymer_black, (0, 0, 0)),
            ((0.14, 0.45, 0.11), (0.16, 0.14, 0.06), polymer_black, (0, 0, 0)),
            ((-0.14, 0.06, 0.04), (0.20, 0.12, 0.28), polymer_black, (0, 0, 0)),
            ((0.14, 0.06, 0.04), (0.20, 0.12, 0.28), polymer_black, (0, 0, 0)),
            ((0.0, 1.16, 0.0), (0.50, 0.66, 0.30), sand_jacket, (0, 0, 0)),
            ((0.0, 1.18, 0.02), (0.45, 0.48, 0.34), kevlar_vest, (0, 0, 0)),
            ((-0.11, 1.08, 0.19), (0.09, 0.14, 0.06), gunmetal, (0, 0, 0)),
            ((0.11, 1.08, 0.19), (0.09, 0.14, 0.06), gunmetal, (0, 0, 0)),
            ((0.0, 1.20, -0.20), (0.34, 0.40, 0.16), olive_green, (0, 0, 0)),
            ((-0.33, 1.18, 0.12), (0.15, 0.54, 0.18), sand_jacket, (-35, 0, 0)),
            ((0.33, 1.18, 0.14), (0.15, 0.54, 0.18), sand_jacket, (-42, 0, 0)),
            ((0.12, 1.12, 0.42), (0.08, 0.12, 0.58), dark_steel, (0, -10, 0)),
            ((0.0, 1.68, 0.0), (0.32, 0.34, 0.32), balaclava, (0, 0, 0)),
            ((0.0, 1.76, -0.01), (0.36, 0.18, 0.36), kevlar_vest, (0, 0, 0)),
            ((0.0, 1.70, 0.16), (0.26, 0.09, 0.06), visor_red, (0, 0, 0)),
        ],
        metallic=0.22,
        roughness=0.68,
    )

    # 14. Военный деревянный ящик 1x1x1
    crate_main = (0.64, 0.48, 0.28, 1.0)
    crate_trim = (0.43, 0.30, 0.16, 1.0)
    export_glb(
        MODELS_DIR / "crate.glb",
        boxes=[
            ((0.0, 0.0, 0.0), (0.96, 0.96, 0.96), crate_main, (0, 0, 0)),
            ((0.0, 0.46, 0.0), (1.00, 0.08, 1.00), crate_trim, (0, 0, 0)),
            ((0.0, -0.46, 0.0), (1.00, 0.08, 1.00), crate_trim, (0, 0, 0)),
            ((0.46, 0.0, 0.46), (0.08, 0.96, 0.08), crate_trim, (0, 0, 0)),
            ((-0.46, 0.0, 0.46), (0.08, 0.96, 0.08), crate_trim, (0, 0, 0)),
            ((0.46, 0.0, -0.46), (0.08, 0.96, 0.08), crate_trim, (0, 0, 0)),
            ((-0.46, 0.0, -0.46), (0.08, 0.96, 0.08), crate_trim, (0, 0, 0)),
        ],
        metallic=0.08,
        roughness=0.84,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ГЕНЕРАЦИЯ ВЫСОКОДЕТАЛИЗИРОВАННЫХ ТЕКСТУР (.PNG)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def generate_textures() -> None:
    TEXTURES_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)

    # 1. Каменная кладка песчаника Dust2 512x512 с фасками (wall_sandstone.png)
    w, h = 512, 512
    base = np.zeros((h, w, 3), dtype=np.float32)
    base[:, :] = [216, 190, 146]
    base += rng.normal(0, 8.5, (h, w, 3))
    yy_grad = np.linspace(1.04, 0.92, h)[:, None, None]
    base *= yy_grad
    for row_idx, y in enumerate(range(0, h, 64)):
        y_end = min(h, y + 64)
        tone = float(rng.uniform(0.95, 1.05))
        base[y:y_end, :] *= tone
        # Световая фаска сверху и тень раствора снизу
        base[y:min(h, y + 3), :] *= 0.68
        base[min(h - 1, y + 3):min(h, y + 6), :] *= 1.09
        x_shift = (row_idx % 2) * 64
        for x in range(x_shift, w, 128):
            base[y:y_end, max(0, x - 2):min(w, x + 2)] *= 0.72
    Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "wall_sandstone.png")

    # 2. Утрамбованный песок и каменная крошка 512x512 (floor_dust.png)
    floor_arr = np.zeros((h, w, 3), dtype=np.float32)
    floor_arr[:, :] = [198, 173, 130]
    ripple = np.sin(np.linspace(0, 12 * np.pi, h))[:, None, None] * 5.5
    floor_arr += ripple + rng.normal(0, 13.0, (h, w, 3))
    img_floor = Image.fromarray(np.clip(floor_arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.5))
    img_floor.save(TEXTURES_DIR / "floor_dust.png")

    # 3. Асфальтовая дорога / бетонная плита (asphalt_road.png)
    asph = np.zeros((256, 256, 3), dtype=np.float32)
    asph[:, :] = [74, 78, 84]
    asph += rng.normal(0, 10.0, (256, 256, 3))
    asph[:, 122:134] = [215, 172, 48]  # дорожная разметка
    Image.fromarray(np.clip(asph, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "asphalt_road.png")

    # 4. Рифлёный металл / бронеплита (metal_plate.png)
    met = np.zeros((256, 256, 3), dtype=np.float32)
    met[:, :] = [92, 98, 108]
    met += rng.normal(0, 6.0, (256, 256, 3))
    for i in range(0, 256, 16):
        met[i:i + 2, :] *= 1.18
        met[:, i:i + 2] *= 0.86
    Image.fromarray(np.clip(met, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "metal_plate.png")

    # 5. Морской контейнер (container_blue.png)
    cont = np.zeros((256, 256, 3), dtype=np.float32)
    cont[:, :] = [44, 88, 138]
    for x in range(0, 256, 16):
        cont[:, x:x + 6] *= 1.16
        cont[:, x + 8:x + 14] *= 0.80
    cont += rng.normal(0, 5.0, (256, 256, 3))
    Image.fromarray(np.clip(cont, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "container_blue.png")

    # 6. Мешковина мешков с песком (sandbag_fabric.png)
    sb = np.zeros((128, 128, 3), dtype=np.float32)
    sb[:, :] = [176, 154, 112]
    sb[::2, :] *= 0.93
    sb[:, ::2] *= 1.05
    sb += rng.normal(0, 7.0, (128, 128, 3))
    Image.fromarray(np.clip(sb, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "sandbag_fabric.png")

    # 7. Военный деревянный ящик (crate_wood.png)
    crate_img = Image.new("RGB", (256, 256), (168, 124, 74))
    draw = ImageDraw.Draw(crate_img)
    for y in range(0, 256, 32):
        shade = int(rng.integers(-12, 12))
        draw.rectangle([0, y, 255, y + 30], fill=(168 + shade, 124 + shade, 74 + shade))
        draw.line([0, y, 255, y], fill=(108, 74, 38), width=2)
    draw.rectangle([0, 0, 255, 255], outline=(98, 66, 34), width=14)
    draw.line([10, 10, 245, 245], fill=(118, 82, 44), width=14)
    draw.line([245, 10, 10, 245], fill=(118, 82, 44), width=14)
    draw.rectangle([86, 108, 170, 148], fill=(48, 44, 38))
    crate_img.save(TEXTURES_DIR / "crate_wood.png")

    # 8. Бочка с опасным грузом (barrel_hazard.png)
    b_img = Image.new("RGB", (128, 128), (195, 38, 32))
    b_draw = ImageDraw.Draw(b_img)
    b_draw.rectangle([0, 46, 127, 82], fill=(235, 192, 34))
    for sx in range(-64, 160, 24):
        b_draw.polygon([(sx, 82), (sx + 12, 82), (sx + 28, 46), (sx + 16, 46)], fill=(28, 28, 30))
    b_img.save(TEXTURES_DIR / "barrel_hazard.png")

    # 9. Вспышка выстрела с альфа-каналом (muzzle_flash.png)
    mf_size = 128
    mf_img = Image.new("RGBA", (mf_size, mf_size), (0, 0, 0, 0))
    mf_draw = ImageDraw.Draw(mf_img)
    cx, cy = mf_size // 2, mf_size // 2
    for r in range(54, 4, -4):
        alpha = int(235 * (1 - r / 56) ** 1.65)
        col = (255, min(255, int(155 + (56 - r) * 2)), int(max(0, 88 - r * 1.5)), alpha)
        mf_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    mf_draw.polygon([(cx, 2), (cx + 11, cy), (cx, mf_size - 2), (cx - 11, cy)], fill=(255, 244, 175, 240))
    mf_draw.polygon([(2, cy), (cx, cy + 11), (mf_size - 2, cy), (cx, cy - 11)], fill=(255, 244, 175, 240))
    mf_img = mf_img.filter(ImageFilter.GaussianBlur(1.4))
    mf_img.save(TEXTURES_DIR / "muzzle_flash.png")

    # 10. Полупрозрачный градиент главного меню (menu_bg.png)
    bg_w, bg_h = 800, 450
    yy = np.linspace(0, 1, bg_h)[:, None]
    xx = np.linspace(0, 1, bg_w)[None, :]
    r_ch = np.clip(14 + 195 * (xx ** 2.3) * (1 - yy * 0.55), 0, 255)
    g_ch = np.clip(20 + 102 * (xx ** 2.1) * (1 - yy * 0.65), 0, 255)
    b_ch = np.clip(34 + 52 * (1 - xx) * (1 - yy * 0.4), 0, 255)
    a_ch = np.clip(215 - 150 * xx, 55, 225)
    bg_arr = np.dstack([
        np.broadcast_to(r_ch, (bg_h, bg_w)),
        np.broadcast_to(g_ch, (bg_h, bg_w)),
        np.broadcast_to(b_ch, (bg_h, bg_w)),
        np.broadcast_to(a_ch, (bg_h, bg_w)),
    ]).astype(np.uint8)
    bg_img = Image.fromarray(bg_arr, mode="RGBA")
    bg_draw = ImageDraw.Draw(bg_img)
    for offset in range(-250, 1000, 52):
        bg_draw.line([(offset, bg_h), (offset + 210, 0)], fill=(242, 152, 38, 70), width=1)
    bg_img.save(TEXTURES_DIR / "menu_bg.png")

    # 11. Иконка здоровья HUD (icon_hp.png)
    hp_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    hp_d = ImageDraw.Draw(hp_img)
    hp_d.rounded_rectangle([22, 8, 42, 56], radius=4, fill=(240, 245, 250, 255))
    hp_d.rounded_rectangle([8, 22, 56, 42], radius=4, fill=(240, 245, 250, 255))
    hp_img.save(TEXTURES_DIR / "icon_hp.png")

    # 12. Иконка брони Kevlar HUD (icon_armor.png)
    ar_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ar_d = ImageDraw.Draw(ar_img)
    ar_d.polygon([(32, 6), (54, 16), (50, 40), (32, 58), (14, 40), (10, 16)], fill=(95, 175, 255, 255))
    ar_d.polygon([(32, 13), (47, 20), (44, 38), (32, 50), (20, 38), (17, 20)], fill=(45, 115, 205, 255))
    ar_img.save(TEXTURES_DIR / "icon_armor.png")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ГЕНЕРАЦИЯ РАСШИРЕННОГО ЗВУКОВОГО ДВИЖКА (.WAV)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _save_wav(path: Path, samples: np.ndarray, sample_rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max(float(np.max(np.abs(samples))), 1e-6)
    if peak > 0.98:
        samples = samples / peak * 0.95
    pcm16 = np.clip(samples * 32767.0, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())


def generate_sounds() -> None:
    sr = 22050
    rng = np.random.default_rng(1337)

    # AK-47
    t = np.linspace(0, 0.24, int(sr * 0.24), endpoint=False)
    ak = (
        rng.normal(0, 1.0, len(t)) * np.exp(-t * 24.0) * 0.75
        + np.sin(2 * np.pi * (155 * np.exp(-t * 14)) * t) * np.exp(-t * 18.0) * 0.85
    )
    _save_wav(SOUNDS_DIR / "ak47_shoot.wav", np.tanh(ak * 1.8), sr)

    # M4A1-S (silenced)
    t_m4 = np.linspace(0, 0.16, int(sr * 0.16), endpoint=False)
    m4 = (
        rng.normal(0, 0.65, len(t_m4)) * np.exp(-t_m4 * 42.0)
        + np.sin(2 * np.pi * (240 * np.exp(-t_m4 * 22)) * t_m4) * np.exp(-t_m4 * 32.0) * 0.7
    )
    _save_wav(SOUNDS_DIR / "m4a1_shoot.wav", m4 * 0.8, sr)

    # AWP (громовой раскат снайперки!)
    t_awp = np.linspace(0, 0.58, int(sr * 0.58), endpoint=False)
    awp = (
        rng.normal(0, 1.25, len(t_awp)) * np.exp(-t_awp * 9.5) * 0.9
        + np.sin(2 * np.pi * (88 * np.exp(-t_awp * 5.5)) * t_awp) * np.exp(-t_awp * 7.5) * 1.2
    )
    _save_wav(SOUNDS_DIR / "awp_shoot.wav", np.tanh(awp * 2.4), sr)

    # MP9 SMG
    t_mp = np.linspace(0, 0.13, int(sr * 0.13), endpoint=False)
    mp = (
        rng.normal(0, 0.85, len(t_mp)) * np.exp(-t_mp * 36.0)
        + np.sin(2 * np.pi * (210 * np.exp(-t_mp * 19)) * t_mp) * np.exp(-t_mp * 28.0) * 0.75
    )
    _save_wav(SOUNDS_DIR / "mp9_shoot.wav", np.tanh(mp * 1.6), sr)

    # XM1014 Shotgun
    t_sg = np.linspace(0, 0.34, int(sr * 0.34), endpoint=False)
    sg = (
        rng.normal(0, 1.15, len(t_sg)) * np.exp(-t_sg * 16.0)
        + np.sin(2 * np.pi * (105 * np.exp(-t_sg * 11)) * t_sg) * np.exp(-t_sg * 14.0) * 1.0
    )
    _save_wav(SOUNDS_DIR / "shotgun_shoot.wav", np.tanh(sg * 2.1), sr)

    # FAMAS
    t_fa = np.linspace(0, 0.19, int(sr * 0.19), endpoint=False)
    fa = (
        rng.normal(0, 0.9, len(t_fa)) * np.exp(-t_fa * 29.0)
        + np.sin(2 * np.pi * (180 * np.exp(-t_fa * 16)) * t_fa) * np.exp(-t_fa * 22.0) * 0.8
    )
    _save_wav(SOUNDS_DIR / "famas_shoot.wav", np.tanh(fa * 1.7), sr)

    # USP-S (тихий тактический хлопок)
    t_usp = np.linspace(0, 0.14, int(sr * 0.14), endpoint=False)
    usp = (
        rng.normal(0, 0.55, len(t_usp)) * np.exp(-t_usp * 48.0)
        + np.sin(2 * np.pi * (290 * np.exp(-t_usp * 26)) * t_usp) * np.exp(-t_usp * 36.0) * 0.65
    )
    _save_wav(SOUNDS_DIR / "usp_shoot.wav", usp * 0.82, sr)

    # Desert Eagle
    t_de = np.linspace(0, 0.36, int(sr * 0.36), endpoint=False)
    de = (
        rng.normal(0, 1.1, len(t_de)) * np.exp(-t_de * 15.0) * 0.8
        + np.sin(2 * np.pi * (110 * np.exp(-t_de * 9)) * t_de) * np.exp(-t_de * 12.0) * 1.0
    )
    _save_wav(SOUNDS_DIR / "deagle_shoot.wav", np.tanh(de * 2.1), sr)

    # Glock-18
    t_gl = np.linspace(0, 0.15, int(sr * 0.15), endpoint=False)
    gl = (
        rng.normal(0, 0.8, len(t_gl)) * np.exp(-t_gl * 34.0)
        + np.sin(2 * np.pi * (195 * np.exp(-t_gl * 18)) * t_gl) * np.exp(-t_gl * 26.0) * 0.72
    )
    _save_wav(SOUNDS_DIR / "glock_shoot.wav", np.tanh(gl * 1.5), sr)

    # Knife slash
    t_kn = np.linspace(0, 0.15, int(sr * 0.15), endpoint=False)
    kn = rng.normal(0, 0.5, len(t_kn)) * np.sin(np.pi * t_kn / 0.15) + 0.28 * np.sin(2 * np.pi * 1750 * t_kn) * np.exp(-t_kn * 35)
    _save_wav(SOUNDS_DIR / "knife_slash.wav", kn * 0.78, sr)

    # Reload
    t_rl = np.linspace(0, 0.55, int(sr * 0.55), endpoint=False)
    rl = np.zeros_like(t_rl)
    for click_t, freq in [(0.04, 880), (0.22, 1180), (0.40, 690)]:
        mask = t_rl >= click_t
        dt_c = t_rl[mask] - click_t
        rl[mask] += (np.sin(2 * np.pi * freq * dt_c) + rng.normal(0, 0.5, len(dt_c))) * np.exp(-dt_c * 55.0) * 0.6
    _save_wav(SOUNDS_DIR / "reload.wav", rl, sr)

    # Empty click
    t_em = np.linspace(0, 0.06, int(sr * 0.06), endpoint=False)
    em = (np.sin(2 * np.pi * 1450 * t_em) + rng.normal(0, 0.4, len(t_em))) * np.exp(-t_em * 95.0) * 0.55
    _save_wav(SOUNDS_DIR / "empty_click.wav", em, sr)

    # Shell clink (звон латунной гильзы об пол!)
    t_sh = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
    sh = (0.6 * np.sin(2 * np.pi * 5200 * t_sh) + 0.4 * np.sin(2 * np.pi * 6850 * t_sh)) * np.exp(-t_sh * 58.0) * 0.45
    _save_wav(SOUNDS_DIR / "shell_clink.wav", sh, sr)

    # Footstep
    t_fs = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
    fs = rng.normal(0, 0.5, len(t_fs)) * np.exp(-t_fs * 45.0) + 0.3 * np.sin(2 * np.pi * 95 * t_fs) * np.exp(-t_fs * 50.0)
    _save_wav(SOUNDS_DIR / "footstep.wav", fs * 0.55, sr)

    # Hitmarker & Headshot
    t_hm = np.linspace(0, 0.05, int(sr * 0.05), endpoint=False)
    _save_wav(SOUNDS_DIR / "hitmarker.wav", np.sin(2 * np.pi * 2100 * t_hm) * np.exp(-t_hm * 85.0) * 0.65, sr)

    t_hs = np.linspace(0, 0.16, int(sr * 0.16), endpoint=False)
    hs = (np.sin(2 * np.pi * 2950 * t_hs) + 0.6 * np.sin(2 * np.pi * 4120 * t_hs)) * np.exp(-t_hs * 28.0) * 0.72
    _save_wav(SOUNDS_DIR / "headshot.wav", hs, sr)

    # Player hurt
    t_ph = np.linspace(0, 0.18, int(sr * 0.18), endpoint=False)
    ph = (np.sin(2 * np.pi * 130 * t_ph) + rng.normal(0, 0.4, len(t_ph))) * np.exp(-t_ph * 22.0) * 0.75
    _save_wav(SOUNDS_DIR / "player_hurt.wav", ph, sr)

    # Explosion (HE Grenade / Barrel / C4)
    t_ex = np.linspace(0, 0.85, int(sr * 0.85), endpoint=False)
    ex = (
        rng.normal(0, 1.3, len(t_ex)) * np.exp(-t_ex * 5.2)
        + np.sin(2 * np.pi * (62 * np.exp(-t_ex * 3.0)) * t_ex) * np.exp(-t_ex * 4.5) * 1.4
    )
    _save_wav(SOUNDS_DIR / "explosion.wav", np.tanh(ex * 2.5), sr)

    # Flashbang (хлопок + звон в ушах!)
    t_fb = np.linspace(0, 0.70, int(sr * 0.70), endpoint=False)
    fb = rng.normal(0, 1.1, len(t_fb)) * np.exp(-t_fb * 28.0) + 0.35 * np.sin(2 * np.pi * 3450 * t_fb) * np.exp(-t_fb * 3.2)
    _save_wav(SOUNDS_DIR / "flashbang.wav", np.tanh(fb * 1.8), sr)

    # Smoke hiss / Molotov burst
    t_sm = np.linspace(0, 0.60, int(sr * 0.60), endpoint=False)
    sm = rng.normal(0, 0.65, len(t_sm)) * np.sin(np.pi * np.minimum(1.0, t_sm / 0.60)) * 0.7
    _save_wav(SOUNDS_DIR / "smoke_hiss.wav", sm, sr)

    # C4 Beep, Plant, Defuse
    t_bp = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
    _save_wav(SOUNDS_DIR / "c4_beep.wav", np.sin(2 * np.pi * 2650 * t_bp) * np.exp(-t_bp * 22.0) * 0.75, sr)

    t_pl = np.linspace(0, 0.32, int(sr * 0.32), endpoint=False)
    pl = np.sin(2 * np.pi * (900 + 800 * t_pl) * t_pl) * np.exp(-t_pl * 8.0) * 0.65
    _save_wav(SOUNDS_DIR / "c4_plant.wav", pl, sr)

    t_df = np.linspace(0, 0.40, int(sr * 0.40), endpoint=False)
    df = (0.5 * np.sin(2 * np.pi * 523.25 * t_df) + 0.5 * np.sin(2 * np.pi * 783.99 * t_df)) * np.exp(-t_df * 5.5)
    _save_wav(SOUNDS_DIR / "c4_defuse.wav", df, sr)

    # Buy item & Killstreak chime
    t_by = np.linspace(0, 0.18, int(sr * 0.18), endpoint=False)
    by = (0.5 * np.sin(2 * np.pi * 1320 * t_by) + 0.5 * np.sin(2 * np.pi * 1760 * np.maximum(0, t_by - 0.05))) * np.exp(-t_by * 16.0)
    _save_wav(SOUNDS_DIR / "buy_item.wav", by * 0.7, sr)

    t_ks = np.linspace(0, 0.45, int(sr * 0.45), endpoint=False)
    ks = (
        0.35 * np.sin(2 * np.pi * 440 * t_ks)
        + 0.35 * np.sin(2 * np.pi * 554.37 * t_ks)
        + 0.35 * np.sin(2 * np.pi * 659.25 * t_ks)
    ) * np.exp(-t_ks * 4.2)
    _save_wav(SOUNDS_DIR / "killstreak.wav", ks, sr)

    # Round Win / Lose / Menu Music
    t_win = np.linspace(0, 1.1, int(sr * 1.1), endpoint=False)
    win = (
        0.35 * np.sin(2 * np.pi * 261.63 * t_win)
        + 0.30 * np.sin(2 * np.pi * 329.63 * t_win)
        + 0.35 * np.sin(2 * np.pi * 392.00 * t_win)
    ) * np.exp(-t_win * 1.9)
    _save_wav(SOUNDS_DIR / "round_win.wav", win, sr)

    t_lose = np.linspace(0, 1.1, int(sr * 1.1), endpoint=False)
    lose = (
        0.45 * np.sin(2 * np.pi * 146.83 * t_lose)
        + 0.40 * np.sin(2 * np.pi * 155.56 * t_lose)
    ) * np.exp(-t_lose * 1.8)
    _save_wav(SOUNDS_DIR / "round_lose.wav", lose, sr)

    dur = 4.0
    t_mu = np.linspace(0, dur, int(sr * dur), endpoint=False)
    pad = (
        0.22 * np.sin(2 * np.pi * 110.0 * t_mu)
        + 0.16 * np.sin(2 * np.pi * 164.81 * t_mu)
        + 0.12 * np.sin(2 * np.pi * 220.0 * t_mu) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t_mu))
    )
    pulse_env = (np.sin(2 * np.pi * 2.0 * t_mu) > 0.7).astype(np.float32)
    pulse = 0.08 * np.sin(2 * np.pi * 440.0 * t_mu) * pulse_env
    fade = np.minimum(np.minimum(t_mu / 0.08, (dur - t_mu) / 0.08), 1.0)
    _save_wav(SOUNDS_DIR / "menu_music.wav", (pad + pulse) * fade, sr)


def copy_default_font() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("C:/Windows/Fonts/bahnschrift.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]
    target = FONTS_DIR / "hud_font.ttf"
    if target.exists():
        return
    for src in candidates:
        if src.exists():
            shutil.copy2(src, target)
            break


def ensure_all_starter_assets() -> None:
    generate_models()
    generate_textures()
    generate_sounds()
    copy_default_font()


if __name__ == "__main__":
    ensure_all_starter_assets()
    print("Starter 3D assets successfully generated in:", ASSETS_DIR)
