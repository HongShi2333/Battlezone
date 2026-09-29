"""
程序化枪械建模。

每把枪由若干 "部件组" 组成, 动画系统可以单独移动它们:
    body   机匣/枪管/枪托/瞄具等 (静止)
    mag    弹匣 (换弹时拔出/插入)
    bolt   拉机柄/枪栓 (拉栓, 空仓挂机)
    slide  手枪套筒 (射击后坐)
    pump   泵动护木
    glass  瞄具镜片 (半透明)

模型坐标: 原点=握把顶部 (右手位置), -Z=枪口方向, +Y=上, 单位米。
"""
import math
import numpy as np
from OpenGL.GL import *
from weapons.definitions import WEAPONS
from weapons.attachments import ATTACHMENTS
from .gl_util import emit_box, draw_box, draw_cylinder

M_DARK = (0.07, 0.07, 0.075)
M_STEEL = (0.22, 0.22, 0.23)
M_RAIL = (0.10, 0.10, 0.10)
BRASS = (0.78, 0.58, 0.25)
RED_SHELL = (0.65, 0.12, 0.1)


class GunModel:
    def __init__(self):
        self.parts = {"body": [], "mag": [], "bolt": [], "slide": [], "pump": [], "glass": []}
        self.sight_y = 0.1
        self.sight_x = 0.0
        self.eye_ref_z = 0.05
        self.relief = 0.10
        self.muzzle = (0, 0.03, -0.6)
        self.grip_r = (0.0, -0.05, 0.03)
        self.grip_l = (0.0, 0.0, -0.3)
        self.mag_pos = (0, -0.1, -0.09)
        self.bolt_pos = (0.03, 0.05, 0.05)
        self.pump_pos = (0, 0.01, -0.3)
        self.rail_y = 0.078
        self.rail_z = -0.06
        self.kind = "rifle"
        self.lens_r = 0.0
        self.length = 0.8
        self.lists = {}

    def box(self, g, c, s, col, rx=0.0, ry=0.0, rz=0.0):
        # 7 元组: 旧版 _glass 只解包 5 个值会崩溃 (ValueError: too many values to unpack)
        self.parts[g].append(("box", c, s, col, rx, ry, rz))

    def cyl(self, g, c, r, l, col, axis="z", seg=12):
        self.parts[g].append(("cyl", c, r, l, col, axis, seg))

    # ── 编译为显示列表 ──
    def compile(self):
        mesh = getattr(self, "mesh", None) or {}
        groups = list(self.parts.keys())
        for g in mesh:
            if g not in groups:
                groups.append(g)
        for g in groups:
            prims = self.parts.get(g) or []
            quads = mesh.get(g) or []
            if not prims and not quads:
                continue
            lid = glGenLists(1)
            glNewList(lid, GL_COMPILE)
            if quads:
                self._emit_quads(quads)
            for p in prims:
                self._emit_prim(p)
            glEndList()
            self.lists[g] = lid

    def _emit_quads(self, quads):
        """贴图网格。显示列表结束时恢复光照 / 剔除 / 关闭贴图, 避免污染后续手套。"""
        tex = getattr(self, "tex_id", None)
        opaque, glow, glass = [], [], []
        for q in quads:
            if q.alpha < 0.92:
                glass.append(q)
            elif q.emissive:
                glow.append(q)
            else:
                opaque.append(q)

        def batch(items, lit):
            if not items:
                return
            if lit:
                glEnable(GL_LIGHTING)
            else:
                glDisable(GL_LIGHTING)
            glDisable(GL_CULL_FACE)
            if tex:
                glEnable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, tex)
            else:
                glDisable(GL_TEXTURE_2D)
            glBegin(GL_QUADS)
            for q in items:
                if tex:
                    glColor4f(1.0, 1.0, 1.0, q.alpha)
                else:
                    glColor4f(0.42, 0.43, 0.46, q.alpha)
                glNormal3f(*q.normal)
                for uv, v in zip(q.uvs, q.verts):
                    if tex:
                        glTexCoord2f(uv[0], uv[1])
                    glVertex3f(*v)
            glEnd()

        batch(opaque, True)
        batch(glow, False)
        batch(glass, False)
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_LIGHTING)
        glEnable(GL_CULL_FACE)
        glColor3f(1, 1, 1)

    def _emit_prim(self, p):
        if not p:
            return
        if p[0] == "box":
            c, s, col, rx, ry, rz = unpack_box(p)
            if rx or ry or rz:
                glPushMatrix()
                glTranslatef(*c)
                if rx:
                    glRotatef(rx, 1, 0, 0)
                if ry:
                    glRotatef(ry, 0, 1, 0)
                if rz:
                    glRotatef(rz, 0, 0, 1)
                draw_box(0, 0, 0, s[0], s[1], s[2], col[:3])
                glPopMatrix()
            else:
                draw_box(c[0], c[1], c[2], s[0], s[1], s[2], col[:3])
        elif p[0] == "cyl":
            c, r, l, col = p[1], p[2], p[3], p[4]
            axis = p[5] if len(p) > 5 else "z"
            seg = int(p[6]) if len(p) > 6 else 12
            draw_cylinder(c[0], c[1], c[2], r, l, col[:3], axis, seg)

    def draw(self, group):
        lid = self.lists.get(group)
        if lid:
            glCallList(lid)

    def delete(self):
        for lid in self.lists.values():
            glDeleteLists(lid, 1)
        self.lists = {}
        tid = getattr(self, "tex_id", None)
        if tid:
            glDeleteTextures([int(tid)])
            self.tex_id = None


def unpack_box(prim):
    """盒子图元。兼容 5 元组 ``(box, c, s, col, rx)`` 与 7 元组 (另含 ry, rz)。

    镜片通道如果按固定 5 个值解包, 7 元组会抛
    ``ValueError: too many values to unpack (expected 5)`` 并在开镜时崩掉。
    """
    c, s, col = prim[1], prim[2], prim[3]
    rx = float(prim[4]) if len(prim) > 4 else 0.0
    ry = float(prim[5]) if len(prim) > 5 else 0.0
    rz = float(prim[6]) if len(prim) > 6 else 0.0
    return c, s, col, rx, ry, rz


def _shade(c, k):
    return (min(1, c[0] * k), min(1, c[1] * k), min(1, c[2] * k))


# ════════════════════ 配件 ════════════════════
def _add_optic(m: GunModel, aid, iron_front_z, pistol=False):
    ry, rz = m.rail_y, m.rail_z
    a = ATTACHMENTS[aid]
    if aid == "iron":
        if pistol:
            return
        # 折叠机瞄 (立起)
        m.box("body", (0, ry + 0.018, rz + 0.12), (0.022, 0.03, 0.012), M_DARK)
        m.box("body", (-0.007, ry + 0.038, rz + 0.12), (0.005, 0.012, 0.008), M_DARK)
        m.box("body", (0.007, ry + 0.038, rz + 0.12), (0.005, 0.012, 0.008), M_DARK)
        m.box("body", (0, ry + 0.018, iron_front_z), (0.018, 0.03, 0.012), M_DARK)
        m.box("body", (0, ry + 0.040, iron_front_z), (0.004, 0.018, 0.004), M_DARK)
        m.sight_y = ry + 0.043
        m.eye_ref_z = rz + 0.12
        m.relief = 0.26
        return
    # 其它瞄具: 前后机瞄折叠
    if not pistol:
        m.box("body", (0, ry + 0.006, rz + 0.12), (0.02, 0.01, 0.02), M_DARK)
        m.box("body", (0, ry + 0.006, iron_front_z), (0.016, 0.01, 0.02), M_DARK)
    if aid == "rmr":
        z = 0.0
        m.box("body", (0, ry + 0.008, z), (0.026, 0.014, 0.04), M_DARK)
        m.box("body", (0, ry + 0.028, z - 0.012), (0.026, 0.028, 0.006), M_DARK)
        m.box("body", (-0.012, ry + 0.022, z), (0.004, 0.018, 0.03), M_DARK)
        m.box("body", (0.012, ry + 0.022, z), (0.004, 0.018, 0.03), M_DARK)
        m.box("glass", (0, ry + 0.028, z - 0.008), (0.02, 0.02, 0.002), (0.4, 0.8, 0.5))
        m.sight_y = ry + 0.026
        m.eye_ref_z = z + 0.02
        m.relief = 0.40
    elif aid == "reddot":
        z = rz + 0.02
        m.box("body", (0, ry + 0.008, z), (0.028, 0.014, 0.045), M_DARK)
        m.box("body", (0, ry + 0.020, z), (0.012, 0.016, 0.02), M_DARK)
        m.cyl("body", (0, ry + 0.042, z), 0.019, 0.045, M_DARK, seg=16)
        m.box("body", (0, ry + 0.064, z), (0.012, 0.008, 0.02), M_DARK)
        m.box("body", (0.02, ry + 0.042, z), (0.008, 0.012, 0.014), M_DARK)
        m.box("glass", (0, ry + 0.042, z - 0.01), (0.03, 0.03, 0.002), (0.45, 0.75, 0.6))
        m.sight_y = ry + 0.042
        m.eye_ref_z = z + 0.022
        m.relief = 0.30
        m.lens_r = 0.015
    elif aid == "holo":
        z = rz + 0.03
        m.box("body", (0, ry + 0.01, z), (0.046, 0.018, 0.085), M_DARK)
        m.box("body", (-0.021, ry + 0.042, z - 0.005), (0.006, 0.05, 0.05), M_DARK)
        m.box("body", (0.021, ry + 0.042, z - 0.005), (0.006, 0.05, 0.05), M_DARK)
        m.box("body", (0, ry + 0.07, z - 0.005), (0.048, 0.006, 0.05), M_DARK)
        m.box("body", (0.028, ry + 0.012, z + 0.02), (0.01, 0.012, 0.03), M_STEEL)
        m.box("glass", (0, ry + 0.043, z - 0.02), (0.036, 0.042, 0.002), (0.5, 0.7, 0.8))
        m.sight_y = ry + 0.043
        m.eye_ref_z = z + 0.02
        m.relief = 0.30
    elif aid in ("x3", "x4"):
        z = rz + 0.02
        L = 0.11 if aid == "x3" else 0.14
        m.box("body", (0, ry + 0.01, z), (0.03, 0.016, L * 0.7), M_DARK)
        m.box("body", (0, ry + 0.035, z), (0.036, 0.04, L * 0.55), M_DARK)
        m.cyl("body", (0, ry + 0.045, z - L * 0.42), 0.021, L * 0.35, M_DARK, seg=16)
        m.cyl("body", (0, ry + 0.045, z + L * 0.40), 0.018, L * 0.3, M_DARK, seg=16)
        m.box("body", (0, ry + 0.07, z - 0.01), (0.008, 0.012, 0.05), (0.2, 0.5, 0.2))
        m.box("glass", (0, ry + 0.045, z + L * 0.55), (0.03, 0.03, 0.002), (0.2, 0.3, 0.35))
        m.sight_y = ry + 0.045
        m.eye_ref_z = z + L * 0.55
        m.relief = 0.14
    elif aid in ("x8", "x12"):
        z = rz + 0.0
        L = 0.30 if aid == "x8" else 0.36
        h = ry + 0.048
        for dz in (-0.06, 0.06):
            m.box("body", (0, ry + 0.018, z + dz), (0.03, 0.03, 0.02), M_DARK)
        m.cyl("body", (0, h, z), 0.016, L, M_DARK, seg=16)
        m.cyl("body", (0, h, z - L / 2 - 0.03), 0.028, 0.08, M_DARK, seg=18)
        m.cyl("body", (0, h, z - L / 2 + 0.02), 0.022, 0.03, M_DARK, seg=18)
        m.cyl("body", (0, h, z + L / 2 + 0.02), 0.021, 0.06, M_DARK, seg=18)
        m.cyl("body", (0, h + 0.022, z - 0.01), 0.011, 0.018, M_STEEL, axis="y")
        m.cyl("body", (0.022, h, z - 0.01), 0.011, 0.018, M_STEEL, axis="x")
        m.box("glass", (0, h, z + L / 2 + 0.052), (0.034, 0.034, 0.002), (0.15, 0.2, 0.3))
        m.sight_y = h
        m.eye_ref_z = z + L / 2 + 0.05
        m.relief = 0.12


def _add_muzzle(m: GunModel, aid, bz, by, br, pistol=False):
    """bz: 枪管末端 z; 返回新的枪口 z"""
    if aid == "suppressor":
        L = 0.13 if pistol else 0.17
        r = 0.016 if pistol else 0.02
        m.cyl("body", (0, by, bz - L / 2), r, L, (0.12, 0.12, 0.12), seg=16)
        m.cyl("body", (0, by, bz - L + 0.004), r * 0.9, 0.01, M_DARK, seg=16)
        return bz - L
    if aid == "compensator":
        m.cyl("body", (0, by, bz - 0.03), br * 1.45, 0.06, M_DARK, seg=10)
        m.box("body", (0, by + br * 1.2, bz - 0.03), (0.012, 0.006, 0.04), M_STEEL)
        return bz - 0.06
    if aid == "flashhider":
        m.cyl("body", (0, by, bz - 0.015), br * 1.2, 0.03, M_DARK, seg=10)
        for a in range(3):
            ang = a / 3 * math.pi * 2 + 0.5
            m.box("body", (math.cos(ang) * br, by + math.sin(ang) * br, bz - 0.05), (0.006, 0.006, 0.045), M_DARK)
        return bz - 0.07
    if aid == "brake":
        m.box("body", (0, by, bz - 0.04), (0.042, 0.03, 0.075), M_DARK)
        m.box("body", (0, by, bz - 0.025), (0.044, 0.012, 0.012), (0.03, 0.03, 0.03))
        m.box("body", (0, by, bz - 0.055), (0.044, 0.012, 0.012), (0.03, 0.03, 0.03))
        return bz - 0.08
    if aid == "choke":
        m.cyl("body", (0, by, bz - 0.025), br * 1.25, 0.05, M_STEEL, seg=12)
        return bz - 0.05
    # 标准 / 独头弹
    m.cyl("body", (0, by, bz - 0.02), br * 1.25, 0.04, M_DARK, seg=10)
    return bz - 0.04


def _add_underbarrel(m: GunModel, aid, z, y, pistol=False):
    if aid == "vgrip":
        m.box("body", (0, y - 0.05, z), (0.028, 0.09, 0.03), M_DARK)
        m.grip_l = (0.0, y - 0.07, z)
    elif aid == "agrip":
        m.box("body", (0, y - 0.022, z + 0.02), (0.03, 0.03, 0.09), M_DARK, rx=-18)
        m.grip_l = (-0.005, y - 0.03, z + 0.01)
    elif aid == "laser":
        if pistol:
            m.box("body", (0, y - 0.012, z), (0.024, 0.022, 0.045), M_DARK)
            m.box("body", (0.006, y - 0.012, z - 0.023), (0.008, 0.008, 0.004), (1.0, 0.1, 0.1))
        else:
            m.box("body", (0.03, y, z), (0.018, 0.026, 0.06), M_DARK)
            m.box("body", (0.03, y + 0.005, z - 0.031), (0.008, 0.008, 0.004), (1.0, 0.1, 0.1))
    elif aid == "bipod":
        m.box("body", (0, y - 0.015, z - 0.02), (0.03, 0.02, 0.04), M_DARK)
        for sx in (-0.012, 0.012):
            m.box("body", (sx, y - 0.025, z + 0.08), (0.008, 0.008, 0.2), M_STEEL)


def _mag(m: GunModel, style, x, y, z, color, ext=1.0, drum=False):
    """挂在 mag 组; y/z 为弹匣顶部中心"""
    if drum:
        m.box("mag", (0, y - 0.03, z), (0.026, 0.06, 0.06), color)
        m.cyl("mag", (0, y - 0.11, z + 0.005), 0.065, 0.07, color, axis="x", seg=20)
        m.mag_pos = (0, y - 0.1, z)
        return
    if style in ("stanag", "curved", "ak"):
        curve = {"stanag": 0.012, "curved": 0.03, "ak": 0.045}[style]
        segs = 3
        seg_h = 0.052 * ext
        w = 0.026 if style == "stanag" else 0.028
        d = 0.064 if style == "stanag" else 0.068
        for i in range(segs):
            cy = y - seg_h * (i + 0.5)
            cz = z - curve * (i + 0.5) ** 1.4 / segs * 1.5
            m.box("mag", (0, cy, cz), (w, seg_h + 0.002, d), color, rx=-8 * i * curve / 0.03)
        m.box("mag", (0, y - seg_h * segs - 0.006, z - curve * 2.2), (w + 0.006, 0.012, d + 0.01), _shade(color, 0.7))
        m.mag_pos = (0, y - seg_h * 1.5, z - curve)
    elif style == "pistol":
        L = 0.105 * ext
        m.box("mag", (0, y - L / 2, z), (0.022, L, 0.036), (0.12, 0.12, 0.12), rx=-12)
        m.box("mag", (0, y - L + 0.002, z + L * 0.2), (0.028, 0.014, 0.046), color, rx=-12)
        m.mag_pos = (0, y - L * 0.6, z + 0.01)
    else:
        size = {"box20": (0.03, 0.11, 0.075), "box5": (0.034, 0.05, 0.085), "box10": (0.035, 0.09, 0.09),
                "saiga": (0.04, 0.12, 0.085)}.get(style, (0.03, 0.1, 0.07))
        h = size[1] * ext
        m.box("mag", (0, y - h / 2, z), (size[0], h, size[2]), color)
        m.box("mag", (0, y - h - 0.004, z), (size[0] + 0.004, 0.01, size[2] + 0.006), _shade(color, 0.7))
        m.mag_pos = (0, y - h * 0.5, z)


# ════════════════════ 枪型 ════════════════════
def _build_rifle(m: GunModel, d, atts, sniper=False):
    C = d.model.get("color", (0.15, 0.15, 0.15))
    F = d.model.get("furniture", C)
    B = d.model.get("barrel", 0.36)
    R = d.model.get("receiver", 0.42)
    stock = d.model.get("stock", "m4")
    mstyle = d.model.get("mag", "stanag")
    hg = d.model.get("handguard", "ris")
    thick = d.model.get("thick_barrel", False)
    big = d.id == "m82"

    rz_front = 0.08 - R * 0.68
    # 握把 / 扳机
    m.box("body", (0, -0.062, 0.035), (0.032, 0.1, 0.045), F, rx=18)
    m.box("body", (0, -0.03, -0.012), (0.012, 0.012, 0.06), M_DARK)
    m.box("body", (0, -0.018, -0.002), (0.004, 0.02, 0.006), M_STEEL)
    # 下机匣
    lw = 0.05 if big else 0.042
    m.box("body", (0, -0.004, (0.08 + rz_front) / 2), (lw, 0.056, 0.08 - rz_front), C)
    m.box("body", (0, -0.034, -0.09), (lw - 0.004, 0.018, 0.08), C)
    # 上机匣
    uh = 0.08 if big else 0.05
    m.box("body", (0, 0.022 + uh / 2, (0.085 + rz_front) / 2), (lw + 0.004, uh, 0.085 - rz_front), _shade(C, 1.05))
    ry = 0.022 + uh + 0.004
    m.box("body", (0, ry, (0.08 + rz_front - 0.08) / 2), (0.024, 0.008, 0.08 - rz_front + 0.06), M_RAIL)
    for i in range(int((0.14 - rz_front) / 0.012)):
        m.box("body", (0, ry + 0.005, 0.07 - i * 0.012), (0.026, 0.003, 0.005), M_RAIL)
    m.rail_y = ry + 0.004
    m.rail_z = (0.06 + rz_front) / 2
    m.box("body", (lw / 2 + 0.003, 0.045, -0.05), (0.002, 0.018, 0.06), M_DARK)
    # 拉机柄 (bolt 组)
    if d.model.get("bolt"):
        m.cyl("bolt", (lw / 2 + 0.03, ry - 0.02, 0.04), 0.005, 0.06, M_STEEL, axis="x")
        m.box("bolt", (lw / 2 + 0.06, ry - 0.025, 0.04), (0.018, 0.018, 0.018), M_DARK)
        m.box("bolt", (0, ry - 0.02, 0.02), (lw * 0.6, 0.02, 0.1), M_STEEL)
        m.bolt_pos = (lw / 2 + 0.06, ry - 0.025, 0.04)
    else:
        m.box("bolt", (0, ry - 0.012, 0.09), (0.034, 0.01, 0.02), M_DARK)
        m.box("bolt", (lw / 2 + 0.006, 0.047, -0.04), (0.008, 0.01, 0.016), M_STEEL)
        m.bolt_pos = (lw / 2 + 0.01, 0.047, -0.04)
    # 护木
    HG = min(0.36, B * 0.82) if not sniper else B * 0.55
    hz = rz_front - HG / 2
    by = 0.022 + uh * 0.45
    if hg == "ris":
        m.box("body", (0, by, hz), (0.058, 0.062, HG), F)
        for s in (-1, 1):
            m.box("body", (s * 0.031, by, hz), (0.006, 0.02, HG * 0.95), M_RAIL)
        m.box("body", (0, by + 0.033, hz), (0.022, 0.006, HG), M_RAIL)
        m.box("body", (0, by - 0.033, hz), (0.022, 0.006, HG), M_RAIL)
    elif hg == "ak":
        m.box("body", (0, by - 0.006, hz), (0.05, 0.052, HG), F)
        m.box("body", (0, by + 0.032, hz), (0.03, 0.02, HG * 0.9), _shade(F, 1.2))
        m.box("body", (0, by + 0.045, hz), (0.02, 0.006, HG * 0.9), M_RAIL)
    elif hg == "scar":
        m.box("body", (0, by, hz), (0.05, 0.058, HG), C)
        m.box("body", (0, by + 0.031, hz), (0.022, 0.006, HG), M_RAIL)
        for s in (-1, 1):
            m.box("body", (s * 0.027, by - 0.006, hz), (0.006, 0.02, HG * 0.6), M_RAIL)
    else:  # smooth / 191
        m.box("body", (0, by, hz), (0.054, 0.058, HG), F)
        m.box("body", (0, by - 0.026, hz), (0.046, 0.012, HG * 0.95), _shade(F, 0.85))
        m.box("body", (0, by + 0.031, hz), (0.022, 0.006, HG), M_RAIL)
    if sniper:
        m.box("body", (0, by - 0.01, (0.08 + rz_front - HG) / 2 - 0.02), (0.056, 0.05, HG + 0.12), F)
    # 枪管
    br = 0.016 if (thick or big) else (0.013 if sniper else 0.0115)
    bz0 = rz_front - HG
    bl = B - HG * 0.4
    m.cyl("body", (0, by, bz0 - bl / 2 + 0.02), br, bl + 0.04, M_DARK, seg=12)
    if hg != "ak" and not sniper:
        m.box("body", (0, by + 0.018, bz0 - 0.03), (0.02, 0.028, 0.03), M_DARK)  # 导气箍
    muzzle_z = _add_muzzle(m, atts["muzzle"], bz0 - bl, by, br)
    if d.model.get("brake") and atts["muzzle"] == "muzzle_std":
        m.box("body", (0, by, bz0 - bl - 0.05), (0.06, 0.04, 0.09), M_DARK)
        muzzle_z = bz0 - bl - 0.1
    m.muzzle = (0, by, muzzle_z)
    # 枪托
    sy = 0.03
    if stock == "m4":
        m.cyl("body", (0, sy, 0.19), 0.016, 0.22, M_DARK)
        m.box("body", (0, sy - 0.012, 0.25), (0.042, 0.075, 0.12), F)
        m.box("body", (0, sy - 0.015, 0.315), (0.044, 0.1, 0.018), M_DARK)
    elif stock == "191":
        m.cyl("body", (0, sy, 0.19), 0.017, 0.2, M_DARK)
        m.box("body", (0, sy - 0.01, 0.25), (0.046, 0.08, 0.14), F)
        m.box("body", (0, sy + 0.035, 0.24), (0.04, 0.02, 0.1), _shade(F, 1.1))
        m.box("body", (0, sy - 0.015, 0.325), (0.048, 0.105, 0.02), M_DARK)
    elif stock == "folding":
        m.box("body", (0, sy + 0.02, 0.2), (0.02, 0.014, 0.24), F)
        m.box("body", (0, sy - 0.035, 0.2), (0.02, 0.014, 0.24), F)
        m.box("body", (0, sy - 0.008, 0.315), (0.035, 0.1, 0.022), M_DARK)
    elif stock == "scar":
        m.box("body", (0, sy - 0.005, 0.2), (0.045, 0.07, 0.22), F)
        m.box("body", (0, sy + 0.035, 0.22), (0.035, 0.015, 0.14), _shade(F, 1.15))
        m.box("body", (0, sy - 0.01, 0.315), (0.047, 0.1, 0.02), M_DARK)
    elif stock == "aw":
        m.box("body", (0, sy - 0.005, 0.18), (0.045, 0.05, 0.18), F)
        m.box("body", (0, sy - 0.055, 0.25), (0.042, 0.04, 0.14), F)
        m.box("body", (0, sy + 0.035, 0.24), (0.035, 0.03, 0.12), _shade(F, 1.1))
        m.box("body", (0, sy - 0.02, 0.33), (0.045, 0.13, 0.022), M_DARK)
    elif stock == "barrett":
        m.box("body", (0, sy - 0.0, 0.2), (0.05, 0.08, 0.24), C)
        m.box("body", (0, sy - 0.02, 0.33), (0.05, 0.13, 0.03), M_DARK)
        m.box("body", (0, sy + 0.05, 0.24), (0.03, 0.02, 0.1), M_DARK)
    elif stock == "svd":
        m.box("body", (0, sy + 0.01, 0.2), (0.04, 0.03, 0.22), F)
        m.box("body", (0, sy - 0.06, 0.25), (0.036, 0.03, 0.16), F)
        m.box("body", (0, sy - 0.03, 0.14), (0.036, 0.09, 0.03), F)
        m.box("body", (0, sy - 0.02, 0.32), (0.04, 0.12, 0.03), F)
    else:
        m.box("body", (0, sy - 0.01, 0.2), (0.042, 0.08, 0.24), F)
        m.box("body", (0, sy - 0.015, 0.325), (0.046, 0.1, 0.02), M_DARK)
    # 弹匣
    ext = 1.35 if atts["magazine"] == "mag_ext" else (0.85 if atts["magazine"] == "mag_fast" else 1.0)
    drum = atts["magazine"] == "mag_drum"
    magc = (0.14, 0.13, 0.11) if mstyle != "curved" else _shade(C, 1.1)
    if mstyle == "ak":
        magc = (0.15, 0.12, 0.10)
    _mag(m, mstyle, 0, -0.04, -0.09, magc, ext, drum)
    # 配件
    front_z = rz_front - HG + 0.02
    _add_optic(m, atts["optic"], front_z)
    _add_underbarrel(m, atts["underbarrel"], rz_front - HG * 0.55, by - 0.035)
    m.grip_r = (0.0, -0.045, 0.03)
    if atts["underbarrel"] not in ("vgrip", "agrip"):
        m.grip_l = (0.0, by - 0.04, rz_front - HG * 0.45)
    m.length = 0.33 - muzzle_z


def _build_bullpup(m: GunModel, d, atts):
    C = d.model.get("color", (0.2, 0.2, 0.17))
    F = d.model.get("furniture", C)
    B = d.model.get("barrel", 0.3)
    mstyle = d.model.get("mag", "curved")
    # 握把 (前), 扳机护圈
    m.box("body", (0, -0.062, 0.02), (0.032, 0.1, 0.045), F, rx=12)
    m.box("body", (0, -0.03, -0.03), (0.034, 0.012, 0.1), C)
    # 主体
    m.box("body", (0, 0.015, 0.06), (0.056, 0.085, 0.5), C)
    m.box("body", (0, -0.035, 0.22), (0.052, 0.04, 0.18), C)
    m.box("body", (0, 0.01, -0.17), (0.052, 0.07, 0.12), _shade(C, 0.95))
    m.box("body", (0, 0.0, 0.32), (0.058, 0.13, 0.03), M_DARK)
    # 提把 / 导轨
    m.box("body", (0, 0.078, 0.05), (0.034, 0.04, 0.26), _shade(C, 1.1))
    m.box("body", (0, 0.1, 0.04), (0.024, 0.008, 0.28), M_RAIL)
    for i in range(20):
        m.box("body", (0, 0.105, 0.17 - i * 0.013), (0.026, 0.003, 0.005), M_RAIL)
    m.rail_y = 0.104
    m.rail_z = 0.04
    # 拉机柄
    m.box("bolt", (0, 0.05, -0.02), (0.02, 0.012, 0.03), M_DARK)
    m.bolt_pos = (0.0, 0.055, -0.02)
    # 枪管
    by = 0.02
    m.cyl("body", (0, by, -0.23 - B / 2), 0.012, B, M_DARK)
    m.box("body", (0, by + 0.02, -0.25), (0.018, 0.02, 0.05), M_DARK)
    muzzle_z = _add_muzzle(m, atts["muzzle"], -0.23 - B, by, 0.012)
    m.muzzle = (0, by, muzzle_z)
    # 弹匣 (握把后方)
    ext = 1.35 if atts["magazine"] == "mag_ext" else (0.85 if atts["magazine"] == "mag_fast" else 1.0)
    _mag(m, mstyle, 0, -0.03, 0.11, _shade(C, 1.15), ext, atts["magazine"] == "mag_drum")
    _add_optic(m, atts["optic"], -0.08)
    if atts["optic"] == "iron":
        m.sight_y = 0.118
        m.eye_ref_z = 0.16
        m.relief = 0.24
    _add_underbarrel(m, atts["underbarrel"], -0.17, -0.03)
    m.grip_r = (0.0, -0.045, 0.02)
    if atts["underbarrel"] not in ("vgrip", "agrip"):
        m.grip_l = (0.0, -0.025, -0.17)
    m.length = 0.34 - muzzle_z


def _build_pistol(m: GunModel, d, atts):
    C = d.model.get("color", (0.12, 0.12, 0.12))
    SL = d.model.get("slide", (0.15, 0.15, 0.15))
    L = d.model.get("length", 0.19)
    big = d.model.get("big", False)
    k = 1.2 if big else 1.0
    # 握把 + 框架
    m.box("body", (0, -0.05, 0.012), (0.03 * k, 0.1, 0.046 * k), C, rx=-14)
    m.box("body", (0, -0.002, -L * 0.35), (0.028 * k, 0.026, L * 0.75), C)
    m.box("body", (0, -0.026, -0.03), (0.008, 0.02, 0.05), C)
    m.box("body", (0, -0.018, -0.02), (0.004, 0.018, 0.006), M_STEEL)
    # 套筒 (slide 组)
    sh = 0.034 * k
    m.box("slide", (0, 0.027, -L * 0.42 + 0.02), (0.027 * k, sh, L), SL)
    m.box("slide", (0.014 * k, 0.03, -0.015), (0.002, 0.012, 0.035), M_DARK)
    for i in range(5):
        m.box("slide", (0, 0.027, 0.06 - i * 0.008), (0.029 * k, sh * 0.8, 0.003), _shade(SL, 0.6))
    front = -L * 0.42 + 0.02 - L / 2
    if big:
        m.box("slide", (0, 0.027 + sh / 2 + 0.004, -L * 0.42 + 0.02), (0.012, 0.008, L), _shade(SL, 1.1))
    ry = 0.027 + sh / 2 + (0.008 if big else 0.0)
    m.rail_y = ry
    m.rail_z = 0.0
    # 机瞄
    m.box("slide", (0, ry + 0.005, 0.05), (0.02, 0.01, 0.008), M_DARK)
    m.box("slide", (0, ry + 0.005, front + 0.012), (0.004, 0.01, 0.006), M_DARK)
    m.sight_y = ry + 0.008
    m.eye_ref_z = 0.05
    m.relief = 0.40
    # 枪管
    by = 0.027
    m.cyl("body", (0, by, front + 0.005), 0.008 * k, 0.02, M_DARK)
    bz = front
    if d.model.get("comp") and atts["muzzle"] == "muzzle_std":
        m.box("body", (0, by, front - 0.02), (0.028, sh, 0.04), SL)
        bz = front - 0.04
    muzzle_z = bz if atts["muzzle"] == "muzzle_std" else _add_muzzle(m, atts["muzzle"], front, by, 0.009, pistol=True)
    m.muzzle = (0, by, muzzle_z)
    # 弹匣
    ext = 1.5 if (d.model.get("long_mag") or atts["magazine"] == "mag_ext") else 1.0
    _mag(m, "pistol", 0, -0.008, 0.01, (0.1, 0.1, 0.1), ext)
    if atts["optic"] == "rmr":
        # RMR 安装在套筒 → 放进 slide 组以跟随后坐
        before = len(m.parts["body"])
        gbefore = len(m.parts["glass"])
        _add_optic(m, "rmr", 0, pistol=True)
        moved = m.parts["body"][before:]
        m.parts["body"] = m.parts["body"][:before]
        m.parts["slide"].extend(moved)
    _add_underbarrel(m, atts["underbarrel"], -L * 0.55, -0.01, pistol=True)
    m.grip_r = (0.0, -0.045, 0.018)
    m.grip_l = (-0.012, -0.055, 0.008)
    m.bolt_pos = (0.0, 0.03, 0.04)
    m.length = 0.1 - muzzle_z


def _build_shotgun(m: GunModel, d, atts):
    C = d.model.get("color", (0.1, 0.1, 0.1))
    F = d.model.get("furniture", C)
    B = d.model.get("barrel", 0.46)
    R = d.model.get("receiver", 0.24)
    stock = d.model.get("stock", "m4")
    m.box("body", (0, -0.06, 0.035), (0.032, 0.1, 0.045), F, rx=18)
    m.box("body", (0, -0.03, -0.012), (0.012, 0.012, 0.06), M_DARK)
    m.box("body", (0, 0.02, 0.04 - R / 2), (0.046, 0.075, R), C)
    m.box("body", (0.024, 0.03, -0.05), (0.002, 0.025, 0.07), M_DARK)
    ry = 0.058
    m.box("body", (0, ry, 0.04 - R / 2), (0.022, 0.006, R * 0.9), M_RAIL)
    m.rail_y = ry + 0.003
    m.rail_z = 0.04 - R / 2
    # 枪管 + 管式弹仓
    bz0 = 0.04 - R
    by = 0.04
    m.cyl("body", (0, by, bz0 - B / 2), 0.014, B, M_DARK, seg=14)
    m.cyl("body", (0, by - 0.028, bz0 - B * 0.42), 0.013, B * 0.84, _shade(C, 1.1), seg=12)
    m.box("body", (0, by - 0.014, bz0 - B * 0.84), (0.012, 0.03, 0.02), M_DARK)
    if d.model.get("heatshield"):
        m.box("body", (0, by + 0.012, bz0 - B * 0.35), (0.03, 0.02, B * 0.5), (0.2, 0.2, 0.2))
    # 泵动护木
    pz = bz0 - B * 0.36
    m.box("pump", (0, by - 0.028, pz), (0.052, 0.045, 0.15), F)
    for i in range(6):
        m.box("pump", (0, by - 0.028, pz - 0.06 + i * 0.024), (0.054, 0.047, 0.006), _shade(F, 0.7))
    m.pump_pos = (0, by - 0.045, pz)
    muzzle_z = _add_muzzle(m, atts["muzzle"], bz0 - B, by, 0.014)
    m.muzzle = (0, by, muzzle_z)
    # 枪托
    if stock == "folding":
        m.box("body", (0, 0.06, 0.18), (0.016, 0.012, 0.26), M_STEEL)
        m.box("body", (0, 0.02, 0.31), (0.03, 0.09, 0.02), M_DARK)
    elif stock == "fixed":
        m.box("body", (0, 0.01, 0.2), (0.04, 0.08, 0.28), F)
        m.box("body", (0, 0.0, 0.34), (0.046, 0.11, 0.02), M_DARK)
    else:
        m.cyl("body", (0, 0.03, 0.19), 0.016, 0.22, M_DARK)
        m.box("body", (0, 0.018, 0.25), (0.042, 0.075, 0.12), F)
        m.box("body", (0, 0.015, 0.315), (0.044, 0.1, 0.018), M_DARK)
    # 霰弹: 珠形准星
    if atts["optic"] == "iron":
        m.box("body", (0, by + 0.018, bz0 - B + 0.02), (0.005, 0.008, 0.005), (0.9, 0.9, 0.9))
        m.box("body", (0, ry + 0.01, 0.0), (0.02, 0.012, 0.012), M_DARK)
        m.sight_y = ry + 0.012
        m.eye_ref_z = 0.0
        m.relief = 0.28
    else:
        _add_optic(m, atts["optic"], bz0 - B + 0.02)
    _add_underbarrel(m, atts["underbarrel"], pz, by - 0.06)
    m.grip_r = (0.0, -0.045, 0.03)
    m.grip_l = (0.0, by - 0.055, pz)
    m.length = 0.33 - muzzle_z


def _upload_texture(path):
    import pygame
    from .gl_util import make_texture
    surf = pygame.image.load(path).convert_alpha()
    w, h = surf.get_size()
    raw = pygame.image.tostring(surf, "RGBA", True)  # 翻转到 OpenGL 底部为 v=0
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4).copy()
    return make_texture(arr, mipmap=True, repeat=False)


# 眼点到枪口的目标距离 (米)。上游模型按方块单位烘焙后往往偏长,
# 连同瞄具锚点一起缩放, 第一人称张角不变, 但程序化配件能按真实尺寸接上。
_EYE_TO_MUZZLE = {"pistol": 0.42, "shotgun": 0.82, "sniper": 1.05, "bullpup": 0.66, "rifle": 0.72}


def _scale_baked(baked, k):
    if abs(k - 1.0) < 0.03:
        return
    from .bedrock_geo import Quad
    for g, qs in list(baked.groups.items()):
        baked.groups[g] = [
            Quad(tuple(tuple(c * k for c in v) for v in q.verts), q.uvs, q.normal, q.alpha, q.emissive)
            for q in qs
        ]
    baked.anchors = {n: tuple(c * k for c in p) for n, p in baked.anchors.items()}
    baked.bounds_min = tuple(c * k for c in baked.bounds_min)
    baked.bounds_max = tuple(c * k for c in baked.bounds_max)


def _fit_scale(kind, iron, muzzle):
    if not iron or not muzzle:
        return 1.0
    dist = abs(iron[2] - muzzle[2])
    if dist < 0.08:
        return 1.0
    target = _EYE_TO_MUZZLE.get(kind, 0.72)
    return max(0.2, min(1.8, target / dist))


def _estimate_grips(kind, anchors):
    """手部骨骼在绑定姿势里只是占位, 不能当握把。

    右手放在握把 (常规步枪在弹匣后方, 无托在弹匣前方)。左手优先用泵动护木,
    其次用模型自带的 grip_pos (前握把安装点), 最后才按护木中段估算。
    """
    mag = anchors.get("mag")
    muzzle = anchors.get("muzzle") or (0.0, 0.04, -0.35)
    pump = anchors.get("pump")
    grip = anchors.get("grip")
    if kind == "pistol":
        z = mag[2] if mag else 0.01
        y = mag[1] if mag else -0.03
        return (0.0, y + 0.02, z + 0.01), (-0.016, y + 0.01, z - 0.02)
    if mag:
        toward_stock = -1.0 if kind == "bullpup" else 1.0
        grip_r = (0.0, mag[1] - 0.01, mag[2] + toward_stock * 0.07)
    else:
        grip_r = (0.0, muzzle[1] - 0.06, muzzle[2] * 0.15)
    if kind == "shotgun" and pump:
        grip_l = pump
    elif grip and (mag is None or grip[2] < mag[2] - 0.02):
        grip_l = grip
    else:
        z0 = mag[2] if mag else 0.0
        grip_l = (0.0, muzzle[1] - 0.03, z0 + (muzzle[2] - z0) * 0.42)
    return grip_r, grip_l


def _apply_external(m: GunModel, baked, d, atts):
    """把烘焙好的 TACZ / SuperbWarfare 网格挂到 GunModel, 并叠上游戏内配件。"""
    from .gun_packs import PACKS
    m.kind = d.model.get("kind", "rifle")
    k = _fit_scale(m.kind, baked.anchors.get("iron"), baked.anchors.get("muzzle"))
    _scale_baked(baked, k)
    m.textured = True
    m.mesh = baked.groups
    m.pack = baked.pack
    m.model_scale = k
    info = PACKS.get(baked.pack, {})
    m.pack_label = "%s · %s" % (info.get("label", baked.pack), baked.model_name)
    m.source_credit = info.get("credit", "")
    tex_path = getattr(baked, "tex_path", None)
    if tex_path:
        try:
            m.tex_id = _upload_texture(tex_path)
        except Exception as e:
            print("[gunpacks] 贴图上传失败 %s: %s" % (tex_path, e))
            m.tex_id = None
    iron = baked.anchors.get("iron")
    idle = baked.anchors.get("idle")
    muzzle = baked.anchors.get("muzzle")
    scope = baked.anchors.get("scope")
    if iron:
        m.sight_x, m.sight_y, m.eye_ref_z = iron
        m.relief = 0.045
    if idle:
        m.hip_pos = (-idle[0], -idle[1], -idle[2])
    if muzzle:
        m.muzzle = muzzle
    else:
        m.muzzle = (0.0, float(baked.center[1]), float(baked.bounds_min[2]))
    if scope:
        m.rail_y, m.rail_z = scope[1], scope[2]
    elif iron:
        m.rail_y = iron[1] - 0.015
        m.rail_z = iron[2] - 0.06
    m.grip_r, m.grip_l = _estimate_grips(m.kind, baked.anchors)
    m.mag_pos = baked.anchors.get("mag", (0.0, -0.08, -0.02))
    m.bolt_pos = baked.anchors.get("bolt", (0.04, m.rail_y, 0.02))
    m.pump_pos = baked.anchors.get("pump", m.grip_l)
    span = baked.span
    m.length = max(0.28, span[0], span[2])
    m.preview_center = baked.center
    m.preview_span = max(span[0], span[1], span[2], 0.3)
    pistol = m.kind == "pistol"
    # 模型自带机械瞄具; 只有换上游戏配件时才叠程序化零件
    if atts.get("optic", "iron") != "iron":
        before = len(m.parts["body"])
        _add_optic(m, atts["optic"], m.muzzle[2] + 0.04, pistol=pistol)
        if pistol and atts.get("optic") == "rmr":
            moved = m.parts["body"][before:]
            m.parts["body"] = m.parts["body"][:before]
            m.parts["slide"].extend(moved)
        m.sight_x = 0.0
    if atts.get("muzzle", "muzzle_std") not in ("muzzle_std", None):
        mz = _add_muzzle(m, atts["muzzle"], m.muzzle[2], m.muzzle[1], 0.012, pistol=pistol)
        m.muzzle = (m.muzzle[0], m.muzzle[1], mz)
    ub = atts.get("underbarrel", "ub_none")
    if ub not in ("ub_none", None):
        z = (m.muzzle[2] + m.grip_r[2]) * 0.45
        _add_underbarrel(m, ub, z, m.muzzle[1] - 0.03, pistol=pistol)
    return m


def build_gun_model(wid, atts) -> GunModel:
    d = WEAPONS[wid]
    try:
        from .gun_packs import load_baked
        baked = load_baked(wid, atts, kind=d.model.get("kind", "rifle"))
    except Exception as e:
        print("[gunpacks] %s 加载失败, 使用程序化模型: %s" % (wid, e))
        baked = None
    if baked is not None and baked.quad_count >= 8:
        m = GunModel()
        _apply_external(m, baked, d, atts)
        span = max(getattr(m, "preview_span", 0.0), m.length)
        if 0.12 <= span <= 2.4:
            m.compile()
            return m
        print("[gunpacks] %s 尺寸异常 (%.2fm), 回退程序化模型" % (wid, span))
    m = GunModel()
    kind = d.model.get("kind", "rifle")
    m.kind = kind
    if kind == "pistol":
        _build_pistol(m, d, atts)
    elif kind == "bullpup":
        _build_bullpup(m, d, atts)
    elif kind == "shotgun":
        _build_shotgun(m, d, atts)
    else:
        _build_rifle(m, d, atts, sniper=(kind == "sniper"))
    m.compile()
    return m


class GunModelCache:
    def __init__(self):
        self.cache = {}
        try:
            from .gun_packs import prefetch_async
            prefetch_async()
        except Exception:
            pass

    def get(self, wid, atts) -> GunModel:
        key = (wid, tuple(sorted(atts.items())))
        m = self.cache.get(key)
        if m is None:
            if len(self.cache) > 60:
                for k in list(self.cache)[:20]:
                    self.cache.pop(k).delete()
            m = build_gun_model(wid, atts)
            self.cache[key] = m
        return m


def draw_shell(x, y, z, shotgun=True):
    if shotgun:
        draw_cylinder(x, y, z, 0.0095, 0.05, RED_SHELL, axis="z", segments=8)
        draw_cylinder(x, y, z + 0.022, 0.01, 0.012, BRASS, axis="z", segments=8)
    else:
        draw_cylinder(x, y, z, 0.005, 0.03, BRASS, axis="z", segments=6)
