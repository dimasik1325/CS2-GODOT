"""
Генератор высококачественных 3D-ассетов CS2 (Smooth-Shaded glTF 2.0 .glb, HD .png, .wav):
- Истинная цилиндрическая, коническая и сферическая 3D-геометрия со сглаженными нормалями!
- 17 моделей (.glb): AK-47, M4A1-S, AWP, P90, MP9, XM1014 Shotgun, FAMAS, USP-S, Desert Eagle,
  Glock-18, Zeus x27, Нож Керамбит, Спецназовец Игрока (CT Operator), Враг (T Soldier),
  Бочка с топливом, Взрывчатка C4, Армейский ящик.
- 14 текстур (.png): песчаник, кирпич, брусчатка, асфальт, металл, дерево, мешковина, навес базара и др.
- 32 звуковых эффекта (.wav): включая фанфару заставки (intro_fanfare), P90, электрошок Zeus x27 и рацию!
"""

from __future__ import annotations

import json
import math
import struct
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
MODELS_DIR = ROOT / "assets" / "models"
TEXTURES_DIR = ROOT / "assets" / "textures"
SOUNDS_DIR = ROOT / "assets" / "sounds"
FONTS_DIR = ROOT / "assets" / "fonts"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. ГЕНЕРАТОР ГЛАДКОЙ 3D-ГЕОМЕТРИИ В БИНАРНЫЙ GLTF 2.0 (.GLB)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class SmoothMeshBuilder:
    """Строит комбинированный 3D-меш из коробок, гладких цилиндров, конусов и сфер с вершинным цветом."""

    def __init__(self) -> None:
        self.positions: list[tuple[float, float, float]] = []
        self.normals: list[tuple[float, float, float]] = []
        self.colors: list[tuple[float, float, float, float]] = []
        self.indices: list[int] = []

    def add_box(
        self,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        rgba: tuple[float, float, float, float],
        rot_x_deg: float = 0.0,
        rot_y_deg: float = 0.0,
    ) -> None:
        cx, cy, cz = center
        hx, hy, hz = size[0] * 0.5, size[1] * 0.5, size[2] * 0.5
        rx = math.radians(rot_x_deg)
        ry = math.radians(rot_y_deg)
        cx_r, sx_r = math.cos(rx), math.sin(rx)
        cy_r, sy_r = math.cos(ry), math.sin(ry)

        def _rot(vx: float, vy: float, vz: float) -> tuple[float, float, float]:
            y1 = vy * cx_r - vz * sx_r
            z1 = vy * sx_r + vz * cx_r
            x2 = vx * cy_r + z1 * sy_r
            z2 = -vx * sy_r + z1 * cy_r
            return x2, y1, z2

        faces = [
            ((0.0, 0.0, 1.0), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
            ((0.0, 0.0, -1.0), [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)]),
            ((1.0, 0.0, 0.0), [(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)]),
            ((-1.0, 0.0, 0.0), [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)]),
            ((0.0, 1.0, 0.0), [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)]),
            ((0.0, -1.0, 0.0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
        ]

        for nrm, quad in faces:
            base_idx = len(self.positions)
            rn = _rot(*nrm)
            for vx, vy, vz in quad:
                rvx, rvy, rvz = _rot(vx, vy, vz)
                self.positions.append((cx + rvx, cy + rvy, cz + rvz))
                self.normals.append(rn)
                self.colors.append(rgba)
            self.indices.extend([base_idx, base_idx + 1, base_idx + 2, base_idx, base_idx + 2, base_idx + 3])

    def add_cylinder(
        self,
        center: tuple[float, float, float],
        radius_a: float,
        radius_b: float,
        length: float,
        rgba: tuple[float, float, float, float],
        axis: str = "z",
        segments: int = 14,
    ) -> None:
        """Добавляет гладкий цилиндр или усечённый конус вдоль оси X, Y или Z."""
        cx, cy, cz = center
        half = length * 0.5
        segs = max(6, segments)

        def _map_axis(u: float, v: float, w: float) -> tuple[float, float, float]:
            if axis == "y":
                return (u, w, v)
            if axis == "x":
                return (w, v, u)
            return (u, v, w)

        ring_start = len(self.positions)
        slope = (radius_a - radius_b) / max(1e-5, length)
        for i in range(segs + 1):
            ang = 2.0 * math.pi * i / segs
            ca, sa = math.cos(ang), math.sin(ang)
            nx_l, ny_l, nz_l = ca, sa, slope
            n_len = math.sqrt(nx_l * nx_l + ny_l * ny_l + nz_l * nz_l)
            nrm = _map_axis(nx_l / n_len, ny_l / n_len, nz_l / n_len)

            px0, py0, pz0 = _map_axis(ca * radius_a, sa * radius_a, -half)
            px1, py1, pz1 = _map_axis(ca * radius_b, sa * radius_b, half)

            self.positions.append((cx + px0, cy + py0, cz + pz0))
            self.normals.append(nrm)
            self.colors.append(rgba)

            self.positions.append((cx + px1, cy + py1, cz + pz1))
            self.normals.append(nrm)
            self.colors.append(rgba)

        for i in range(segs):
            i0 = ring_start + i * 2
            i1 = i0 + 1
            i2 = i0 + 2
            i3 = i0 + 3
            self.indices.extend([i0, i2, i3, i0, i3, i1])

        # Торцевые крышки
        for end_sign, rad in ((-1.0, radius_a), (1.0, radius_b)):
            if rad <= 1e-5:
                continue
            cap_center_idx = len(self.positions)
            c_off = _map_axis(0.0, 0.0, end_sign * half)
            c_nrm = _map_axis(0.0, 0.0, end_sign)
            self.positions.append((cx + c_off[0], cy + c_off[1], cz + c_off[2]))
            self.normals.append(c_nrm)
            self.colors.append(rgba)
            for i in range(segs + 1):
                ang = 2.0 * math.pi * i / segs
                rp = _map_axis(math.cos(ang) * rad, math.sin(ang) * rad, end_sign * half)
                self.positions.append((cx + rp[0], cy + rp[1], cz + rp[2]))
                self.normals.append(c_nrm)
                self.colors.append(rgba)
            for i in range(segs):
                v1 = cap_center_idx + 1 + i
                v2 = cap_center_idx + 2 + i
                if end_sign > 0:
                    self.indices.extend([cap_center_idx, v1, v2])
                else:
                    self.indices.extend([cap_center_idx, v2, v1])

    def add_sphere(
        self,
        center: tuple[float, float, float],
        scale_xyz: tuple[float, float, float],
        rgba: tuple[float, float, float, float],
        rings: int = 8,
        sectors: int = 12,
    ) -> None:
        """Добавляет гладкий эллипсоид / сферу (для шлемов, голов и суставов)."""
        cx, cy, cz = center
        rx, ry, rz = scale_xyz
        base = len(self.positions)
        for r in range(rings + 1):
            v = r / rings
            phi = v * math.pi
            sp, cp = math.sin(phi), math.cos(phi)
            for s in range(sectors + 1):
                u = s / sectors
                theta = u * 2.0 * math.pi
                st, ct = math.sin(theta), math.cos(theta)
                nx, ny, nz = ct * sp, cp, st * sp
                self.positions.append((cx + nx * rx, cy + ny * ry, cz + nz * rz))
                self.normals.append((nx, ny, nz))
                self.colors.append(rgba)

        stride = sectors + 1
        for r in range(rings):
            for s in range(sectors):
                i0 = base + r * stride + s
                i1 = i0 + 1
                i2 = i0 + stride
                i3 = i2 + 1
                self.indices.extend([i0, i2, i1, i1, i2, i3])


def export_mesh_to_glb(
    path: Path,
    builder: SmoothMeshBuilder,
    metallic: float = 0.45,
    roughness: float = 0.48,
) -> None:
    pos_arr = np.asarray(builder.positions, dtype=np.float32)
    nrm_arr = np.asarray(builder.normals, dtype=np.float32)
    col_arr = np.asarray(builder.colors, dtype=np.float32)
    idx_arr = np.asarray(builder.indices, dtype=np.uint32)

    pos_bytes = pos_arr.tobytes()
    nrm_bytes = nrm_arr.tobytes()
    col_bytes = col_arr.tobytes()
    idx_bytes = idx_arr.tobytes()

    def _pad4(b: bytes) -> bytes:
        rem = len(b) % 4
        return b if rem == 0 else b + b"\x00" * (4 - rem)

    pos_bytes_p = _pad4(pos_bytes)
    nrm_bytes_p = _pad4(nrm_bytes)
    col_bytes_p = _pad4(col_bytes)
    idx_bytes_p = _pad4(idx_bytes)

    off_pos = 0
    off_nrm = off_pos + len(pos_bytes_p)
    off_col = off_nrm + len(nrm_bytes_p)
    off_idx = off_col + len(col_bytes_p)
    bin_blob = pos_bytes_p + nrm_bytes_p + col_bytes_p + idx_bytes_p

    min_pos = pos_arr.min(axis=0).tolist()
    max_pos = pos_arr.max(axis=0).tolist()

    gltf_dict = {
        "asset": {"version": "2.0", "generator": "CS2-AlkoDimas-SmoothGLB-2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": path.stem}],
        "materials": [
            {
                "name": f"{path.stem}_mat",
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
                "name": path.stem,
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
            {"buffer": 0, "byteOffset": off_pos, "byteLength": len(pos_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": off_nrm, "byteLength": len(nrm_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": off_col, "byteLength": len(col_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": off_idx, "byteLength": len(idx_bytes), "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(pos_arr),
                "type": "VEC3",
                "min": min_pos,
                "max": max_pos,
            },
            {"bufferView": 1, "componentType": 5126, "count": len(nrm_arr), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": len(col_arr), "type": "VEC4"},
            {"bufferView": 3, "componentType": 5125, "count": len(idx_arr), "type": "SCALAR"},
        ],
    }

    json_bytes = json.dumps(gltf_dict, separators=(",", ":")).encode("utf-8")
    if len(json_bytes) % 4 != 0:
        json_bytes += b" " * (4 - (len(json_bytes) % 4))

    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
    header = struct.pack("<III", 0x46546C67, 2, total_length)
    json_chunk = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
    bin_chunk = struct.pack("<II", len(bin_blob), 0x004E4942) + bin_blob

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + json_chunk + bin_chunk)


def generate_all_models() -> None:
    gunmetal = (0.17, 0.19, 0.22, 1.0)
    dark_steel = (0.10, 0.11, 0.13, 1.0)
    chrome = (0.74, 0.78, 0.83, 1.0)
    wood_rich = (0.50, 0.27, 0.12, 1.0)
    wood_dark = (0.37, 0.19, 0.08, 1.0)
    olive_awp = (0.24, 0.33, 0.20, 1.0)
    polymer_tan = (0.58, 0.50, 0.37, 1.0)
    ruby_blade = (0.86, 0.12, 0.18, 1.0)
    zeus_yellow = (0.94, 0.76, 0.14, 1.0)

    # 1. AK-47 (круглый ствол, газовая трубка, ДТК, изогнутый рожок, дерево)
    ak = SmoothMeshBuilder()
    ak.add_box((0.0, 0.0, 0.02), (0.048, 0.068, 0.32), gunmetal)
    ak.add_cylinder((0.0, 0.036, 0.02), 0.024, 0.024, 0.31, dark_steel, axis="z", segments=12)
    ak.add_cylinder((0.0, 0.014, -0.34), 0.011, 0.011, 0.42, dark_steel, axis="z", segments=14)
    ak.add_cylinder((0.0, 0.038, -0.25), 0.009, 0.009, 0.22, gunmetal, axis="z", segments=12)
    ak.add_cylinder((0.0, 0.014, -0.56), 0.015, 0.012, 0.045, dark_steel, axis="z", segments=12)
    ak.add_box((0.0, 0.048, -0.51), (0.008, 0.038, 0.018), dark_steel)
    ak.add_box((0.0, 0.012, -0.22), (0.052, 0.056, 0.18), wood_rich)
    ak.add_box((0.0, -0.022, 0.28), (0.044, 0.082, 0.23), wood_dark, rot_x_deg=6.0)
    ak.add_box((0.0, -0.095, 0.10), (0.036, 0.12, 0.048), wood_dark, rot_x_deg=-18.0)
    ak.add_box((0.0, -0.115, -0.08), (0.038, 0.17, 0.062), (0.64, 0.30, 0.10, 1.0), rot_x_deg=18.0)
    ak.add_box((0.0, -0.21, -0.12), (0.036, 0.09, 0.058), (0.58, 0.26, 0.08, 1.0), rot_x_deg=30.0)
    export_mesh_to_glb(MODELS_DIR / "ak47.glb", ak, metallic=0.58, roughness=0.40)

    # 2. M4A1-S (круглый глушитель, цевьё с планкой Пикатинни, телескопический приклад)
    m4 = SmoothMeshBuilder()
    m4.add_box((0.0, 0.0, 0.03), (0.048, 0.072, 0.29), gunmetal)
    m4.add_box((0.0, 0.045, -0.04), (0.028, 0.014, 0.36), dark_steel)
    m4.add_cylinder((0.0, 0.014, -0.19), 0.026, 0.026, 0.22, dark_steel, axis="z", segments=14)
    m4.add_cylinder((0.0, 0.014, -0.35), 0.011, 0.011, 0.14, gunmetal, axis="z", segments=12)
    m4.add_cylinder((0.0, 0.014, -0.53), 0.021, 0.021, 0.25, (0.12, 0.14, 0.17, 1.0), axis="z", segments=16)
    m4.add_cylinder((0.0, 0.008, 0.27), 0.017, 0.017, 0.22, gunmetal, axis="z", segments=12)
    m4.add_box((0.0, -0.025, 0.34), (0.042, 0.10, 0.09), dark_steel)
    m4.add_box((0.0, -0.095, 0.10), (0.036, 0.12, 0.046), dark_steel, rot_x_deg=-15.0)
    m4.add_box((0.0, -0.12, -0.06), (0.036, 0.16, 0.058), (0.22, 0.24, 0.28, 1.0), rot_x_deg=8.0)
    export_mesh_to_glb(MODELS_DIR / "m4a1.glb", m4, metallic=0.66, roughness=0.34)

    # 3. AWP (круглая оптика с линзами, длинный рифлёный ствол, ДТК, оливковое ложе)
    awp = SmoothMeshBuilder()
    awp.add_box((0.0, -0.005, 0.06), (0.054, 0.076, 0.48), olive_awp)
    awp.add_box((0.0, -0.022, 0.38), (0.050, 0.105, 0.24), olive_awp)
    awp.add_box((0.0, 0.034, 0.02), (0.044, 0.042, 0.28), dark_steel)
    awp.add_cylinder((0.0, 0.026, -0.42), 0.014, 0.012, 0.56, dark_steel, axis="z", segments=16)
    awp.add_box((0.0, 0.026, -0.71), (0.034, 0.028, 0.055), gunmetal)
    # Гладкий оптический прицел + объектив и окуляр
    awp.add_cylinder((0.0, 0.094, 0.01), 0.019, 0.019, 0.28, dark_steel, axis="z", segments=16)
    awp.add_cylinder((0.0, 0.094, -0.14), 0.024, 0.029, 0.07, gunmetal, axis="z", segments=16)
    awp.add_cylinder((0.0, 0.094, 0.15), 0.023, 0.021, 0.05, gunmetal, axis="z", segments=16)
    awp.add_cylinder((0.0, 0.094, -0.176), 0.025, 0.025, 0.006, (0.14, 0.55, 0.78, 1.0), axis="z", segments=14)
    awp.add_box((0.0, 0.062, -0.06), (0.022, 0.032, 0.024), gunmetal)
    awp.add_box((0.0, 0.062, 0.08), (0.022, 0.032, 0.024), gunmetal)
    awp.add_cylinder((0.035, 0.035, 0.06), 0.008, 0.008, 0.05, chrome, axis="x", segments=10)
    awp.add_box((0.0, -0.088, 0.00), (0.038, 0.095, 0.085), dark_steel)
    export_mesh_to_glb(MODELS_DIR / "awp.glb", awp, metallic=0.52, roughness=0.38)

    # 4. P90 (легендарный булл-пап CS2 с полупрозрачным верхним магазином на 50 патронов!)
    p90 = SmoothMeshBuilder()
    p90.add_box((0.0, -0.01, 0.04), (0.054, 0.105, 0.38), (0.20, 0.22, 0.26, 1.0))
    p90.add_box((0.0, -0.03, 0.24), (0.052, 0.125, 0.14), dark_steel)
    # Полупрозрачный янтарный магазин сверху с латунными патронами внутри
    p90.add_box((0.0, 0.052, 0.05), (0.046, 0.024, 0.28), (0.72, 0.52, 0.20, 1.0))
    p90.add_box((0.0, 0.075, -0.06), (0.032, 0.036, 0.09), gunmetal)
    p90.add_cylinder((0.0, 0.015, -0.19), 0.011, 0.011, 0.10, dark_steel, axis="z", segments=12)
    p90.add_box((0.0, -0.075, -0.08), (0.036, 0.075, 0.05), dark_steel, rot_x_deg=12.0)
    p90.add_box((0.0, -0.082, 0.05), (0.036, 0.082, 0.05), dark_steel, rot_x_deg=-10.0)
    export_mesh_to_glb(MODELS_DIR / "p90.glb", p90, metallic=0.50, roughness=0.42)

    # 5. MP9 (компактный ПП спецназа с круглой передней рукояткой)
    mp9 = SmoothMeshBuilder()
    mp9.add_box((0.0, 0.01, 0.0), (0.046, 0.068, 0.26), polymer_tan)
    mp9.add_box((0.0, 0.052, 0.01), (0.028, 0.024, 0.075), dark_steel)
    mp9.add_cylinder((0.0, 0.014, -0.19), 0.016, 0.016, 0.14, dark_steel, axis="z", segments=14)
    mp9.add_box((0.0, -0.105, 0.03), (0.034, 0.17, 0.040), dark_steel, rot_x_deg=-8.0)
    mp9.add_cylinder((0.0, -0.068, -0.09), 0.013, 0.013, 0.09, dark_steel, axis="y", segments=10)
    mp9.add_cylinder((0.0, 0.015, 0.21), 0.008, 0.008, 0.18, gunmetal, axis="z", segments=10)
    export_mesh_to_glb(MODELS_DIR / "mp9.glb", mp9, metallic=0.46, roughness=0.44)

    # 6. XM1014 Shotgun (двойные гладкие трубы ствола и подствольного магазина!)
    sg = SmoothMeshBuilder()
    sg.add_box((0.0, 0.005, 0.04), (0.050, 0.074, 0.28), gunmetal)
    sg.add_cylinder((0.0, 0.026, -0.32), 0.014, 0.014, 0.46, chrome, axis="z", segments=14)
    sg.add_cylinder((0.0, -0.006, -0.29), 0.013, 0.013, 0.40, dark_steel, axis="z", segments=14)
    sg.add_cylinder((0.0, -0.006, -0.20), 0.022, 0.022, 0.19, (0.20, 0.22, 0.25, 1.0), axis="z", segments=12)
    sg.add_box((0.0, -0.028, 0.28), (0.044, 0.088, 0.24), dark_steel, rot_x_deg=7.0)
    sg.add_box((0.0, -0.092, 0.10), (0.036, 0.11, 0.048), dark_steel, rot_x_deg=-16.0)
    export_mesh_to_glb(MODELS_DIR / "shotgun.glb", sg, metallic=0.68, roughness=0.32)

    # 7. FAMAS (ручка переноски и магазин позади рукояти)
    fam = SmoothMeshBuilder()
    fam.add_box((0.0, 0.0, 0.05), (0.050, 0.078, 0.42), gunmetal)
    fam.add_box((0.0, 0.072, 0.00), (0.032, 0.022, 0.30), dark_steel)
    fam.add_box((0.0, 0.046, -0.12), (0.030, 0.035, 0.035), dark_steel)
    fam.add_box((0.0, 0.046, 0.12), (0.030, 0.035, 0.035), dark_steel)
    fam.add_cylinder((0.0, 0.010, -0.26), 0.011, 0.011, 0.22, dark_steel, axis="z", segments=12)
    fam.add_box((0.0, -0.095, -0.02), (0.036, 0.12, 0.046), dark_steel, rot_x_deg=-14.0)
    fam.add_box((0.0, -0.120, 0.18), (0.036, 0.16, 0.056), (0.26, 0.28, 0.32, 1.0), rot_x_deg=6.0)
    export_mesh_to_glb(MODELS_DIR / "famas.glb", fam, metallic=0.55, roughness=0.40)

    # 8. USP-S (тактический пистолет спецназа с круглым глушителем)
    usp = SmoothMeshBuilder()
    usp.add_box((0.0, 0.024, -0.02), (0.036, 0.042, 0.19), gunmetal)
    usp.add_box((0.0, -0.008, 0.0), (0.034, 0.026, 0.17), dark_steel)
    usp.add_cylinder((0.0, 0.024, -0.21), 0.017, 0.017, 0.20, (0.12, 0.14, 0.17, 1.0), axis="z", segments=16)
    usp.add_box((0.0, -0.078, 0.048), (0.032, 0.12, 0.048), dark_steel, rot_x_deg=-14.0)
    export_mesh_to_glb(MODELS_DIR / "usp.glb", usp, metallic=0.64, roughness=0.34)

    # 9. Desert Eagle (.50 AE хром)
    de = SmoothMeshBuilder()
    de.add_box((0.0, 0.025, -0.04), (0.042, 0.052, 0.25), chrome)
    de.add_cylinder((0.0, 0.026, -0.06), 0.012, 0.012, 0.23, dark_steel, axis="z", segments=12)
    de.add_box((0.0, -0.01, 0.01), (0.038, 0.028, 0.19), gunmetal)
    de.add_box((0.0, -0.085, 0.055), (0.036, 0.13, 0.054), (0.14, 0.14, 0.16, 1.0), rot_x_deg=-14.0)
    export_mesh_to_glb(MODELS_DIR / "deagle.glb", de, metallic=0.86, roughness=0.22)

    # 10. Glock-18
    gl = SmoothMeshBuilder()
    gl.add_box((0.0, 0.022, -0.02), (0.034, 0.038, 0.185), dark_steel)
    gl.add_cylinder((0.0, 0.022, -0.115), 0.008, 0.008, 0.03, gunmetal, axis="z", segments=10)
    gl.add_box((0.0, -0.008, 0.0), (0.033, 0.024, 0.17), (0.22, 0.24, 0.20, 1.0))
    gl.add_box((0.0, -0.076, 0.044), (0.031, 0.12, 0.046), (0.18, 0.20, 0.17, 1.0), rot_x_deg=-16.0)
    export_mesh_to_glb(MODELS_DIR / "glock.glb", gl, metallic=0.45, roughness=0.48)

    # 11. Zeus x27 (электрошокер CS2 жёлто-чёрный с двумя электродами!)
    zeus = SmoothMeshBuilder()
    zeus.add_box((0.0, 0.02, -0.02), (0.048, 0.058, 0.19), dark_steel)
    zeus.add_box((0.0, 0.022, -0.06), (0.050, 0.042, 0.10), zeus_yellow)
    zeus.add_cylinder((-0.012, 0.025, -0.125), 0.005, 0.003, 0.028, (0.35, 0.85, 1.0, 1.0), axis="z", segments=10)
    zeus.add_cylinder((0.012, 0.025, -0.125), 0.005, 0.003, 0.028, (0.35, 0.85, 1.0, 1.0), axis="z", segments=10)
    zeus.add_box((0.0, -0.072, 0.045), (0.036, 0.115, 0.048), dark_steel, rot_x_deg=-16.0)
    export_mesh_to_glb(MODELS_DIR / "zeus.glb", zeus, metallic=0.52, roughness=0.38)

    # 12. Нож Керамбит Ruby Doppler (с кольцом на пальце и изогнутым лезвием)
    kn = SmoothMeshBuilder()
    kn.add_cylinder((0.0, -0.028, 0.11), 0.022, 0.022, 0.012, ruby_blade, axis="x", segments=14)
    kn.add_box((0.0, -0.005, 0.045), (0.018, 0.032, 0.11), dark_steel, rot_x_deg=12.0)
    kn.add_box((0.0, 0.012, -0.045), (0.006, 0.030, 0.09), ruby_blade, rot_x_deg=-18.0)
    kn.add_box((0.0, -0.014, -0.115), (0.005, 0.024, 0.08), (0.96, 0.22, 0.28, 1.0), rot_x_deg=-42.0)
    export_mesh_to_glb(MODELS_DIR / "knife.glb", kn, metallic=0.88, roughness=0.18)

    # 13. Детализированная 3D-модель Врага (T Soldier со сферическим шлемом, визором, жилетом и круглыми конечностями)
    en = SmoothMeshBuilder()
    pants = (0.20, 0.22, 0.27, 1.0)
    jacket = (0.58, 0.44, 0.28, 1.0)
    vest = (0.20, 0.22, 0.19, 1.0)
    pouch = (0.30, 0.28, 0.22, 1.0)
    skin = (0.76, 0.58, 0.46, 1.0)
    helmet = (0.24, 0.24, 0.26, 1.0)
    visor = (0.88, 0.22, 0.16, 1.0)

    # Ботинки, голени и бёдра (гладкие цилиндры + наколенники)
    for sx in (-0.13, 0.13):
        en.add_box((sx, 0.07, -0.04), (0.14, 0.14, 0.26), (0.10, 0.10, 0.12, 1.0))
        en.add_cylinder((sx, 0.36, 0.0), 0.075, 0.085, 0.46, pants, axis="y", segments=12)
        en.add_sphere((sx, 0.48, -0.07), (0.065, 0.065, 0.04), dark_steel, rings=6, sectors=10)
        en.add_cylinder((sx, 0.72, 0.0), 0.088, 0.095, 0.38, pants, axis="y", segments=12)
    # Пояс, торс и бронежилет с подсумками
    en.add_box((0.0, 0.88, 0.0), (0.42, 0.10, 0.26), dark_steel)
    en.add_box((0.0, 1.18, 0.0), (0.44, 0.54, 0.25), jacket)
    en.add_box((0.0, 1.19, 0.0), (0.47, 0.42, 0.29), vest)
    for px in (-0.13, 0.0, 0.13):
        en.add_box((px, 1.10, -0.155), (0.085, 0.14, 0.05), pouch)
    # Плечи, руки и винтовка в руках
    for sx in (-0.30, 0.30):
        en.add_sphere((sx, 1.38, 0.0), (0.09, 0.09, 0.09), jacket, rings=7, sectors=10)
    en.add_cylinder((-0.31, 1.16, -0.08), 0.065, 0.058, 0.42, jacket, axis="y", segments=10)
    en.add_cylinder((0.30, 1.18, -0.14), 0.065, 0.058, 0.42, jacket, axis="y", segments=10)
    en.add_box((0.12, 1.12, -0.34), (0.06, 0.09, 0.52), dark_steel)
    en.add_cylinder((0.12, 1.14, -0.66), 0.016, 0.016, 0.26, gunmetal, axis="z", segments=10)
    # Шея, сферическая голова, балаклава, каска и тактические очки
    en.add_cylinder((0.0, 1.48, 0.0), 0.075, 0.08, 0.10, skin, axis="y", segments=10)
    en.add_sphere((0.0, 1.63, 0.0), (0.135, 0.15, 0.14), (0.18, 0.18, 0.20, 1.0), rings=10, sectors=14)
    en.add_sphere((0.0, 1.69, 0.01), (0.152, 0.12, 0.158), helmet, rings=9, sectors=14)
    en.add_box((0.0, 1.64, -0.135), (0.21, 0.065, 0.04), visor)
    export_mesh_to_glb(MODELS_DIR / "enemy.glb", en, metallic=0.22, roughness=0.72)

    # 14. Детализированная 3D-модель Игрока — Спецназовец CT SAS Operator (для вида от 3-го лица F5 и Меню!)
    ct = SmoothMeshBuilder()
    ct_navy = (0.14, 0.22, 0.34, 1.0)
    ct_vest = (0.12, 0.15, 0.20, 1.0)
    ct_helmet = (0.16, 0.24, 0.34, 1.0)
    ct_visor = (0.20, 0.68, 0.96, 1.0)

    for sx in (-0.13, 0.13):
        ct.add_box((sx, 0.07, -0.04), (0.14, 0.14, 0.26), (0.09, 0.10, 0.12, 1.0))
        ct.add_cylinder((sx, 0.36, 0.0), 0.078, 0.088, 0.46, ct_navy, axis="y", segments=12)
        ct.add_sphere((sx, 0.48, -0.075), (0.068, 0.068, 0.042), ct_vest, rings=6, sectors=10)
        ct.add_cylinder((sx, 0.72, 0.0), 0.090, 0.098, 0.38, ct_navy, axis="y", segments=12)
    ct.add_box((0.0, 0.88, 0.0), (0.43, 0.10, 0.27), ct_vest)
    ct.add_box((0.0, 1.18, 0.0), (0.45, 0.54, 0.26), ct_navy)
    ct.add_box((0.0, 1.19, 0.0), (0.48, 0.43, 0.30), ct_vest)
    ct.add_box((0.0, 1.20, 0.18), (0.32, 0.36, 0.12), (0.16, 0.20, 0.26, 1.0))  # Тактический рюкзак спецназа
    for px in (-0.13, 0.0, 0.13):
        ct.add_box((px, 1.10, -0.16), (0.085, 0.14, 0.05), (0.22, 0.28, 0.36, 1.0))
    for sx in (-0.30, 0.30):
        ct.add_sphere((sx, 1.38, 0.0), (0.095, 0.095, 0.095), ct_navy, rings=7, sectors=10)
        ct.add_cylinder((sx, 1.17, -0.10), 0.066, 0.058, 0.42, ct_navy, axis="y", segments=10)
    ct.add_sphere((0.0, 1.63, 0.0), (0.138, 0.15, 0.142), (0.12, 0.14, 0.18, 1.0), rings=10, sectors=14)
    ct.add_sphere((0.0, 1.70, 0.01), (0.158, 0.125, 0.162), ct_helmet, rings=10, sectors=14)
    ct.add_box((0.0, 1.65, -0.14), (0.22, 0.070, 0.042), ct_visor)
    # Крепление ПНВ на шлеме CT
    ct.add_box((0.0, 1.75, -0.14), (0.07, 0.06, 0.05), dark_steel)
    export_mesh_to_glb(MODELS_DIR / "player_operator.glb", ct, metallic=0.28, roughness=0.65)

    # 15. Гладкая круглая взрывоопасная бочка (barrel.glb)
    bar = SmoothMeshBuilder()
    bar.add_cylinder((0.0, 0.55, 0.0), 0.34, 0.34, 1.10, (0.80, 0.15, 0.13, 1.0), axis="y", segments=18)
    for ry_h in (0.06, 0.38, 0.72, 1.04):
        bar.add_cylinder((0.0, ry_h, 0.0), 0.358, 0.358, 0.045, (0.94, 0.76, 0.16, 1.0), axis="y", segments=18)
    bar.add_cylinder((0.12, 1.12, 0.0), 0.045, 0.045, 0.04, chrome, axis="y", segments=10)
    export_mesh_to_glb(MODELS_DIR / "barrel.glb", bar, metallic=0.58, roughness=0.38)

    # 16. Заряд взрывчатки C4
    c4 = SmoothMeshBuilder()
    c4.add_box((-0.07, 0.045, 0.0), (0.12, 0.09, 0.24), (0.64, 0.56, 0.40, 1.0))
    c4.add_box((0.07, 0.045, 0.0), (0.12, 0.09, 0.24), (0.62, 0.54, 0.38, 1.0))
    c4.add_box((0.0, 0.105, -0.02), (0.16, 0.04, 0.13), (0.15, 0.20, 0.16, 1.0))
    c4.add_box((0.0, 0.128, -0.04), (0.11, 0.008, 0.05), (0.88, 0.14, 0.12, 1.0))
    c4.add_box((0.0, 0.05, 0.0), (0.27, 0.095, 0.04), (0.16, 0.16, 0.18, 1.0))
    export_mesh_to_glb(MODELS_DIR / "c4.glb", c4, metallic=0.32, roughness=0.60)

    # 17. Армейский ящик с усиливающими рёбрами (crate.glb)
    cr = SmoothMeshBuilder()
    cr.add_box((0.0, 0.5, 0.0), (0.94, 0.94, 0.94), (0.58, 0.43, 0.25, 1.0))
    frame_c = (0.39, 0.28, 0.16, 1.0)
    for y_pos in (0.06, 0.94):
        cr.add_box((0.0, y_pos, 0.47), (1.0, 0.12, 0.06), frame_c)
        cr.add_box((0.0, y_pos, -0.47), (1.0, 0.12, 0.06), frame_c)
        cr.add_box((0.47, y_pos, 0.0), (0.06, 0.12, 1.0), frame_c)
        cr.add_box((-0.47, y_pos, 0.0), (0.06, 0.12, 1.0), frame_c)
    for sx in (-0.47, 0.47):
        for sz in (-0.47, 0.47):
            cr.add_box((sx, 0.5, sz), (0.08, 1.0, 0.08), frame_c)
    export_mesh_to_glb(MODELS_DIR / "crate.glb", cr, metallic=0.14, roughness=0.82)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. ГЕНЕРАТОР HD-ТЕКСТУР (.PNG) С МИКРОРЕЛЬЕФОМ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def generate_all_textures() -> None:
    TEXTURES_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)

    # 1. Песчаник со швами и барельефом (wall_sandstone.png)
    w, h = 512, 512
    sand = rng.normal(loc=202.0, scale=11.0, size=(h, w, 3))
    sand[:, :, 0] += 18
    sand[:, :, 1] += 4
    sand[:, :, 2] -= 24
    for row_idx, y in enumerate(range(0, h, 64)):
        sand[y : y + 3, :, :] *= 0.60
        sand[min(h - 1, y + 3) : min(h, y + 5), :, :] *= 1.12
        offset = 64 if (row_idx % 2) else 0
        for x in range(offset, w, 128):
            sand[y : min(h, y + 64), x : min(w, x + 3), :] *= 0.64
    Image.fromarray(np.clip(sand, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "wall_sandstone.png")

    # 2. Обожжённый кирпич (wall_brick.png)
    br = rng.normal(loc=152.0, scale=13.0, size=(h, w, 3))
    br[:, :, 0] += 36
    br[:, :, 1] -= 16
    br[:, :, 2] -= 34
    for r_i, y in enumerate(range(0, h, 32)):
        br[y : y + 3, :, :] = 178
        off = 32 if (r_i % 2) else 0
        for x in range(off, w, 64):
            br[y : min(h, y + 32), x : min(w, x + 3), :] = 174
    Image.fromarray(np.clip(br, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "wall_brick.png")

    # 3. Каменная брусчатка площади (cobblestone.png)
    cob = rng.normal(loc=168.0, scale=12.0, size=(h, w, 3))
    cob[:, :, 0] += 8
    cob[:, :, 2] -= 8
    for r_i, y in enumerate(range(0, h, 48)):
        cob[y : y + 3, :, :] *= 0.56
        off = 28 if (r_i % 2) else 0
        for x in range(off, w, 56):
            cob[y : min(h, y + 48), x : min(w, x + 3), :] *= 0.58
    Image.fromarray(np.clip(cob, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "cobblestone.png")

    # 4. Полосатая восточная ткань навеса базара (fabric_awning.png)
    awn = np.zeros((256, 256, 3), dtype=np.float32)
    for x in range(256):
        stripe = (x // 32) % 2
        if stripe == 0:
            awn[:, x] = [188, 52, 42]
        else:
            awn[:, x] = [238, 224, 196]
    awn += rng.normal(0.0, 6.0, size=awn.shape)
    Image.fromarray(np.clip(awn, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "fabric_awning.png")

    # 5. Пыльная плитка пола (floor_dust.png)
    flr = rng.normal(loc=186.0, scale=12.0, size=(h, w, 3))
    flr[:, :, 0] += 16
    flr[:, :, 1] += 5
    flr[:, :, 2] -= 22
    for i in range(0, w, 64):
        flr[i : i + 2, :, :] *= 0.78
        flr[:, i : i + 2, :] *= 0.78
    Image.fromarray(np.clip(flr, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "floor_dust.png")

    # 6. Асфальт с жёлтой разметкой (asphalt_road.png)
    asp = rng.normal(loc=66.0, scale=9.0, size=(h, w, 3))
    asp[:, :, 2] += 4
    for y in range(24, h, 96):
        asp[y : min(h, y + 48), 248:264, 0] = 228
        asp[y : min(h, y + 48), 248:264, 1] = 182
        asp[y : min(h, y + 48), 248:264, 2] = 44
    Image.fromarray(np.clip(asp, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "asphalt_road.png")

    # 7. Рифлёный металл (metal_plate.png)
    met = rng.normal(loc=112.0, scale=7.0, size=(256, 256, 3))
    met[:, :, 2] += 8
    for y in range(0, 256, 16):
        for x in range(0, 256, 16):
            met[y + 4 : y + 10, x + 6 : x + 9, :] += 26
    Image.fromarray(np.clip(met, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "metal_plate.png")

    # 8. Синий гофро-контейнер (container_blue.png)
    cnt = rng.normal(loc=70.0, scale=6.0, size=(256, 256, 3))
    cnt[:, :, 0] = np.clip(cnt[:, :, 0] - 28, 20, 255)
    cnt[:, :, 1] = np.clip(cnt[:, :, 1] + 18, 20, 255)
    cnt[:, :, 2] = np.clip(cnt[:, :, 2] + 78, 30, 255)
    for x in range(0, 256, 16):
        cnt[:, x : x + 4, :] *= 0.72
        cnt[:, x + 4 : x + 8, :] *= 1.18
    Image.fromarray(np.clip(cnt, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "container_blue.png")

    # 9. Мешковина (sandbag_fabric.png)
    sb = rng.normal(loc=168.0, scale=14.0, size=(256, 256, 3))
    sb[:, :, 0] += 14
    sb[:, :, 2] -= 28
    sb[::4, :, :] *= 0.88
    sb[:, ::4, :] *= 0.90
    Image.fromarray(np.clip(sb, 0, 255).astype(np.uint8)).save(TEXTURES_DIR / "sandbag_fabric.png")

    # 10. Взрывоопасная бочка (barrel_hazard.png)
    bh = np.zeros((256, 256, 3), dtype=np.uint8)
    bh[:, :] = (196, 38, 34)
    bh[96:160, :] = (238, 192, 34)
    Image.fromarray(bh).save(TEXTURES_DIR / "barrel_hazard.png")

    # 11. Деревянные доски ящика (crate_wood.png)
    wood = rng.normal(loc=148.0, scale=9.0, size=(256, 256, 3))
    wood[:, :, 0] += 26
    wood[:, :, 2] -= 38
    for y in range(0, 256, 32):
        wood[y : y + 3, :, :] *= 0.52
    wood_img = Image.fromarray(np.clip(wood, 0, 255).astype(np.uint8))
    d_w = ImageDraw.Draw(wood_img)
    d_w.rectangle([4, 4, 251, 251], outline=(86, 56, 28), width=10)
    d_w.line([8, 8, 247, 247], fill=(96, 64, 32), width=10)
    wood_img.save(TEXTURES_DIR / "crate_wood.png")

    # 12. Вспышка выстрела (muzzle_flash.png)
    mf = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    dmf = ImageDraw.Draw(mf)
    cx, cy = 128, 128
    for angle_deg in range(0, 360, 30):
        rad = math.radians(angle_deg)
        r_len = 118 if angle_deg % 60 == 0 else 72
        x2 = cx + math.cos(rad) * r_len
        y2 = cy + math.sin(rad) * r_len
        dmf.polygon(
            [(cx - math.sin(rad) * 14, cy + math.cos(rad) * 14), (x2, y2), (cx + math.sin(rad) * 14, cy - math.cos(rad) * 14)],
            fill=(255, 195, 55, 225),
        )
    dmf.ellipse([86, 86, 170, 170], fill=(255, 248, 205, 255))
    mf.filter(ImageFilter.GaussianBlur(radius=3.5)).save(TEXTURES_DIR / "muzzle_flash.png")

    # 13. Стильный виньеточный фон Panorama UI (menu_bg.png)
    bg_w, bg_h = 1280, 720
    yy = np.linspace(0.0, 1.0, bg_h)[:, None]
    xx = np.linspace(0.0, 1.0, bg_w)[None, :]
    r = 12 + 28 * (1.0 - yy) + 38 * np.exp(-((xx - 0.72) ** 2 + (yy - 0.35) ** 2) / 0.08)
    g = 18 + 26 * (1.0 - yy) + 22 * np.exp(-((xx - 0.72) ** 2 + (yy - 0.35) ** 2) / 0.08)
    b = 30 + 38 * (1.0 - yy) + 12 * np.exp(-((xx - 0.20) ** 2 + (yy - 0.75) ** 2) / 0.11)
    a = np.clip(235 - 155 * xx, 48, 242)
    bg_arr = np.stack([r, g, b, np.broadcast_to(a, r.shape)], axis=-1)
    bg_img = Image.fromarray(np.clip(bg_arr, 0, 255).astype(np.uint8), mode="RGBA")
    dbg = ImageDraw.Draw(bg_img)
    for stripe in range(-400, 1500, 160):
        dbg.line([stripe, 720, stripe + 340, 0], fill=(245, 166, 35, 26), width=2)
    bg_img.save(TEXTURES_DIR / "menu_bg.png")

    # 14. Иконки HP и Брони
    hp_icon = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    dhp = ImageDraw.Draw(hp_icon)
    dhp.rounded_rectangle([24, 8, 40, 56], radius=4, fill=(92, 238, 150, 255))
    dhp.rounded_rectangle([8, 24, 56, 40], radius=4, fill=(92, 238, 150, 255))
    hp_icon.save(TEXTURES_DIR / "icon_hp.png")

    ar_icon = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    dar = ImageDraw.Draw(ar_icon)
    dar.polygon([(32, 6), (56, 16), (50, 42), (32, 58), (14, 42), (8, 16)], fill=(85, 178, 255, 255))
    ar_icon.save(TEXTURES_DIR / "icon_armor.png")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. ПРОЦЕДУРНЫЙ СИНТЕЗ 32 ЗВУКОВЫХ ЭФФЕКТОВ (.WAV)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _write_wav(path: Path, samples: np.ndarray, sample_rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())


def generate_all_sounds() -> None:
    sr = 44100
    rng = np.random.default_rng(1337)

    # 0. Эпичная кинематографичная фанфара заставки "АлкoДимас для усатого Эльдара" (intro_fanfare.wav)
    t = np.linspace(0, 3.2, int(sr * 3.2), endpoint=False)
    sub_drop = np.sin(2 * np.pi * (88.0 * np.exp(-t * 0.55) + 42.0) * t) * np.exp(-t * 0.9) * 0.55
    brass_chord = (
        0.28 * np.sin(2 * np.pi * 146.83 * t)
        + 0.24 * np.sin(2 * np.pi * 220.00 * t)
        + 0.22 * np.sin(2 * np.pi * 293.66 * t)
        + 0.18 * np.sin(2 * np.pi * 369.99 * t)
    ) * np.clip(t * 2.2, 0.0, 1.0) * np.exp(-np.maximum(0.0, t - 0.6) * 0.85)
    shimmer = np.sin(2 * np.pi * 587.33 * t) * np.exp(-np.abs(t - 1.1) * 2.5) * 0.22
    _write_wav(SOUNDS_DIR / "intro_fanfare.wav", sub_drop + brass_chord + shimmer, sr)

    # 1. AK-47
    t = np.linspace(0, 0.28, int(sr * 0.28), endpoint=False)
    ak = (rng.normal(0, 1, len(t)) * np.exp(-t * 26.0) * 0.72 + np.sin(2 * np.pi * (150 * np.exp(-t * 16)) * t) * np.exp(-t * 18.0) * 0.68)
    _write_wav(SOUNDS_DIR / "ak47_shoot.wav", ak, sr)

    # 2. M4A1-S
    t = np.linspace(0, 0.19, int(sr * 0.19), endpoint=False)
    m4 = (rng.normal(0, 1, len(t)) * np.exp(-t * 42.0) * 0.48 + np.sin(2 * np.pi * 235 * t) * np.exp(-t * 34.0) * 0.42)
    _write_wav(SOUNDS_DIR / "m4a1_shoot.wav", m4, sr)

    # 3. AWP
    t = np.linspace(0, 0.62, int(sr * 0.62), endpoint=False)
    awp = (
        rng.normal(0, 1, len(t)) * np.exp(-t * 11.0) * 0.82
        + np.sin(2 * np.pi * (96 * np.exp(-t * 7.5)) * t) * np.exp(-t * 8.5) * 0.88
    )
    _write_wav(SOUNDS_DIR / "awp_shoot.wav", awp, sr)

    # 4. P90 (скорострельный чёткий импульс 5.7x28mm)
    t = np.linspace(0, 0.14, int(sr * 0.14), endpoint=False)
    p90_s = rng.normal(0, 1, len(t)) * np.exp(-t * 46.0) * 0.56 + np.sin(2 * np.pi * 265 * t) * np.exp(-t * 36.0) * 0.48
    _write_wav(SOUNDS_DIR / "p90_shoot.wav", p90_s, sr)

    # 5. MP9
    t = np.linspace(0, 0.15, int(sr * 0.15), endpoint=False)
    mp9 = rng.normal(0, 1, len(t)) * np.exp(-t * 44.0) * 0.55 + np.sin(2 * np.pi * 240 * t) * np.exp(-t * 35.0) * 0.45
    _write_wav(SOUNDS_DIR / "mp9_shoot.wav", mp9, sr)

    # 6. XM1014 Shotgun
    t = np.linspace(0, 0.40, int(sr * 0.40), endpoint=False)
    sg = rng.normal(0, 1, len(t)) * np.exp(-t * 17.0) * 0.82 + np.sin(2 * np.pi * (115 * np.exp(-t * 11)) * t) * np.exp(-t * 14.0) * 0.75
    _write_wav(SOUNDS_DIR / "shotgun_shoot.wav", sg, sr)

    # 7. FAMAS
    t = np.linspace(0, 0.22, int(sr * 0.22), endpoint=False)
    fam = rng.normal(0, 1, len(t)) * np.exp(-t * 31.0) * 0.65 + np.sin(2 * np.pi * 175 * t) * np.exp(-t * 22.0) * 0.55
    _write_wav(SOUNDS_DIR / "famas_shoot.wav", fam, sr)

    # 8. USP-S
    t = np.linspace(0, 0.16, int(sr * 0.16), endpoint=False)
    usp = rng.normal(0, 1, len(t)) * np.exp(-t * 48.0) * 0.42 + np.sin(2 * np.pi * 290 * t) * np.exp(-t * 40.0) * 0.36
    _write_wav(SOUNDS_DIR / "usp_shoot.wav", usp, sr)

    # 9. Desert Eagle
    t = np.linspace(0, 0.36, int(sr * 0.36), endpoint=False)
    de = rng.normal(0, 1, len(t)) * np.exp(-t * 18.0) * 0.78 + np.sin(2 * np.pi * (118 * np.exp(-t * 12)) * t) * np.exp(-t * 14.0) * 0.78
    _write_wav(SOUNDS_DIR / "deagle_shoot.wav", de, sr)

    # 10. Glock-18
    t = np.linspace(0, 0.17, int(sr * 0.17), endpoint=False)
    gl = rng.normal(0, 1, len(t)) * np.exp(-t * 38.0) * 0.56 + np.sin(2 * np.pi * 215 * t) * np.exp(-t * 30.0) * 0.48
    _write_wav(SOUNDS_DIR / "glock_shoot.wav", gl, sr)

    # 11. Zeus x27 высоковольтный разряд (zeus_zap.wav)
    t = np.linspace(0, 0.34, int(sr * 0.34), endpoint=False)
    zap = (
        np.sign(np.sin(2 * np.pi * 180 * t + 6 * np.sin(2 * np.pi * 55 * t))) * 0.42
        + rng.normal(0, 1, len(t)) * 0.45
    ) * np.exp(-t * 10.5)
    _write_wav(SOUNDS_DIR / "zeus_zap.wav", zap, sr)

    # 12. Нож Керамбит
    t = np.linspace(0, 0.18, int(sr * 0.18), endpoint=False)
    swish = rng.normal(0, 1, len(t)) * np.sin(np.pi * t / 0.18) * 0.45 + np.sin(2 * np.pi * 1400 * t) * np.exp(-t * 36.0) * 0.22
    _write_wav(SOUNDS_DIR / "knife_slash.wav", swish, sr)

    # 13. Перезарядка
    t = np.linspace(0, 0.55, int(sr * 0.55), endpoint=False)
    rel = np.zeros_like(t)
    for offset, freq in ((0.04, 880.0), (0.24, 1140.0), (0.42, 1520.0)):
        m = t >= offset
        dt_s = t[m] - offset
        rel[m] += (np.sin(2 * np.pi * freq * dt_s) + rng.normal(0, 0.4, len(dt_s))) * np.exp(-dt_s * 45.0) * 0.55
    _write_wav(SOUNDS_DIR / "reload.wav", rel, sr)

    # 14. Щелчок / клик UI
    t = np.linspace(0, 0.08, int(sr * 0.08), endpoint=False)
    _write_wav(SOUNDS_DIR / "empty_click.wav", np.sin(2 * np.pi * 1650 * t) * np.exp(-t * 75.0) * 0.55, sr)

    # 15. Звон латунной гильзы
    t = np.linspace(0, 0.11, int(sr * 0.11), endpoint=False)
    clink = (np.sin(2 * np.pi * 4250 * t) + 0.6 * np.sin(2 * np.pi * 6120 * t)) * np.exp(-t * 52.0) * 0.28
    _write_wav(SOUNDS_DIR / "shell_clink.wav", clink, sr)

    # 16. Шаг
    t = np.linspace(0, 0.12, int(sr * 0.12), endpoint=False)
    step = (rng.normal(0, 1, len(t)) * 0.40 + np.sin(2 * np.pi * 92 * t) * 0.45) * np.exp(-t * 32.0)
    _write_wav(SOUNDS_DIR / "footstep.wav", step, sr)

    # 17. Hitmarker & Headshot
    t = np.linspace(0, 0.07, int(sr * 0.07), endpoint=False)
    _write_wav(SOUNDS_DIR / "hitmarker.wav", np.sin(2 * np.pi * 2250 * t) * np.exp(-t * 65.0) * 0.55, sr)

    t = np.linspace(0, 0.22, int(sr * 0.22), endpoint=False)
    hs = (np.sin(2 * np.pi * 1880 * t) + 0.6 * np.sin(2 * np.pi * 2920 * t)) * np.exp(-t * 20.0) * 0.65
    _write_wav(SOUNDS_DIR / "headshot.wav", hs, sr)

    # 18. Взрыв HE / бочки / C4
    t = np.linspace(0, 0.95, int(sr * 0.95), endpoint=False)
    expl = rng.normal(0, 1, len(t)) * np.exp(-t * 5.2) * 0.85 + np.sin(2 * np.pi * (68 * np.exp(-t * 3.5)) * t) * np.exp(-t * 4.5) * 0.85
    _write_wav(SOUNDS_DIR / "explosion.wav", expl, sr)

    # 19. Светошумовая Flashbang
    t = np.linspace(0, 0.70, int(sr * 0.70), endpoint=False)
    fb = rng.normal(0, 1, len(t)) * np.exp(-t * 24.0) * 0.75 + np.sin(2 * np.pi * 3450 * t) * np.exp(-t * 3.8) * 0.35
    _write_wav(SOUNDS_DIR / "flashbang.wav", fb, sr)

    # 20. Шипение дыма
    t = np.linspace(0, 0.80, int(sr * 0.80), endpoint=False)
    _write_wav(SOUNDS_DIR / "smoke_hiss.wav", rng.normal(0, 1, len(t)) * np.sin(np.pi * t / 0.80) * 0.42, sr)

    # 21. Звуки C4
    t = np.linspace(0, 0.09, int(sr * 0.09), endpoint=False)
    _write_wav(SOUNDS_DIR / "c4_beep.wav", np.sin(2 * np.pi * 2680 * t) * np.exp(-t * 28.0) * 0.62, sr)

    t = np.linspace(0, 0.45, int(sr * 0.45), endpoint=False)
    plant = np.sin(2 * np.pi * (900 + 800 * t) * t) * np.exp(-t * 6.5) * 0.55
    _write_wav(SOUNDS_DIR / "c4_plant.wav", plant, sr)

    t = np.linspace(0, 0.50, int(sr * 0.50), endpoint=False)
    defuse = (np.sin(2 * np.pi * 660 * t) + np.sin(2 * np.pi * 990 * t)) * np.exp(-t * 5.5) * 0.52
    _write_wav(SOUNDS_DIR / "c4_defuse.wav", defuse, sr)

    # 22. Покупка и Киллстрик и Рация
    t = np.linspace(0, 0.24, int(sr * 0.24), endpoint=False)
    buy_s = (np.sin(2 * np.pi * 1320 * t) + np.sin(2 * np.pi * 1760 * np.maximum(0, t - 0.08))) * np.exp(-t * 14.0) * 0.45
    _write_wav(SOUNDS_DIR / "buy_item.wav", buy_s, sr)

    t = np.linspace(0, 0.45, int(sr * 0.45), endpoint=False)
    ks = (np.sin(2 * np.pi * 587.3 * t) + np.sin(2 * np.pi * 880.0 * t)) * np.exp(-t * 5.0) * 0.52
    _write_wav(SOUNDS_DIR / "killstreak.wav", ks, sr)

    t = np.linspace(0, 0.18, int(sr * 0.18), endpoint=False)
    radio = (np.sin(2 * np.pi * 1480 * t) * (t < 0.06) + np.sin(2 * np.pi * 1920 * t) * (t >= 0.07)) * 0.40 + rng.normal(0, 0.06, len(t))
    _write_wav(SOUNDS_DIR / "radio_beep.wav", radio, sr)

    # 23. Урон игроку
    t = np.linspace(0, 0.20, int(sr * 0.20), endpoint=False)
    hurt = np.sin(2 * np.pi * 105 * t) * np.exp(-t * 16.0) * 0.65 + rng.normal(0, 0.3, len(t)) * np.exp(-t * 22.0)
    _write_wav(SOUNDS_DIR / "player_hurt.wav", hurt, sr)

    # 24. Победа и Поражение
    dur = 1.4
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    win = np.zeros_like(t)
    for idx, freq in enumerate((523.25, 659.25, 783.99, 1046.50)):
        st = idx * 0.22
        m = t >= st
        dt_w = t[m] - st
        win[m] += np.sin(2 * np.pi * freq * dt_w) * np.exp(-dt_w * 3.2) * 0.36
    _write_wav(SOUNDS_DIR / "round_win.wav", win, sr)

    lose = np.zeros_like(t)
    for idx, freq in enumerate((392.0, 349.23, 311.13, 261.63)):
        st = idx * 0.26
        m = t >= st
        dt_l = t[m] - st
        lose[m] += np.sin(2 * np.pi * freq * dt_l) * np.exp(-dt_l * 2.8) * 0.38
    _write_wav(SOUNDS_DIR / "round_lose.wav", lose, sr)

    # 25. Атмосферная тема меню
    m_dur = 8.0
    t = np.linspace(0, m_dur, int(sr * m_dur), endpoint=False)
    pad = (
        0.22 * np.sin(2 * np.pi * 110.0 * t)
        + 0.16 * np.sin(2 * np.pi * 164.81 * t)
        + 0.13 * np.sin(2 * np.pi * 220.0 * t + np.sin(2 * np.pi * 0.25 * t))
    )
    pulse_env = 0.55 + 0.45 * np.sin(2 * np.pi * 0.5 * t)
    fade = np.minimum(1.0, np.minimum(t / 0.4, (m_dur - t) / 0.4))
    _write_wav(SOUNDS_DIR / "menu_music.wav", pad * pulse_env * fade * 0.55, sr)


def ensure_all_starter_assets() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    generate_all_models()
    generate_all_textures()
    generate_all_sounds()


if __name__ == "__main__":
    ensure_all_starter_assets()
    print("Generated all 17 smooth .glb models, 14 HD .png textures, and 32 .wav sounds!")
