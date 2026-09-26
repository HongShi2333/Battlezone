"""OpenGL 工具: 程序化纹理 / 文字纹理缓存 / 基础几何 / 2D 绘制"""
import math
import os
import numpy as np
import pygame
from OpenGL.GL import *


# ════════════════════ 投影 (不依赖 GLU) ════════════════════
def perspective(fov_y, aspect, near, far):
    top = near * math.tan(math.radians(fov_y) / 2)
    glFrustum(-top * aspect, top * aspect, -top, top, near, far)


# ════════════════════ 纹理 ════════════════════
def make_texture(rgb_array, mipmap=True, repeat=True):
    """rgb_array: HxWx3 或 HxWx4 uint8"""
    h, w = rgb_array.shape[:2]
    fmt = GL_RGBA if rgb_array.shape[2] == 4 else GL_RGB
    tid = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tid)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    wrap = GL_REPEAT if repeat else GL_CLAMP_TO_EDGE
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wrap)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    data = np.ascontiguousarray(rgb_array, dtype=np.uint8)
    if mipmap:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_GENERATE_MIPMAP, GL_TRUE)
        glTexImage2D(GL_TEXTURE_2D, 0, fmt, w, h, 0, fmt, GL_UNSIGNED_BYTE, data)
    else:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, fmt, w, h, 0, fmt, GL_UNSIGNED_BYTE, data)
    return tid


def _noise(size, octaves=5, seed=0):
    rng = np.random.default_rng(seed)
    out = np.zeros((size, size), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        n = max(2, 4 * 2 ** o)
        base = rng.random((n, n)).astype(np.float32)
        # 可平铺的双线性放大
        idx = np.arange(size) * n / size
        i0 = np.floor(idx).astype(int) % n
        i1 = (i0 + 1) % n
        f = idx - np.floor(idx)
        f = f * f * (3 - 2 * f)
        rows = base[i0][:, i0] * (1 - f)[None, :] + base[i0][:, i1] * f[None, :]
        rows2 = base[i1][:, i0] * (1 - f)[None, :] + base[i1][:, i1] * f[None, :]
        layer = rows * (1 - f)[:, None] + rows2 * f[:, None]
        out += layer * amp
        total += amp
        amp *= 0.5
    return out / total


def _to_rgb(gray, tint=(1, 1, 1)):
    g = np.clip(gray, 0, 1)
    return (np.stack([g * tint[0], g * tint[1], g * tint[2]], -1) * 255).astype(np.uint8)


def generate_textures():
    init_unit_cube()
    S = 256
    tex = {}
    n1 = _noise(S, 6, 1)
    n2 = _noise(S, 4, 2)
    fine = np.random.default_rng(3).random((S, S)).astype(np.float32)

    # 混凝土
    g = 0.62 + (n1 - 0.5) * 0.35 + (fine - 0.5) * 0.08
    yy, xx = np.mgrid[0:S, 0:S]
    g[(yy % 128) < 2] *= 0.8          # 浇筑缝
    tex["concrete"] = make_texture(_to_rgb(g))
    # 沥青地面
    g = 0.45 + (n1 - 0.5) * 0.25 + (fine - 0.5) * 0.18
    crack = np.abs(_noise(S, 5, 9) - 0.5) < 0.008
    g[crack] *= 0.55
    tex["asphalt"] = make_texture(_to_rgb(g))
    # 集装箱波纹
    ridge = 0.5 + 0.5 * np.sin(xx / S * math.pi * 2 * 16)
    g = 0.72 + ridge * 0.22 + (n2 - 0.5) * 0.18 + (fine - 0.5) * 0.05
    rust = _noise(S, 5, 7)
    g = g * (1 - np.clip((rust - 0.62) * 3, 0, 0.35))
    g[(yy % 256) < 6] *= 0.7
    tex["container"] = make_texture(_to_rgb(g))
    # 木箱
    plank = ((yy // 32) % 2) * 0.06
    grain = _noise(S, 5, 11)
    g = 0.62 + plank + (np.sin(xx * 0.05 + grain * 12) * 0.06) + (fine - 0.5) * 0.06
    g[(yy % 32) < 2] *= 0.55
    border = (xx < 16) | (xx > S - 16) | (yy < 16) | (yy > S - 16)
    g[border] *= 0.78
    diag = np.abs(xx - yy) < 10
    g[diag] *= 0.8
    rgb = _to_rgb(g, (1.0, 0.78, 0.52))
    tex["crate"] = make_texture(rgb)
    # 金属
    g = 0.6 + (np.random.default_rng(5).random((S, 1)).astype(np.float32) - 0.5) * 0.12 + (n2 - 0.5) * 0.15
    g = np.broadcast_to(g, (S, S)).copy()
    for cx in (16, S - 16):
        for cy in range(16, S, 48):
            m = (xx - cx) ** 2 + (yy - cy) ** 2 < 20
            g[m] = 0.85
    tex["metal"] = make_texture(_to_rgb(g))
    # 沙袋
    cell_y = (yy % 48) / 48.0
    off = ((yy // 48) % 2) * 32
    cell_x = ((xx + off) % 64) / 64.0
    bump = np.sin(cell_y * math.pi) * np.sin(cell_x * math.pi)
    g = 0.45 + bump * 0.35 + (fine - 0.5) * 0.12
    tex["sandbag"] = make_texture(_to_rgb(g, (1.0, 0.92, 0.72)))
    # 墙面 (灰泥)
    g = 0.78 + (n1 - 0.5) * 0.2 + (fine - 0.5) * 0.05
    tex["plaster"] = make_texture(_to_rgb(g))
    # 平整 (无纹理)
    tex["flat"] = make_texture(np.full((4, 4, 3), 255, np.uint8), mipmap=False)
    # 条纹 (隔离墩 / 护栏)
    stripe = ((xx + yy) // 32) % 2
    g = 0.8 + (fine - 0.5) * 0.06
    rgb = _to_rgb(g)
    rgb[stripe == 1] = (rgb[stripe == 1] * np.array([1.0, 0.75, 0.2])).astype(np.uint8)
    tex["stripe"] = make_texture(rgb)
    # 粒子 / 光晕 (RGBA)
    r = np.sqrt((xx - S / 2) ** 2 + (yy - S / 2) ** 2) / (S / 2)
    a = np.clip(1 - r, 0, 1) ** 2
    glow = np.dstack([np.full((S, S), 255), np.full((S, S), 255), np.full((S, S), 255), a * 255]).astype(np.uint8)
    tex["glow"] = make_texture(glow, mipmap=False, repeat=False)
    # 枪口火焰星形
    ang = np.arctan2(yy - S / 2, xx - S / 2)
    star = np.clip(1 - r / (0.35 + 0.65 * np.abs(np.cos(ang * 3)) ** 6), 0, 1) ** 1.5
    fl = np.dstack([np.full((S, S), 255), np.full((S, S), 230), np.full((S, S), 170), star * 255]).astype(np.uint8)
    tex["flash"] = make_texture(fl, mipmap=False, repeat=False)
    # 烟雾
    sm = np.clip(1 - r, 0, 1) ** 1.2 * (0.5 + 0.5 * _noise(S, 4, 13))
    smoke = np.dstack([np.full((S, S), 200), np.full((S, S), 195), np.full((S, S), 185), sm * 255]).astype(np.uint8)
    tex["smoke"] = make_texture(smoke, mipmap=False, repeat=False)
    # 弹孔
    hole = np.zeros((64, 64, 4), np.uint8)
    y2, x2 = np.mgrid[0:64, 0:64]
    rr = np.sqrt((x2 - 32) ** 2 + (y2 - 32) ** 2)
    hole[..., 3] = (np.clip(1 - rr / 30, 0, 1) ** 0.7 * 220).astype(np.uint8)
    hole[..., :3] = np.where(rr[..., None] < 6, 10, 40).astype(np.uint8)
    tex["hole"] = make_texture(hole, mipmap=False, repeat=False)
    return tex


# ════════════════════ 文字 ════════════════════
_CJK_CANDIDATES = [
    "microsoftyahei", "microsoftyaheiui", "msyh", "simhei", "dengxian", "pingfangsc", "pingfang",
    "hiraginosansgb", "notosanscjksc", "notosanscjk", "notosanssc", "sourcehansanssc", "wenquanyimicrohei",
    "wqymicrohei", "wenquanyizenhei", "arialunicode",
]
_CJK_PATHS = [
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
]


def find_cjk_font():
    for p in _CJK_PATHS:
        if os.path.exists(p):
            return p
    for name in _CJK_CANDIDATES:
        path = pygame.font.match_font(name)
        if path:
            return path
    return None


class TextRenderer:
    """把文字渲染成纹理并缓存 — 同一字符串只光栅化一次"""

    def __init__(self):
        self.font_path = find_cjk_font()
        self.fonts = {}
        self.cache = {}

    def font(self, size, bold=False):
        key = (size, bold)
        f = self.fonts.get(key)
        if f is None:
            f = pygame.font.Font(self.font_path, size) if self.font_path else pygame.font.SysFont(None, size)
            f.set_bold(bold)
            self.fonts[key] = f
        return f

    def get(self, text, size=18, color=(255, 255, 255), bold=False):
        key = (text, size, color, bold)
        e = self.cache.get(key)
        if e is None:
            if len(self.cache) > 900:
                for k, (tid, _, _) in list(self.cache.items())[:300]:
                    glDeleteTextures([tid])
                    del self.cache[k]
            surf = self.font(size, bold).render(text, True, color[:3])
            w, h = surf.get_size()
            w, h = max(w, 1), max(h, 1)
            data = pygame.image.tostring(surf, "RGBA", False)
            tid = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tid)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
            e = (tid, w, h)
            self.cache[key] = e
        return e

    def size(self, text, size=18, bold=False):
        _, w, h = self.get(text, size, (255, 255, 255), bold)
        return w, h

    def draw(self, text, x, y, size=18, color=(255, 255, 255), alpha=1.0, align="left", bold=False,
             shadow=True, valign="top"):
        if not text:
            return 0
        c = tuple(int(v) for v in color[:3])
        tid, w, h = self.get(text, size, c, bold)
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        if valign == "middle":
            y -= h / 2
        elif valign == "bottom":
            y -= h
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tid)
        if shadow:
            glColor4f(0, 0, 0, alpha * 0.6)
            _quad(x + 1.5, y + 1.5, w, h)
        glColor4f(1, 1, 1, alpha)
        _quad(x, y, w, h)
        glDisable(GL_TEXTURE_2D)
        return w


def _quad(x, y, w, h):
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex2f(x, y)
    glTexCoord2f(1, 0); glVertex2f(x + w, y)
    glTexCoord2f(1, 1); glVertex2f(x + w, y + h)
    glTexCoord2f(0, 1); glVertex2f(x, y + h)
    glEnd()


# ════════════════════ 2D 绘制 ════════════════════
def begin_2d(w, h):
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    glOrtho(0, w, h, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glDisable(GL_FOG)
    glDisable(GL_CULL_FACE)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


def end_2d():
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glPopMatrix()
    glEnable(GL_DEPTH_TEST)


def rect(x, y, w, h, color, alpha=1.0):
    glColor4f(color[0], color[1], color[2], alpha)
    glBegin(GL_QUADS)
    glVertex2f(x, y); glVertex2f(x + w, y); glVertex2f(x + w, y + h); glVertex2f(x, y + h)
    glEnd()


def rect_grad(x, y, w, h, c0, c1, a0=1.0, a1=1.0, horizontal=False):
    glBegin(GL_QUADS)
    if horizontal:
        glColor4f(*c0[:3], a0); glVertex2f(x, y)
        glColor4f(*c1[:3], a1); glVertex2f(x + w, y); glVertex2f(x + w, y + h)
        glColor4f(*c0[:3], a0); glVertex2f(x, y + h)
    else:
        glColor4f(*c0[:3], a0); glVertex2f(x, y); glVertex2f(x + w, y)
        glColor4f(*c1[:3], a1); glVertex2f(x + w, y + h); glVertex2f(x, y + h)
    glEnd()


def rect_outline(x, y, w, h, color, alpha=1.0, width=1.0):
    glLineWidth(width)
    glColor4f(color[0], color[1], color[2], alpha)
    glBegin(GL_LINE_LOOP)
    glVertex2f(x, y); glVertex2f(x + w, y); glVertex2f(x + w, y + h); glVertex2f(x, y + h)
    glEnd()


def line(x0, y0, x1, y1, color, alpha=1.0, width=1.0):
    glLineWidth(width)
    glColor4f(color[0], color[1], color[2], alpha)
    glBegin(GL_LINES)
    glVertex2f(x0, y0); glVertex2f(x1, y1)
    glEnd()


def circle(x, y, r, color, alpha=1.0, segments=32, filled=True, width=1.0):
    glColor4f(color[0], color[1], color[2], alpha)
    if filled:
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(x, y)
    else:
        glLineWidth(width)
        glBegin(GL_LINE_LOOP)
    for i in range(segments + (1 if filled else 0)):
        a = i / segments * math.pi * 2
        glVertex2f(x + math.cos(a) * r, y + math.sin(a) * r)
    glEnd()


def arc(x, y, r, a0, a1, color, alpha=1.0, width=3.0, segments=16):
    glLineWidth(width)
    glColor4f(color[0], color[1], color[2], alpha)
    glBegin(GL_LINE_STRIP)
    for i in range(segments + 1):
        a = a0 + (a1 - a0) * i / segments
        glVertex2f(x + math.cos(a) * r, y + math.sin(a) * r)
    glEnd()


def textured_rect(tid, x, y, w, h, color=(1, 1, 1), alpha=1.0):
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tid)
    glColor4f(color[0], color[1], color[2], alpha)
    _quad(x, y, w, h)
    glDisable(GL_TEXTURE_2D)


# ════════════════════ 3D 几何 ════════════════════
_FACES = (
    ((1, 0, 0), ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1))),
    ((-1, 0, 0), ((-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, -1, -1))),
    ((0, 1, 0), ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1))),
    ((0, -1, 0), ((-1, -1, 1), (-1, -1, -1), (1, -1, -1), (1, -1, 1))),
    ((0, 0, 1), ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))),
    ((0, 0, -1), ((1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1))),
)


def emit_box(cx, cy, cz, sx, sy, sz, color=None):
    """在 glBegin(GL_QUADS) 内部调用: 带法线的盒子"""
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    if color is not None:
        glColor3f(*color)
    for n, verts in _FACES:
        glNormal3f(*n)
        for vx, vy, vz in verts:
            glVertex3f(cx + vx * hx, cy + vy * hy, cz + vz * hz)


_UNIT_CUBE = None


def init_unit_cube():
    """必须在任何 glNewList 编译之前调用 (显示列表不可嵌套创建)"""
    global _UNIT_CUBE
    if _UNIT_CUBE is None:
        _UNIT_CUBE = glGenLists(1)
        glNewList(_UNIT_CUBE, GL_COMPILE)
        glBegin(GL_QUADS)
        emit_box(0, 0, 0, 1, 1, 1)
        glEnd()
        glEndList()


def draw_box(cx, cy, cz, sx, sy, sz, color=None):
    """使用缓存的单位立方体显示列表 (比逐顶点提交快约 10 倍); 需开启 GL_NORMALIZE 以校正光照"""
    if _UNIT_CUBE is None:
        init_unit_cube()
    if color is not None:
        glColor3f(*color)
    glPushMatrix()
    glTranslatef(cx, cy, cz)
    glScalef(sx, sy, sz)
    glCallList(_UNIT_CUBE)
    glPopMatrix()


def draw_cylinder(cx, cy, cz, radius, length, color=None, axis="z", segments=12, caps=True):
    """沿轴向的圆柱, 中心在 (cx,cy,cz)"""
    if color is not None:
        glColor3f(*color)
    h = length / 2
    glBegin(GL_QUAD_STRIP)
    for i in range(segments + 1):
        a = i / segments * math.pi * 2
        c, s = math.cos(a), math.sin(a)
        if axis == "z":
            glNormal3f(c, s, 0)
            glVertex3f(cx + c * radius, cy + s * radius, cz + h)
            glVertex3f(cx + c * radius, cy + s * radius, cz - h)
        elif axis == "y":
            glNormal3f(c, 0, s)
            glVertex3f(cx + c * radius, cy - h, cz + s * radius)
            glVertex3f(cx + c * radius, cy + h, cz + s * radius)
        else:
            glNormal3f(0, c, s)
            glVertex3f(cx + h, cy + c * radius, cz + s * radius)
            glVertex3f(cx - h, cy + c * radius, cz + s * radius)
    glEnd()
    if caps:
        for side in (-1, 1):
            glBegin(GL_TRIANGLE_FAN)
            if axis == "z":
                glNormal3f(0, 0, side)
                glVertex3f(cx, cy, cz + h * side)
            elif axis == "y":
                glNormal3f(0, side, 0)
                glVertex3f(cx, cy + h * side, cz)
            else:
                glNormal3f(side, 0, 0)
                glVertex3f(cx + h * side, cy, cz)
            direction = -side if axis == "y" else side
            for i in range(segments + 1):
                a = i / segments * math.pi * 2 * direction
                c, s = math.cos(a), math.sin(a)
                if axis == "z":
                    glVertex3f(cx + c * radius, cy + s * radius, cz + h * side)
                elif axis == "y":
                    glVertex3f(cx + c * radius, cy + h * side, cz + s * radius)
                else:
                    glVertex3f(cx + h * side, cy + c * radius, cz + s * radius)
            glEnd()


def draw_limb(p0, p1, w, h, color):
    """在两点之间画一个方形截面的 "骨骼" 盒子 (手臂 / 腿)"""
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    if L < 1e-5:
        return
    fz = (dx / L, dy / L, dz / L)
    up = (0, 1, 0) if abs(fz[1]) < 0.95 else (1, 0, 0)
    fx = (up[1] * fz[2] - up[2] * fz[1], up[2] * fz[0] - up[0] * fz[2], up[0] * fz[1] - up[1] * fz[0])
    lx = math.sqrt(fx[0] ** 2 + fx[1] ** 2 + fx[2] ** 2)
    fx = (fx[0] / lx, fx[1] / lx, fx[2] / lx)
    fy = (fz[1] * fx[2] - fz[2] * fx[1], fz[2] * fx[0] - fz[0] * fx[2], fz[0] * fx[1] - fz[1] * fx[0])
    m = np.array([fx[0], fx[1], fx[2], 0, fy[0], fy[1], fy[2], 0, fz[0], fz[1], fz[2], 0,
                  (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2, 1], dtype=np.float32)
    glPushMatrix()
    glMultMatrixf(m)
    draw_box(0, 0, 0, w, h, L, color)
    glPopMatrix()


def billboard(pos, size, cam_right, cam_up, rot=0.0):
    """面向摄像机的四边形 (需先绑定纹理)"""
    c, s = math.cos(rot), math.sin(rot)
    rx = [cam_right[i] * c + cam_up[i] * s for i in range(3)]
    ux = [-cam_right[i] * s + cam_up[i] * c for i in range(3)]
    hs = size / 2
    glTexCoord2f(0, 0); glVertex3f(pos[0] - rx[0] * hs - ux[0] * hs, pos[1] - rx[1] * hs - ux[1] * hs, pos[2] - rx[2] * hs - ux[2] * hs)
    glTexCoord2f(1, 0); glVertex3f(pos[0] + rx[0] * hs - ux[0] * hs, pos[1] + rx[1] * hs - ux[1] * hs, pos[2] + rx[2] * hs - ux[2] * hs)
    glTexCoord2f(1, 1); glVertex3f(pos[0] + rx[0] * hs + ux[0] * hs, pos[1] + rx[1] * hs + ux[1] * hs, pos[2] + rx[2] * hs + ux[2] * hs)
    glTexCoord2f(0, 1); glVertex3f(pos[0] - rx[0] * hs + ux[0] * hs, pos[1] - rx[1] * hs + ux[1] * hs, pos[2] - rx[2] * hs + ux[2] * hs)
