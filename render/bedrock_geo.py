"""
基岩版几何 (Bedrock geo.json) 解析与烘焙。

TACZ 与 SuperbWarfare 的枪械模型都是 Blockbench 导出的
``minecraft:geometry`` 1.12 / 1.16 立方体模型。本模块只实现公开的几何约定,
不依赖这两个模组的代码:

* 骨骼 pivot 为模型空间绝对坐标 (像素), 旋转顺序 X→Y→Z (度)
* 父骨骼变换为 ``T(pivot) · Rz · Ry · Rx · T(-pivot)``, 子骨骼在父矩阵上叠加
* 立方体 origin 为最小角, 负尺寸表示翻转
* 每面 UV 与方盒 UV 展开都按基岩版约定
* 输出单位为米 (16 像素 = 1 方块 = 1 米), +Y 上, -Z 为枪口, 与本游戏枪械空间一致
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

PIXEL = 1.0 / 16.0

# 面顶点序与 TACZ / 基岩版渲染器一致: v1..v8 = 最小角出发的 8 个角
# v1 (---) v2 (+--) v3 (++-) v4 (-+-) v5 (--+) v6 (+-+) v7 (+++) v8 (-++)
_FACE_IDX = {
    "down": (5, 4, 0, 1),
    "up": (2, 3, 7, 6),
    "west": (0, 4, 7, 3),
    "north": (1, 0, 3, 2),
    "east": (5, 1, 2, 6),
    "south": (4, 5, 6, 7),
}
_FACE_ORDER = ("down", "up", "west", "north", "east", "south")

# 会被整棵子树隐藏的定位 / 占位骨骼
_HIDE_SUBTREE = {
    "lefthand", "righthand", "lefthand_pos", "righthand_pos",
    "left_hand", "right_hand",
    "attachment_adapter",
    "additional_magazine",
    "laser_beam",
}
_HAND_POS = {"lefthand_pos", "righthand_pos", "left_hand_pos", "right_hand_pos"}
_SLIDE_ROOTS = {"slide", "slide2", "huatao"}
_BOLT_ROOTS = {"bolt", "pull", "charging_handle", "bolt_handle", "gun_bolt"}
_PUMP_ROOTS = {"pump", "forend", "pump_handguard"}
_MAG_ROOTS = {"magazine", "magazine_pos"}

# 互斥变体: 只显示当前配件对应的那一棵
_MAG_VARIANT = {
    "mag_standard": "std",
    "magazine_standard": "std",
    "mag_extended_1": "ext",
    "magazine_extend": "ext",
    "mag_extended_2": "ext2",
    "mag_extended_3": "drum",
    "magazine_extend_pro": "drum",
}
_STOCK_VARIANT = {
    "oem_stock_standard": "std",
    "oem_stock_light": "light",
    "oem_stock_heavy": "heavy",
    "custom_stock_adapter": "custom",
}
_OTHER_VARIANT = {
    "handguard_default": ("hg", "default"),
    "handguard_tactical": ("hg", "tactical"),
    "sight": ("sight", "iron"),
    "sight_folded": ("sight", "folded"),
    "mount": ("mount", "on"),
    "carry": ("carry", "iron"),
    "muzzle_default": ("muzzle", "default"),
    "scope_default": ("scope", "default"),
    "grip_default": ("grip", "default"),
    "laser_default": ("laser", "default"),
    "stock_default": ("stock", "default"),
}


@dataclass
class Bone:
    name: str
    parent: Optional[str]
    pivot: np.ndarray
    rotation: Tuple[float, float, float]
    cubes: list
    mirror: bool = False


@dataclass
class Quad:
    verts: Tuple[Tuple[float, float, float], ...]
    uvs: Tuple[Tuple[float, float], ...]
    normal: Tuple[float, float, float]
    alpha: float = 1.0
    emissive: bool = False


@dataclass
class BakedGun:
    groups: Dict[str, List[Quad]] = field(default_factory=dict)
    anchors: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)
    bounds_min: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    bounds_max: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    pack: str = ""
    model_name: str = ""
    quad_count: int = 0

    @property
    def center(self):
        return tuple((a + b) * 0.5 for a, b in zip(self.bounds_min, self.bounds_max))

    @property
    def span(self):
        return tuple(b - a for a, b in zip(self.bounds_min, self.bounds_max))


def _arr3(v, default=(0.0, 0.0, 0.0)):
    if not v or len(v) < 3:
        return np.array(default, dtype=np.float64)
    return np.array([float(v[0]), float(v[1]), float(v[2])], dtype=np.float64)


def _rot(rx, ry, rz):
    """列向量, 先 Rx 再 Ry 再 Rz (与基岩版 / Java ModelPart 一致)。"""
    ax, ay, az = math.radians(rx), math.radians(ry), math.radians(rz)
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    cz, sz = math.cos(az), math.sin(az)
    rx_m = np.array([[1, 0, 0, 0], [0, cx, -sx, 0], [0, sx, cx, 0], [0, 0, 0, 1]], np.float64)
    ry_m = np.array([[cy, 0, sy, 0], [0, 1, 0, 0], [-sy, 0, cy, 0], [0, 0, 0, 1]], np.float64)
    rz_m = np.array([[cz, -sz, 0, 0], [sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], np.float64)
    return rz_m @ ry_m @ rx_m


def _T(p):
    m = np.identity(4)
    m[:3, 3] = p
    return m


def parse_geometry(data) -> Tuple[List[Bone], int, int]:
    """返回 (bones, texture_width, texture_height)。"""
    geos = data.get("minecraft:geometry")
    geo = None
    if isinstance(geos, list) and geos:
        geo = geos[0]
    elif isinstance(geos, dict):
        if "bones" in geos:
            geo = geos
        else:
            for v in geos.values():
                if isinstance(v, dict) and ("bones" in v or "description" in v):
                    geo = v
                    break
    if geo is None and "bones" in data:
        geo = data
    if not geo:
        return [], 64, 64
    desc = geo.get("description") or {}
    tw = int(desc.get("texture_width") or 64)
    th = int(desc.get("texture_height") or 64)
    bones = []
    for raw in geo.get("bones") or []:
        name = str(raw.get("name") or "")
        if not name:
            continue
        rot = raw.get("rotation") or [0, 0, 0]
        bones.append(Bone(
            name=name,
            parent=raw.get("parent"),
            pivot=_arr3(raw.get("pivot")),
            rotation=(float(rot[0]) if len(rot) > 0 else 0.0,
                      float(rot[1]) if len(rot) > 1 else 0.0,
                      float(rot[2]) if len(rot) > 2 else 0.0),
            cubes=list(raw.get("cubes") or []),
            mirror=bool(raw.get("mirror", False)),
        ))
    return bones, tw, th


def _selected_variants(atts):
    mag = (atts or {}).get("magazine", "mag_std")
    optic = (atts or {}).get("optic", "iron")
    muzzle = (atts or {}).get("muzzle", "muzzle_std")
    ub = (atts or {}).get("underbarrel", "ub_none")
    if mag == "mag_drum":
        mag_v = "drum"
    elif mag == "mag_ext":
        mag_v = "ext"
    else:
        mag_v = "std"
    return {
        "mag": mag_v,
        "stock": "std",
        "hg": "tactical" if ub in ("vgrip", "agrip", "laser") else "default",
        "sight": "folded" if optic != "iron" else "iron",
        "mount": "on" if optic != "iron" else "off",
        "carry": "iron" if optic == "iron" else "off",
        "muzzle": "default" if muzzle == "muzzle_std" else "off",
        "scope": "default" if optic == "iron" else "off",
        "grip": "default" if ub not in ("vgrip", "agrip") else "off",
        "laser": "default" if ub != "laser" else "off",
    }


def _variant_of(name):
    if name in _MAG_VARIANT:
        return ("mag", _MAG_VARIANT[name])
    if name in _STOCK_VARIANT:
        return ("stock", _STOCK_VARIANT[name])
    if name in _OTHER_VARIANT:
        return _OTHER_VARIANT[name]
    return None


def _is_shell(name):
    if name in ("shells", "bullet_shell", "shell"):
        return True
    if name.startswith("shell") and name[5:].isdigit():
        return True
    return False


def _is_ammo_variant(name):
    """SuperbWarfare 把多种弹药烤进同一模型, 只保留 *_api_default。"""
    if "_api_" not in name:
        return False
    return "api_default" not in name


def _is_illuminated(name):
    return name.endswith("_illuminated") or "glow" in name or name.endswith("_light")


def _group_for(name, inherited, slide_roots):
    if name in slide_roots:
        return "slide"
    if name in _BOLT_ROOTS:
        return "bolt"
    if name in _PUMP_ROOTS:
        return "pump"
    if name in _MAG_ROOTS or name in _MAG_VARIANT:
        return "mag"
    return inherited or "body"


def _face_uv(cube, face, tw, th):
    uv = cube.get("uv")
    if isinstance(uv, dict):
        item = uv.get(face)
        if not item:
            return None
        if isinstance(item, dict):
            origin = item.get("uv") or [0, 0]
            size = item.get("uv_size") or [0, 0]
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            origin, size = item[:2], [0, 0]
        else:
            return None
        if abs(float(size[0])) < 1e-6 and abs(float(size[1])) < 1e-6:
            return None
        u1, v1 = float(origin[0]), float(origin[1])
        u2, v2 = u1 + float(size[0]), v1 + float(size[1])
        return u1 / tw, v1 / th, u2 / tw, v2 / th
    if isinstance(uv, (list, tuple)) and len(uv) >= 2 and face:
        return _box_uv(float(uv[0]), float(uv[1]), cube, face, tw, th)
    return None


def _box_uv(u, v, cube, face, tw, th):
    """基岩版方盒 UV 展开 (与 Java ModelBox 相同的走线)。"""
    size = cube.get("size") or [0, 0, 0]
    dx, dy, dz = abs(float(size[0])), abs(float(size[1])), abs(float(size[2]))
    p1, p2 = u + dz, u + dz + dx
    p3, p4 = p2 + dx, p2 + dz
    p5 = p4 + dx
    p6, p7, p8, p9 = v + dz, v + dz + dy, v, u
    table = {
        "down": (p1, p8, p2, p6),
        "up": (p2, p6, p3, p8),
        "west": (p9, p6, p1, p7),
        "north": (p1, p6, p2, p7),
        "east": (p2, p6, p4, p7),
        "south": (p4, p6, p5, p7),
    }
    u1, v1, u2, v2 = table[face]
    return u1 / tw, v1 / th, u2 / tw, v2 / th


def _sample_alpha(rgba, u1, v1, u2, v2):
    if rgba is None:
        return 1.0
    h, w = rgba.shape[:2]
    u = (u1 + u2) * 0.5
    v = (v1 + v2) * 0.5
    x = int(max(0, min(w - 1, abs(u) * w)))
    y = int(max(0, min(h - 1, abs(v) * h)))
    if rgba.shape[2] < 4:
        return 1.0
    return float(rgba[y, x, 3]) / 255.0


# 基岩版加载进 Java ModelPart 时, 根骨骼 Y 要换成 24 - y, 子骨骼 Y 取反。
# TACZ / SuperbWarfare 都走这条路径; 直接在 Y 朝上的绝对坐标里绕 pivot 转, 带旋转的零件会散开。
_JAVA_ROOT_Y = 24.0


def _game_from_java(p):
    return (float(p[0]), _JAVA_ROOT_Y * PIXEL - float(p[1]), float(p[2]))


def _java_point(mat, local_px):
    v = mat @ np.array([local_px[0] * PIXEL, local_px[1] * PIXEL, local_px[2] * PIXEL, 1.0], np.float64)
    return _game_from_java(v[:3])


def _bone_java_matrix(bone, parent_mat, parent_pivot):
    if parent_pivot is None:
        rel = np.array([bone.pivot[0], _JAVA_ROOT_Y - bone.pivot[1], bone.pivot[2]], np.float64)
    else:
        rel = np.array([
            bone.pivot[0] - parent_pivot[0],
            parent_pivot[1] - bone.pivot[1],
            bone.pivot[2] - parent_pivot[2],
        ], np.float64)
    return parent_mat @ _T(rel * PIXEL) @ _rot(*bone.rotation)


def _emit_cube(quads, cube, mat, pivot, tw, th, rgba, emissive, mirror):
    origin = _arr3(cube.get("origin"))
    size = _arr3(cube.get("size"))
    inflate = float(cube.get("inflate") or 0.0)
    if inflate:
        origin = origin - inflate
        size = size + inflate * 2.0
    if abs(size[0]) < 1e-4 and abs(size[1]) < 1e-4 and abs(size[2]) < 1e-4:
        return
    # 相对旋转中心, 且 Y 与 Java 版一致 (向下为正)
    x = origin[0] - pivot[0]
    y = pivot[1] - origin[1] - size[1]
    z = origin[2] - pivot[2]
    sx, sy, sz = float(size[0]), float(size[1]), float(size[2])
    corners = [
        (x, y, z), (x + sx, y, z), (x + sx, y + sy, z), (x, y + sy, z),
        (x, y, z + sz), (x + sx, y, z + sz), (x + sx, y + sy, z + sz), (x, y + sy, z + sz),
    ]
    world = [_java_point(mat, c) for c in corners]
    cube_mirror = bool(cube.get("mirror", False)) or mirror
    for face in _FACE_ORDER:
        uv = _face_uv(cube, face, tw, th)
        if uv is None:
            continue
        u1, v1, u2, v2 = uv
        idx = _FACE_IDX[face]
        if cube_mirror and face in ("east", "west"):
            idx = tuple(reversed(idx))
        pts = tuple(tuple(float(x) for x in world[i]) for i in idx)
        # Y 从 Java 朝下翻回朝上, 绕序反了, 连同 UV 一起倒过来
        pts = (pts[0], pts[3], pts[2], pts[1])
        # 基岩版 UV: v 向下增大; OpenGL 纹理 v=0 在底部
        uvs = (
            (u2, 1.0 - v1),
            (u2, 1.0 - v2),
            (u1, 1.0 - v2),
            (u1, 1.0 - v1),
        )
        a = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1], pts[1][2] - pts[0][2]
        b = pts[2][0] - pts[0][0], pts[2][1] - pts[0][1], pts[2][2] - pts[0][2]
        n = (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )
        ln = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) or 1.0
        n = (n[0] / ln, n[1] / ln, n[2] / ln)
        alpha = _sample_alpha(rgba, u1, v1, u2, v2)
        if alpha < 0.05:
            continue
        quads.append(Quad(pts, uvs, n, alpha, emissive))


def bake_gun(data, atts=None, rgba=None, pack="", model_name="", kind="rifle") -> BakedGun:
    bones, tw, th = parse_geometry(data)
    by_name = {b.name: b for b in bones}
    children = {b.name: [] for b in bones}
    roots = []
    for b in bones:
        if b.parent and b.parent in by_name and b.parent != b.name:
            children[b.parent].append(b.name)
        else:
            roots.append(b.name)

    matrices = {}

    def matrix_of(name, stack):
        if name in matrices:
            return matrices[name]
        if name in stack:
            matrices[name] = np.identity(4)
            return matrices[name]
        bone = by_name[name]
        stack.add(name)
        if bone.parent in by_name:
            parent = matrix_of(bone.parent, stack)
            parent_pivot = by_name[bone.parent].pivot
        else:
            parent = np.identity(4)
            parent_pivot = None
        stack.discard(name)
        matrices[name] = _bone_java_matrix(bone, parent, parent_pivot)
        return matrices[name]

    for n in by_name:
        matrix_of(n, set())

    selected = _selected_variants(atts)
    slide_roots = _SLIDE_ROOTS if kind == "pistol" else set()
    # 扩容弹匣若模型没有 ext 变体, 回退到 std / ext2
    present_mag = {v for n, v in _MAG_VARIANT.items() if n in by_name}
    if selected["mag"] not in present_mag:
        if selected["mag"] == "ext" and "ext2" in present_mag:
            selected["mag"] = "ext2"
        elif "std" in present_mag:
            selected["mag"] = "std"

    groups = {"body": [], "mag": [], "bolt": [], "slide": [], "pump": [], "glass": []}
    anchors = {}

    def consider_anchor(name, world_pivot):
        key = {
            "muzzle_flash": "muzzle",
            "muzzle_pos": "muzzle",
            "flare": "muzzle",
            "iron_view": "iron",
            "idle_view": "idle",
            "scope_pos": "scope",
            "righthand_pos": "grip_r",
            "lefthand_pos": "grip_l",
            "magazine": "mag",
            "magazine_pos": "mag",
            "grip_pos": "grip",
            "shell": "shell",
        }.get(name)
        if key and key not in anchors:
            anchors[key] = tuple(float(x) for x in world_pivot)

    def walk(name, inherited_group, inherited_hide, inherited_variant):
        bone = by_name[name]
        lname = bone.name.lower()
        hide = inherited_hide
        hide_sub = False
        variant = inherited_variant
        if lname in _HIDE_SUBTREE or lname.startswith("refit_") or lname in _HAND_POS:
            hide = True
            hide_sub = True
        if _is_shell(lname) or _is_ammo_variant(lname):
            hide = True
            hide_sub = True
        var = _variant_of(lname)
        if var:
            kind, value = var
            variant = (kind, value)
            # mount=off 表示未安装瞄具, 该变体应隐藏
            want = selected.get(kind)
            if want != value:
                hide = True
                hide_sub = True
        group = "body" if hide else _group_for(lname, inherited_group, slide_roots)
        if inherited_group in ("slide", "mag", "bolt", "pump") and lname not in _SLIDE_ROOTS | _BOLT_ROOTS | _PUMP_ROOTS | _MAG_ROOTS and not var:
            # 已在活动部件子树里, 继续跟随, 除非自己是另一类根
            if lname not in _SLIDE_ROOTS | _BOLT_ROOTS | _PUMP_ROOTS:
                group = inherited_group if not hide else group
        world_pivot = _game_from_java(matrices[name][:3, 3])
        consider_anchor(lname, world_pivot)
        if not hide:
            emissive = _is_illuminated(lname)
            target_groups = groups
            for cube in bone.cubes:
                # 跳过多边形网格 (poly_mesh); 默认枪包是立方体
                if not isinstance(cube, dict) or "origin" not in cube:
                    continue
                rot = cube.get("rotation")
                cpivot = cube.get("pivot")
                mat = matrices[name]
                pivot = bone.pivot
                if rot and cpivot:
                    pv = _arr3(cpivot)
                    rel = np.array([
                        pv[0] - bone.pivot[0],
                        bone.pivot[1] - pv[1],
                        pv[2] - bone.pivot[2],
                    ], np.float64) * PIXEL
                    mat = mat @ _T(rel) @ _rot(float(rot[0]), float(rot[1]), float(rot[2]))
                    pivot = pv
                tmp = []
                _emit_cube(tmp, cube, mat, pivot, tw, th, rgba, emissive, bone.mirror)
                for q in tmp:
                    g = "glass" if (q.alpha < 0.92 or "lens" in lname or "glass" in lname or "reticle" in lname) else group
                    if g not in target_groups:
                        g = "body"
                    # 半透明镜片仍要跟着套筒走时, 放进 slide 会失去混合; 镜片单独一组即可
                    target_groups[g].append(q)
        for child in children.get(name, []):
            # 隐藏一旦成立就盖住整棵子树 (转接件、备用弹匣、手部占位都有嵌套骨骼)
            walk(child, group if not hide else inherited_group, hide or hide_sub, variant)

    for root in roots:
        walk(root, "body", False, None)

    # 没有 magazine 根、但有 mag_standard 时, 上面的 walk 已经按变体归入 mag 组
    pts = []
    count = 0
    for qs in groups.values():
        count += len(qs)
        for q in qs:
            pts.extend(q.verts)
    baked = BakedGun(groups=groups, anchors=anchors, pack=pack, model_name=model_name, quad_count=count)
    if pts:
        arr = np.array(pts, dtype=np.float64)
        baked.bounds_min = tuple(float(x) for x in arr.min(axis=0))
        baked.bounds_max = tuple(float(x) for x in arr.max(axis=0))
    # 螺栓 / 泵动锚点: 用该组包围盒中心
    for g, key in (("bolt", "bolt"), ("pump", "pump"), ("slide", "slide"), ("mag", "mag")):
        qs = groups.get(g) or []
        if not qs:
            continue
        acc = np.zeros(3)
        n = 0
        for q in qs:
            for v in q.verts:
                acc += v
                n += 1
        if n and key not in anchors or g != "mag":
            anchors[key] = tuple(float(x) for x in acc / n)
    baked.anchors = anchors
    return baked
