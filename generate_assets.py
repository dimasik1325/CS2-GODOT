"""
Генератор базовых игровых ассетов для CS2 Clone (Ursina).
Создаёт валидные бинарные 3D-модели (.glb), текстуры (.png),
звуковые эффекты (.wav) и шрифт (.ttf) в папке assets/,
чтобы игра запускалась сразу «из коробки» со звуком, текстурами и 3D-моделями.
Любой файл в assets/ можно свободно заменить скачанным с Sketchfab / Kenney / Quaternius.
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
# 1. ГЕНЕРАЦИЯ ВАЛИДНЫХ GLTF 2.0 BINARY (.GLB) МОДЕЛЕЙ
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
    """Создаёт вершины, нормали, цвета вершин и индексы для ориентированного параллелепипеда."""
    hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
    faces = [
        # +Z (передняя грань)
        ([(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)], (0, 0, 1)),
        # -Z (задняя грань)
        ([(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)], (0, 0, -1)),
        # +X (правая грань)
        ([(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)], (1, 0, 0)),
        # -X (левая грань)
        ([(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)], (-1, 0, 0)),
        # +Y (верхняя грань)
        ([(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)], (0, 1, 0)),
        # -Y (нижняя грань)
        ([(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)], (0, -1, 0)),
    ]

    rot = _rotation_matrix_xyz(*rot_deg)
    offset = np.array(center, dtype=np.float32)

    positions: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    colors: list[tuple[float, float, float, float]] = []
    indices: list[int] = []

    for face_idx, (verts, normal) in enumerate(faces):
        base_idx = face_idx * 4
        n_vec = rot @ np.array(normal, dtype=np.float32)
        n_norm = n_vec / max(float(np.linalg.norm(n_vec)), 1e-6)
        for v in verts:
            p_vec = (rot @ np.array(v, dtype=np.float32)) + offset
            positions.append(p_vec)
            normals.append(n_norm)
            colors.append(color_rgba)
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
    metallic: float = 0.25,
    roughness: float = 0.65,
) -> None:
    """Упаковывает список боксов в стандартный бинарный файл glTF 2.0 (.glb)."""
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
        "asset": {"version": "2.0", "generator": "CS2-Python-Ursina-Generator"},
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
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": int(len(normals)),
                "type": "VEC3",
            },
            {
                "bufferView": 2,
                "componentType": 5126,
                "count": int(len(colors)),
                "type": "VEC4",
            },
            {
                "bufferView": 3,
                "componentType": 5123,
                "count": int(len(indices)),
                "type": "SCALAR",
            },
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
    dark_steel = (0.16, 0.17, 0.19, 1.0)
    gunmetal = (0.24, 0.26, 0.29, 1.0)
    wood_walnut = (0.48, 0.27, 0.12, 1.0)
    bakelite_orange = (0.68, 0.30, 0.10, 1.0)
    chrome = (0.76, 0.79, 0.83, 1.0)
    polymer_black = (0.11, 0.12, 0.13, 1.0)

    # 1. AK-47 (ствол вдоль +Z)
    export_glb(
        MODELS_DIR / "ak47.glb",
        boxes=[
            ((0.0, 0.0, 0.02), (0.055, 0.075, 0.34), dark_steel, (0, 0, 0)),       # ствольная коробка
            ((0.0, 0.042, 0.01), (0.048, 0.025, 0.30), gunmetal, (0, 0, 0)),       # крышка коробки
            ((0.0, 0.005, 0.27), (0.058, 0.068, 0.19), wood_walnut, (0, 0, 0)),    # деревянное цевьё
            ((0.0, 0.015, 0.49), (0.020, 0.020, 0.32), dark_steel, (0, 0, 0)),     # ствол
            ((0.0, 0.038, 0.43), (0.016, 0.022, 0.20), gunmetal, (0, 0, 0)),       # газовая трубка
            ((0.0, 0.048, 0.62), (0.012, 0.050, 0.025), dark_steel, (0, 0, 0)),    # мушка
            ((0.0, -0.045, -0.25), (0.048, 0.085, 0.24), wood_walnut, (8, 0, 0)),  # деревянный приклад
            ((0.0, -0.095, -0.07), (0.038, 0.12, 0.052), wood_walnut, (-18, 0, 0)),# рукоятка
            ((0.0, -0.135, 0.11), (0.042, 0.21, 0.075), bakelite_orange, (22, 0, 0)), # рожок AK
        ],
        metallic=0.45,
        roughness=0.50,
    )

    # 2. M4A1-S (с глушителем вдоль +Z)
    export_glb(
        MODELS_DIR / "m4a1.glb",
        boxes=[
            ((0.0, 0.0, 0.02), (0.054, 0.078, 0.30), polymer_black, (0, 0, 0)),    # ресивер
            ((0.0, 0.052, 0.02), (0.038, 0.028, 0.14), gunmetal, (0, 0, 0)),       # планка/коллиматор
            ((0.0, 0.008, 0.26), (0.056, 0.064, 0.22), gunmetal, (0, 0, 0)),       # тактическое цевьё
            ((0.0, 0.012, 0.44), (0.022, 0.022, 0.18), dark_steel, (0, 0, 0)),     # ствол
            ((0.0, 0.012, 0.63), (0.036, 0.036, 0.24), polymer_black, (0, 0, 0)),  # глушитель M4A1-S
            ((0.0, -0.015, -0.24), (0.046, 0.092, 0.22), polymer_black, (0, 0, 0)),# тактический приклад
            ((0.0, -0.095, -0.06), (0.036, 0.12, 0.05), polymer_black, (-16, 0, 0)),# пистолетная рукоять
            ((0.0, -0.125, 0.09), (0.040, 0.18, 0.068), gunmetal, (8, 0, 0)),      # магазин STANAG
        ],
        metallic=0.55,
        roughness=0.42,
    )

    # 3. Desert Eagle
    export_glb(
        MODELS_DIR / "deagle.glb",
        boxes=[
            ((0.0, 0.02, 0.08), (0.048, 0.065, 0.27), chrome, (0, 0, 0)),          # массивный затвор Deagle
            ((0.0, -0.015, 0.04), (0.044, 0.032, 0.22), dark_steel, (0, 0, 0)),    # рамка
            ((0.0, -0.095, -0.03), (0.040, 0.145, 0.062), polymer_black, (-15, 0, 0)), # рукоять
            ((0.0, -0.042, 0.04), (0.018, 0.032, 0.065), dark_steel, (0, 0, 0)),   # спусковая скоба
            ((0.0, 0.056, 0.20), (0.012, 0.016, 0.022), polymer_black, (0, 0, 0)), # мушка
        ],
        metallic=0.78,
        roughness=0.28,
    )

    # 4. Тактический нож
    export_glb(
        MODELS_DIR / "knife.glb",
        boxes=[
            ((0.0, -0.03, -0.06), (0.032, 0.042, 0.15), polymer_black, (10, 0, 0)), # рукоять
            ((0.0, -0.01, 0.02), (0.055, 0.075, 0.018), gunmetal, (10, 0, 0)),      # гарда
            ((0.0, 0.01, 0.15), (0.010, 0.046, 0.24), chrome, (6, 0, 0)),           # лезвие
            ((0.0, 0.026, 0.28), (0.008, 0.028, 0.08), chrome, (-12, 0, 0)),        # остриё клинка
        ],
        metallic=0.82,
        roughness=0.22,
    )

    # 5. Враг-бот (гуманоид высотой ~1.85м, ноги в y=0)
    sand_jacket = (0.68, 0.56, 0.38, 1.0)
    kevlar_vest = (0.18, 0.20, 0.22, 1.0)
    cargo_pants = (0.26, 0.30, 0.24, 1.0)
    balaclava = (0.14, 0.14, 0.16, 1.0)
    visor_red = (0.85, 0.20, 0.16, 1.0)

    export_glb(
        MODELS_DIR / "enemy.glb",
        boxes=[
            ((-0.14, 0.42, 0.0), (0.19, 0.84, 0.22), cargo_pants, (0, 0, 0)),      # левая нога
            ((0.14, 0.42, 0.0), (0.19, 0.84, 0.22), cargo_pants, (0, 0, 0)),       # правая нога
            ((-0.14, 0.06, 0.04), (0.20, 0.12, 0.28), polymer_black, (0, 0, 0)),   # левый ботинок
            ((0.14, 0.06, 0.04), (0.20, 0.12, 0.28), polymer_black, (0, 0, 0)),    # правый ботинок
            ((0.0, 1.16, 0.0), (0.50, 0.66, 0.30), sand_jacket, (0, 0, 0)),        # торс
            ((0.0, 1.18, 0.02), (0.44, 0.48, 0.33), kevlar_vest, (0, 0, 0)),       # бронежилет
            ((-0.33, 1.18, 0.12), (0.15, 0.54, 0.18), sand_jacket, (-35, 0, 0)),   # левая рука
            ((0.33, 1.18, 0.14), (0.15, 0.54, 0.18), sand_jacket, (-42, 0, 0)),    # правая рука
            ((0.12, 1.12, 0.42), (0.08, 0.12, 0.58), dark_steel, (0, -10, 0)),     # автомат в руках бота
            ((0.0, 1.68, 0.0), (0.32, 0.34, 0.32), balaclava, (0, 0, 0)),          # голова в балаклаве
            ((0.0, 1.71, 0.15), (0.26, 0.09, 0.06), visor_red, (0, 0, 0)),         # тактические очки
        ],
        metallic=0.15,
        roughness=0.78,
    )

    # 6. Деревянный тактический ящик 1x1x1 (центр в 0,0,0)
    crate_main = (0.64, 0.48, 0.28, 1.0)
    crate_trim = (0.45, 0.32, 0.17, 1.0)
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
        metallic=0.05,
        roughness=0.88,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ГЕНЕРАЦИЯ ТЕКСТУР (.PNG) В СТИЛЕ DE_DUST2 И HUD CS2
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def generate_textures() -> None:
    TEXTURES_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)

    # 1. Песчаник стен de_dust2 (wall_sandstone.png)
    w, h = 256, 256
    noise = rng.normal(0, 9, (h, w, 3))
    base = np.zeros((h, w, 3), dtype=np.float32)
    base[:, :] = [212, 186, 142]
    base += noise
    # Горизонтальные и вертикальные швы каменных блоков
    for row_idx, y in enumerate(range(0, h, 32)):
        base[max(0, y - 1):min(h, y + 2), :] *= 0.76
        x_shift = (row_idx % 2) * 32
        for x in range(x_shift, w, 64):
            base[y:min(h, y + 32), max(0, x - 1):min(w, x + 2)] *= 0.80
    img_wall = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    img_wall.save(TEXTURES_DIR / "wall_sandstone.png")

    # 2. Пыльная земля арены (floor_dust.png)
    noise_floor = rng.normal(0, 12, (h, w, 3))
    floor_arr = np.zeros((h, w, 3), dtype=np.float32)
    floor_arr[:, :] = [196, 170, 126]
    floor_arr += noise_floor
    img_floor = Image.fromarray(np.clip(floor_arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    img_floor.save(TEXTURES_DIR / "floor_dust.png")

    # 3. Деревянный ящик (crate_wood.png)
    crate_img = Image.new("RGB", (256, 256), (168, 124, 74))
    draw = ImageDraw.Draw(crate_img)
    for y in range(0, 256, 32):
        shade = int(rng.integers(-10, 10))
        draw.rectangle([0, y, 255, y + 30], fill=(168 + shade, 124 + shade, 74 + shade))
        draw.line([0, y, 255, y], fill=(112, 78, 42), width=2)
    draw.rectangle([0, 0, 255, 255], outline=(104, 72, 38), width=14)
    draw.line([10, 10, 245, 245], fill=(122, 86, 46), width=14)
    draw.line([245, 10, 10, 245], fill=(122, 86, 46), width=14)
    crate_img.save(TEXTURES_DIR / "crate_wood.png")

    # 4. Вспышка выстрела с альфа-каналом (muzzle_flash.png)
    mf_size = 128
    mf_img = Image.new("RGBA", (mf_size, mf_size), (0, 0, 0, 0))
    mf_draw = ImageDraw.Draw(mf_img)
    cx, cy = mf_size // 2, mf_size // 2
    for r in range(52, 4, -4):
        alpha = int(220 * (1 - r / 54) ** 1.7)
        col = (255, min(255, int(150 + (54 - r) * 2)), int(max(0, 80 - r * 1.5)), alpha)
        mf_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    mf_draw.polygon([(cx, 4), (cx + 10, cy), (cx, mf_size - 4), (cx - 10, cy)], fill=(255, 240, 160, 230))
    mf_draw.polygon([(4, cy), (cx, cy + 10), (mf_size - 4, cy), (cx, cy - 10)], fill=(255, 240, 160, 230))
    mf_img = mf_img.filter(ImageFilter.GaussianBlur(1.5))
    mf_img.save(TEXTURES_DIR / "muzzle_flash.png")

    # 5. Фон главного меню в стиле CS2 (menu_bg.png — тёмно-синий с оранжевым акцентом)
    bg_w, bg_h = 640, 360
    yy = np.linspace(0, 1, bg_h)[:, None]
    xx = np.linspace(0, 1, bg_w)[None, :]
    r_ch = np.clip(18 + 185 * (xx ** 2.2) * (1 - yy * 0.55), 0, 255)
    g_ch = np.clip(24 + 95 * (xx ** 2.0) * (1 - yy * 0.65), 0, 255)
    b_ch = np.clip(38 + 45 * (1 - xx) * (1 - yy * 0.4), 0, 255)
    bg_arr = np.dstack([
        np.broadcast_to(r_ch, (bg_h, bg_w)),
        np.broadcast_to(g_ch, (bg_h, bg_w)),
        np.broadcast_to(b_ch, (bg_h, bg_w)),
    ]).astype(np.uint8)
    bg_img = Image.fromarray(bg_arr)
    bg_draw = ImageDraw.Draw(bg_img)
    # Диагональные тактические полосы CS2
    for offset in range(-200, 800, 48):
        bg_draw.line([(offset, bg_h), (offset + 180, 0)], fill=(235, 145, 38), width=1)
    bg_img = bg_img.filter(ImageFilter.GaussianBlur(0.8))
    bg_img.save(TEXTURES_DIR / "menu_bg.png")

    # 6. Иконка здоровья HUD (icon_hp.png)
    hp_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    hp_d = ImageDraw.Draw(hp_img)
    hp_d.rounded_rectangle([22, 8, 42, 56], radius=4, fill=(240, 245, 250, 255))
    hp_d.rounded_rectangle([8, 22, 56, 42], radius=4, fill=(240, 245, 250, 255))
    hp_img.save(TEXTURES_DIR / "icon_hp.png")

    # 7. Иконка брони Kevlar HUD (icon_armor.png)
    ar_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ar_d = ImageDraw.Draw(ar_img)
    ar_d.polygon([(32, 6), (54, 16), (50, 40), (32, 58), (14, 40), (10, 16)], fill=(95, 175, 255, 255))
    ar_d.polygon([(32, 13), (47, 20), (44, 38), (32, 50), (20, 38), (17, 20)], fill=(45, 115, 205, 255))
    ar_img.save(TEXTURES_DIR / "icon_armor.png")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ГЕНЕРАЦИЯ ЗВУКОВ (.WAV) ВЫСТРЕЛОВ, ПЕРЕЗАРЯДКИ, ШАГОВ, МУЗЫКИ
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

    # AK-47: мощный хлесткий выстрел с низким басовым ударом
    t = np.linspace(0, 0.24, int(sr * 0.24), endpoint=False)
    ak = (
        rng.normal(0, 1.0, len(t)) * np.exp(-t * 24.0) * 0.75
        + np.sin(2 * np.pi * (155 * np.exp(-t * 14)) * t) * np.exp(-t * 18.0) * 0.85
    )
    _save_wav(SOUNDS_DIR / "ak47_shoot.wav", np.tanh(ak * 1.8), sr)

    # M4A1-S: приглушённый выстрел с глушителем (silenced pew-thump)
    t_m4 = np.linspace(0, 0.16, int(sr * 0.16), endpoint=False)
    m4 = (
        rng.normal(0, 0.65, len(t_m4)) * np.exp(-t_m4 * 42.0)
        + np.sin(2 * np.pi * (240 * np.exp(-t_m4 * 22)) * t_m4) * np.exp(-t_m4 * 32.0) * 0.7
    )
    _save_wav(SOUNDS_DIR / "m4a1_shoot.wav", m4 * 0.8, sr)

    # Desert Eagle: тяжёлый раскатистый пушечный выстрел
    t_de = np.linspace(0, 0.36, int(sr * 0.36), endpoint=False)
    de = (
        rng.normal(0, 1.1, len(t_de)) * np.exp(-t_de * 15.0) * 0.8
        + np.sin(2 * np.pi * (110 * np.exp(-t_de * 9)) * t_de) * np.exp(-t_de * 12.0) * 1.0
    )
    _save_wav(SOUNDS_DIR / "deagle_shoot.wav", np.tanh(de * 2.1), sr)

    # Knife slash: свист рассекаемого воздуха + металлический звон
    t_kn = np.linspace(0, 0.15, int(sr * 0.15), endpoint=False)
    kn = rng.normal(0, 0.5, len(t_kn)) * np.sin(np.pi * t_kn / 0.15) + 0.25 * np.sin(2 * np.pi * 1650 * t_kn) * np.exp(-t_kn * 35)
    _save_wav(SOUNDS_DIR / "knife_slash.wav", kn * 0.75, sr)

    # Перезарядка (двойной металлический щелчок магазина и затвора)
    t_rl = np.linspace(0, 0.55, int(sr * 0.55), endpoint=False)
    rl = np.zeros_like(t_rl)
    for click_t, freq in [(0.04, 880), (0.22, 1180), (0.40, 690)]:
        mask = t_rl >= click_t
        dt_c = t_rl[mask] - click_t
        rl[mask] += (np.sin(2 * np.pi * freq * dt_c) + rng.normal(0, 0.5, len(dt_c))) * np.exp(-dt_c * 55.0) * 0.6
    _save_wav(SOUNDS_DIR / "reload.wav", rl, sr)

    # Пустой магазин (сухой щелчок бойка)
    t_em = np.linspace(0, 0.06, int(sr * 0.06), endpoint=False)
    em = (np.sin(2 * np.pi * 1450 * t_em) + rng.normal(0, 0.4, len(t_em))) * np.exp(-t_em * 95.0) * 0.55
    _save_wav(SOUNDS_DIR / "empty_click.wav", em, sr)

    # Шаг по песку/камню
    t_fs = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
    fs = rng.normal(0, 0.5, len(t_fs)) * np.exp(-t_fs * 45.0) + 0.3 * np.sin(2 * np.pi * 95 * t_fs) * np.exp(-t_fs * 50.0)
    _save_wav(SOUNDS_DIR / "footstep.wav", fs * 0.55, sr)

    # Hitmarker (чёткий тик попадания CS)
    t_hm = np.linspace(0, 0.05, int(sr * 0.05), endpoint=False)
    hm = np.sin(2 * np.pi * 2100 * t_hm) * np.exp(-t_hm * 85.0) * 0.65
    _save_wav(SOUNDS_DIR / "hitmarker.wav", hm, sr)

    # Headshot dink (металлический звон шлема из CS2!)
    t_hs = np.linspace(0, 0.16, int(sr * 0.16), endpoint=False)
    hs = (np.sin(2 * np.pi * 2950 * t_hs) + 0.6 * np.sin(2 * np.pi * 4120 * t_hs)) * np.exp(-t_hs * 28.0) * 0.7
    _save_wav(SOUNDS_DIR / "headshot.wav", hs, sr)

    # Ранение игрока
    t_ph = np.linspace(0, 0.18, int(sr * 0.18), endpoint=False)
    ph = (np.sin(2 * np.pi * 130 * t_ph) + rng.normal(0, 0.4, len(t_ph))) * np.exp(-t_ph * 22.0) * 0.75
    _save_wav(SOUNDS_DIR / "player_hurt.wav", ph, sr)

    # Победа в раунде (короткий героический аккорд CT)
    t_win = np.linspace(0, 1.1, int(sr * 1.1), endpoint=False)
    win = (
        0.35 * np.sin(2 * np.pi * 261.63 * t_win)
        + 0.30 * np.sin(2 * np.pi * 329.63 * t_win)
        + 0.35 * np.sin(2 * np.pi * 392.00 * t_win)
    ) * np.exp(-t_win * 1.9)
    _save_wav(SOUNDS_DIR / "round_win.wav", win, sr)

    # Поражение в раунде (мрачный низкий интервал)
    t_lose = np.linspace(0, 1.1, int(sr * 1.1), endpoint=False)
    lose = (
        0.45 * np.sin(2 * np.pi * 146.83 * t_lose)
        + 0.40 * np.sin(2 * np.pi * 155.56 * t_lose)
    ) * np.exp(-t_lose * 1.8)
    _save_wav(SOUNDS_DIR / "round_lose.wav", lose, sr)

    # Фоновая тактическая эмбиент-тема меню (бесшовный цикл 4 секунды)
    dur = 4.0
    t_mu = np.linspace(0, dur, int(sr * dur), endpoint=False)
    pad = (
        0.22 * np.sin(2 * np.pi * 110.0 * t_mu)
        + 0.16 * np.sin(2 * np.pi * 164.81 * t_mu)
        + 0.12 * np.sin(2 * np.pi * 220.0 * t_mu) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t_mu))
    )
    pulse_env = (np.sin(2 * np.pi * 2.0 * t_mu) > 0.7).astype(np.float32)
    pulse = 0.08 * np.sin(2 * np.pi * 440.0 * t_mu) * pulse_env
    # Плавный фейд краёв для бесшовного лупа
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
    print("Starter assets successfully generated in:", ASSETS_DIR)
