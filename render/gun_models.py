"""
程序化枪械建模 (精致战术风格 — 参考 TACZ 与 SuperbWarfare 设计哲学)。

每把枪由精密的部件组构成, 动画系统可独立驱动:
    body   机匣/枪管/枪托/瞄具/导气系统等 (静止基体)
    mag    弹匣/供弹系统 (换弹插拔)
    bolt   拉机柄/机头/枪栓 (拉栓, 空仓挂机)
    slide  手枪套筒 (射击后坐, 空仓挂起)
    pump   泵动护木 (霰弹泵动)
    glass  瞄具镜片 (双层光学镜片, 半透明带镀膜色泽)

模型坐标: 原点=握把顶部 (右手基准), -Z=枪口方向, +Y=上方, 单位米。
所有开镜瞄准点 (sight_y, eye_ref_z, relief) 均经过精密校准，保证开镜中心与屏幕准星完全对齐且缩放精确。
"""
import math
from OpenGL.GL import *
from weapons.definitions import WEAPONS
from weapons.attachments import ATTACHMENTS
from .gl_util import draw_box, draw_cylinder

# ── 材质与色彩 ─────────────────────────────────────────
M_DARK = (0.075, 0.075, 0.082)       # 战术黑硬质阳极氧化
M_STEEL = (0.24, 0.25, 0.26)         # 枪机 / 枪管工具钢
M_RAIL = (0.045, 0.045, 0.050)       # 皮轨凹槽深阴影
M_POLYMER = (0.12, 0.12, 0.13)       # 强化聚合物
BRASS = (0.82, 0.64, 0.24)           # 黄铜弹壳
COPPER = (0.76, 0.44, 0.22)          # 弹头紫铜
RED_SHELL = (0.68, 0.12, 0.10)       # 霰弹红色弹壳
DOT_GLOW = (1.0, 0.20, 0.15)         # 红点发光晶体
FIBER_GLOW = (1.0, 0.25, 0.12)       # ACOG 光纤集光管
TRITIUM = (0.25, 0.95, 0.40)         # 机械瞄具夜光氚光点


def _shade(c, k):
    return (min(1.0, c[0] * k), min(1.0, c[1] * k), min(1.0, c[2] * k))


class GunModel:
    def __init__(self):
        self.parts = {"body": [], "mag": [], "bolt": [], "slide": [], "pump": [], "glass": []}
        self.sight_y = 0.10
        self.eye_ref_z = 0.05
        self.relief = 0.12
        self.muzzle = (0.0, 0.03, -0.60)
        self.grip_r = (0.0, -0.05, 0.03)
        self.grip_l = (0.0, 0.0, -0.30)
        self.mag_pos = (0.0, -0.10, -0.09)
        self.bolt_pos = (0.03, 0.05, 0.05)
        self.pump_pos = (0.0, 0.01, -0.30)
        self.rail_y = 0.078
        self.rail_z = -0.06
        self.kind = "rifle"
        self.lens_r = 0.0
        self.length = 0.80
        self.lists = {}

    def box(self, g, c, s, col, rx=0.0, ry=0.0, rz=0.0):
        self.parts[g].append(("box", c, s, col, rx, ry, rz))

    def cyl(self, g, c, r, l, col, axis="z", seg=14):
        self.parts[g].append(("cyl", c, r, l, col, axis, seg))

    def rail(self, g, cy, z0, z1, w=0.024, h=0.007, col=M_DARK):
        """生成带凹凸齿槽的皮卡汀尼导轨 (TACZ 风格精细刻线)"""
        length = abs(z1 - z0)
        cz = (z0 + z1) / 2
        # 底座基槽
        self.box(g, (0, cy, cz), (w, h, length), col)
        # 凸齿与凹槽
        step = 0.010
        n = max(1, int(length / step))
        slot_w = w + 0.002
        for i in range(n):
            tz = z0 - (i + 0.5) * (length / n) if z0 > z1 else z0 + (i + 0.5) * (length / n)
            self.box(g, (0, cy + h * 0.45, tz), (slot_w, h * 0.4, step * 0.48), _shade(col, 1.25))

    def compile(self):
        for g, prims in self.parts.items():
            if not prims:
                continue
            lid = glGenLists(1)
            glNewList(lid, GL_COMPILE)
            for p in prims:
                if p[0] == "box":
                    _, c, s, col, rx, ry, rz = p
                    if rx or ry or rz:
                        glPushMatrix()
                        glTranslatef(*c)
                        if rx: glRotatef(rx, 1, 0, 0)
                        if ry: glRotatef(ry, 0, 1, 0)
                        if rz: glRotatef(rz, 0, 0, 1)
                        draw_box(0, 0, 0, s[0], s[1], s[2], col)
                        glPopMatrix()
                    else:
                        draw_box(c[0], c[1], c[2], s[0], s[1], s[2], col)
                else:
                    _, c, r, l, col, axis, seg = p
                    draw_cylinder(c[0], c[1], c[2], r, l, col, axis, seg)
            glEndList()
            self.lists[g] = lid

    def draw(self, group):
        lid = self.lists.get(group)
        if lid:
            glCallList(lid)

    def delete(self):
        for lid in self.lists.values():
            glDeleteLists(lid, 1)
        self.lists = {}


# ════════════════════ 配件建模 ════════════════════
def _add_optic(m: GunModel, aid, iron_front_z, pistol=False):
    """
    安装瞄具并精确设置开镜瞄准轴:
      m.sight_y: 瞄准轴眼高 (保证红点/分划线在屏幕正中央)
      m.eye_ref_z: 瞄具物镜/目镜基准面
      m.relief: 出瞳距离，决定开镜时瞄具占视野比例
    """
    ry, rz = m.rail_y, m.rail_z
    if aid == "iron":
        if pistol:
            return
        # ── 战术折叠机械瞄具 (立起工作状态) ──
        # 后机瞄 (双孔觇孔照门 + 风偏调节轮)
        m.box("body", (0, ry + 0.014, rz + 0.12), (0.024, 0.022, 0.014), M_DARK)
        m.box("body", (0, ry + 0.032, rz + 0.12), (0.018, 0.024, 0.008), M_DARK)
        m.box("body", (-0.007, ry + 0.040, rz + 0.12), (0.004, 0.016, 0.006), M_STEEL)
        m.box("body", (0.007, ry + 0.040, rz + 0.12), (0.004, 0.016, 0.006), M_STEEL)
        # 风偏螺钮
        m.box("body", (0.015, ry + 0.032, rz + 0.12), (0.008, 0.010, 0.010), M_STEEL)
        # 前机瞄 (护圈 + 准星柱 + 氚光标记)
        m.box("body", (0, ry + 0.016, iron_front_z), (0.022, 0.025, 0.014), M_DARK)
        m.box("body", (-0.008, ry + 0.038, iron_front_z), (0.004, 0.022, 0.010), M_DARK, rz=12)
        m.box("body", (0.008, ry + 0.038, iron_front_z), (0.004, 0.022, 0.010), M_DARK, rz=-12)
        m.box("body", (0, ry + 0.038, iron_front_z), (0.003, 0.016, 0.004), M_STEEL)
        m.box("body", (0, ry + 0.044, iron_front_z), (0.003, 0.004, 0.004), TRITIUM)  # 氚光夜光准心

        m.sight_y = ry + 0.043
        m.eye_ref_z = rz + 0.12
        m.relief = 0.22
        return

    # 安装光学瞄具时，折叠备用机瞄卧倒在导轨前后
    if not pistol:
        m.box("body", (0, ry + 0.006, rz + 0.12), (0.022, 0.010, 0.028), M_DARK)
        m.box("body", (0, ry + 0.006, iron_front_z), (0.018, 0.010, 0.028), M_DARK)

    if aid == "rmr":
        # ── Trijicon RMR 微型反射式红点 (手枪专用) ──
        z = 0.0
        m.box("body", (0, ry + 0.006, z), (0.026, 0.012, 0.044), M_DARK)
        # 防护外框与倒角
        m.box("body", (0, ry + 0.026, z - 0.016), (0.026, 0.028, 0.006), M_DARK)
        m.box("body", (-0.012, ry + 0.020, z), (0.004, 0.020, 0.034), M_DARK)
        m.box("body", (0.012, ry + 0.020, z), (0.004, 0.020, 0.034), M_DARK)
        # 侧面调节旋钮
        m.box("body", (0.014, ry + 0.015, z), (0.004, 0.008, 0.008), M_STEEL)
        # 镀膜微弧镜片
        m.box("glass", (0, ry + 0.024, z - 0.010), (0.020, 0.022, 0.002), (0.42, 0.85, 0.65))
        m.sight_y = ry + 0.024
        m.eye_ref_z = z + 0.015
        m.relief = 0.36

    elif aid == "reddot":
        # ── Aimpoint T2 封闭式管状红点 ──
        z = rz + 0.02
        # 镂空高增高垫块 + 导轨锁紧螺栓
        m.box("body", (0, ry + 0.006, z), (0.028, 0.012, 0.048), M_DARK)
        m.box("body", (0, ry + 0.018, z), (0.014, 0.014, 0.024), M_DARK)
        m.box("body", (0.016, ry + 0.008, z), (0.006, 0.010, 0.014), M_STEEL)
        # 镜体主筒
        m.cyl("body", (0, ry + 0.042, z), 0.019, 0.052, M_DARK, seg=16)
        # 前后遮光罩与物镜外圈
        m.cyl("body", (0, ry + 0.042, z - 0.026), 0.021, 0.008, _shade(M_DARK, 1.2), seg=16)
        m.cyl("body", (0, ry + 0.042, z + 0.026), 0.021, 0.008, _shade(M_DARK, 1.2), seg=16)
        # 顶部/右侧防尘盖与高低/风偏调节手轮
        m.box("body", (0, ry + 0.063, z - 0.004), (0.012, 0.008, 0.012), M_STEEL)
        m.box("body", (0.021, ry + 0.042, z - 0.004), (0.008, 0.012, 0.012), M_STEEL)
        # 侧挂电池仓与旋钮
        m.cyl("body", (0.018, ry + 0.038, z + 0.014), 0.009, 0.014, M_DARK, axis="x", seg=12)
        # 镀膜前后镜片
        m.box("glass", (0, ry + 0.042, z - 0.022), (0.028, 0.028, 0.002), (0.40, 0.78, 0.60))
        m.box("glass", (0, ry + 0.042, z + 0.022), (0.028, 0.028, 0.002), (0.35, 0.65, 0.80))
        m.sight_y = ry + 0.042
        m.eye_ref_z = z + 0.026
        m.relief = 0.22
        m.lens_r = 0.016

    elif aid == "holo":
        # ── EOTech EXPS3 战术全息瞄具 ──
        z = rz + 0.03
        # 快拆导轨底座 + 侧推锁扣
        m.box("body", (0, ry + 0.009, z), (0.046, 0.016, 0.088), M_DARK)
        m.box("body", (0.026, ry + 0.009, z), (0.008, 0.012, 0.040), M_STEEL)
        # 外层航空铝合金翻滚防撞罩 (带前倾斜角)
        m.box("body", (-0.022, ry + 0.042, z - 0.006), (0.006, 0.052, 0.058), M_DARK)
        m.box("body", (0.022, ry + 0.042, z - 0.006), (0.006, 0.052, 0.058), M_DARK)
        m.box("body", (0, ry + 0.069, z - 0.006), (0.050, 0.006, 0.058), M_DARK)
        # 前斜角倒切
        m.box("body", (0, ry + 0.062, z - 0.038), (0.048, 0.014, 0.012), M_DARK, rx=25)
        # 侧面硅胶亮度调节按钮组
        m.box("body", (-0.024, ry + 0.032, z + 0.016), (0.003, 0.012, 0.022), (0.18, 0.18, 0.18))
        # 全息方框双层光学镜片
        m.box("glass", (0, ry + 0.043, z - 0.024), (0.036, 0.040, 0.002), (0.45, 0.70, 0.85))
        m.box("glass", (0, ry + 0.043, z + 0.016), (0.036, 0.040, 0.002), (0.40, 0.65, 0.80))
        m.sight_y = ry + 0.043
        m.eye_ref_z = z + 0.024
        m.relief = 0.20

    elif aid in ("x3", "x4"):
        # ── Trijicon ACOG 4x32 战术棱镜瞄具 ──
        z = rz + 0.02
        L = 0.12 if aid == "x3" else 0.15
        # 导轨双螺栓安装座
        m.box("body", (0, ry + 0.008, z), (0.032, 0.015, L * 0.72), M_DARK)
        m.box("body", (0.018, ry + 0.008, z - 0.02), (0.008, 0.012, 0.014), M_STEEL)
        m.box("body", (0.018, ry + 0.008, z + 0.02), (0.008, 0.012, 0.014), M_STEEL)
        # 棱镜主体 (锥形过渡锻造壳体)
        m.box("body", (0, ry + 0.034, z), (0.038, 0.038, L * 0.58), M_DARK)
        # 前物镜筒与遮光檐
        m.cyl("body", (0, ry + 0.044, z - L * 0.40), 0.022, L * 0.35, M_DARK, seg=16)
        m.cyl("body", (0, ry + 0.044, z - L * 0.55), 0.023, 0.010, _shade(M_DARK, 1.2), seg=16)
        # 后目镜与波纹橡胶眼罩
        m.cyl("body", (0, ry + 0.044, z + L * 0.38), 0.019, L * 0.30, M_DARK, seg=16)
        m.cyl("body", (0, ry + 0.044, z + L * 0.52), 0.021, 0.012, (0.05, 0.05, 0.05), seg=16)
        # 顶部高亮红色光纤集光条 (ACOG 标志性特征)
        m.box("body", (0, ry + 0.068, z - 0.010), (0.006, 0.008, L * 0.45), FIBER_GLOW)
        m.box("body", (0, ry + 0.065, z - 0.010), (0.012, 0.004, L * 0.50), M_STEEL)
        # 保护盖旋钮
        m.box("body", (0.021, ry + 0.044, z - 0.005), (0.008, 0.012, 0.012), M_STEEL)
        m.box("body", (0, ry + 0.065, z + 0.025), (0.012, 0.008, 0.012), M_STEEL)
        # 高透多层镀膜镜片
        m.box("glass", (0, ry + 0.044, z - L * 0.50), (0.032, 0.032, 0.002), (0.35, 0.75, 0.65))
        m.box("glass", (0, ry + 0.044, z + L * 0.50), (0.030, 0.030, 0.002), (0.30, 0.60, 0.85))
        m.sight_y = ry + 0.044
        m.eye_ref_z = z + L * 0.52
        m.relief = 0.13

    elif aid in ("x8", "x12"):
        # ── 远距离高精度狙击瞄准镜 (带遮光筒与快速调节塔轮) ──
        z = rz + 0.0
        L = 0.31 if aid == "x8" else 0.36
        h = ry + 0.050
        # 34mm 双体加固战术镜圈 (带导轨锁紧块与 6 颗内六角螺钉)
        for dz in (-0.065, 0.065):
            m.box("body", (0, ry + 0.016, z + dz), (0.032, 0.024, 0.024), M_DARK)
            m.box("body", (0.018, ry + 0.016, z + dz), (0.008, 0.012, 0.016), M_STEEL)
            m.box("body", (0, h + 0.018, z + dz), (0.034, 0.006, 0.024), M_STEEL)
        # 镜身中央 34mm 主镜管
        m.cyl("body", (0, h, z), 0.017, L * 0.58, M_DARK, seg=16)
        # 前物镜钟 (56mm 大口径锥形扩张筒 + 延伸遮光筒)
        obj_z = z - L * 0.36
        m.cyl("body", (0, h, obj_z), 0.028, 0.09, M_DARK, seg=18)
        m.cyl("body", (0, h, obj_z - 0.055), 0.029, 0.02, _shade(M_DARK, 1.25), seg=18)
        # 后目镜筒 + 变倍调节环 (带快调拨杆 Throw Lever)
        eye_z = z + L * 0.32
        m.cyl("body", (0, h, eye_z), 0.022, 0.08, M_DARK, seg=18)
        m.cyl("body", (0, h, eye_z - 0.035), 0.024, 0.018, _shade(M_STEEL, 0.9), seg=18)
        m.box("body", (0, h + 0.028, eye_z - 0.035), (0.006, 0.014, 0.008), M_STEEL)  # 变倍拨杆
        m.cyl("body", (0, h, eye_z + 0.048), 0.023, 0.018, (0.05, 0.05, 0.05), seg=18)  # 橡胶目镜圈
        # 战术高耸高低/风偏塔轮 (带清晰刻度槽与防滑滚花)
        m.cyl("body", (0, h + 0.026, z), 0.012, 0.022, M_STEEL, axis="y", seg=16)
        m.cyl("body", (0.026, h, z), 0.012, 0.022, M_STEEL, axis="x", seg=16)
        m.cyl("body", (-0.026, h, z), 0.010, 0.018, M_STEEL, axis="x", seg=14)  # 侧视差调节轮
        # 双层防眩多层镀膜光学镜片
        m.box("glass", (0, h, obj_z - 0.045), (0.044, 0.044, 0.002), (0.30, 0.70, 0.60))
        m.box("glass", (0, h, eye_z + 0.045), (0.036, 0.036, 0.002), (0.25, 0.55, 0.80))
        m.sight_y = h
        m.eye_ref_z = eye_z + 0.055
        m.relief = 0.11


def _add_muzzle(m: GunModel, aid, bz, by, br, pistol=False):
    """
    安装枪口装置 (消音器/补偿器/消焰器/制退器/收束器) 并返回新的枪口中心坐标 Z
    """
    if aid == "suppressor":
        # ── 战术快拆消音器 (带滚花锁紧环与内部挡板槽线) ──
        L = 0.14 if pistol else 0.18
        r = 0.016 if pistol else 0.020
        # 尾部快拆齿纹锁环
        m.cyl("body", (0, by, bz - 0.012), r * 1.05, 0.024, _shade(M_STEEL, 0.8), seg=16)
        # 筒身消光耐热涂层
        m.cyl("body", (0, by, bz - L / 2), r, L, (0.10, 0.10, 0.11), seg=16)
        # 前端内凹出弹孔端盖
        m.cyl("body", (0, by, bz - L + 0.005), r * 0.92, 0.010, M_DARK, seg=16)
        m.cyl("body", (0, by, bz - L + 0.002), br * 0.7, 0.006, (0.02, 0.02, 0.02), seg=10)
        return bz - L

    if aid == "compensator":
        # ── 双室枪口补偿器 (顶部双开泄气孔 + 侧面偏转挡板) ──
        cL = 0.055 if pistol else 0.075
        cR = br * 1.45
        m.cyl("body", (0, by, bz - cL / 2), cR, cL, M_STEEL, seg=12)
        # 顶部泄气孔槽
        m.box("body", (0, by + cR * 0.95, bz - cL * 0.4), (0.008, 0.006, 0.014), (0.02, 0.02, 0.02))
        m.box("body", (0, by + cR * 0.95, bz - cL * 0.7), (0.008, 0.006, 0.014), (0.02, 0.02, 0.02))
        return bz - cL

    if aid == "flashhider":
        # ── A2 鸟笼式五开槽消焰器 ──
        fL = 0.040 if pistol else 0.055
        m.cyl("body", (0, by, bz - fL / 2), br * 1.3, fL, M_DARK, seg=12)
        # 径向发散消焰槽 (底部封闭防止扬尘)
        for ang in (0.3, 0.9, 1.57, 2.24, 2.84):
            sx = math.cos(ang) * br * 1.3
            sy = math.sin(ang) * br * 1.3
            m.box("body", (sx, by + sy, bz - fL * 0.65), (0.004, 0.004, fL * 0.5), (0.02, 0.02, 0.02))
        return bz - fL

    if aid == "brake":
        # ── 竞技大型制退器 (双室侧向排气叶片) ──
        m.box("body", (0, by, bz - 0.045), (0.044, 0.032, 0.085), M_DARK)
        # 左右倾斜偏转排气室
        for s in (-1, 1):
            m.box("body", (s * 0.018, by, bz - 0.032), (0.012, 0.024, 0.016), (0.02, 0.02, 0.02))
            m.box("body", (s * 0.018, by, bz - 0.060), (0.012, 0.024, 0.016), (0.02, 0.02, 0.02))
        return bz - 0.09

    if aid == "choke":
        # ── 破门锯齿收束器 ──
        m.cyl("body", (0, by, bz - 0.028), br * 1.3, 0.055, M_STEEL, seg=14)
        for i in range(4):
            ang = i * math.pi / 2
            m.box("body", (math.cos(ang) * br * 1.25, by + math.sin(ang) * br * 1.25, bz - 0.058),
                  (0.006, 0.006, 0.008), M_STEEL)
        return bz - 0.06

    # 标准原厂枪口
    m.cyl("body", (0, by, bz - 0.018), br * 1.22, 0.036, M_DARK, seg=12)
    return bz - 0.036


def _add_underbarrel(m: GunModel, aid, z, y, pistol=False):
    """安装战术下挂配件 (垂直握把 / 倾斜握把 / 战术激光指示器 / 双脚架)"""
    if aid == "vgrip":
        # ── 战术垂直握把 (带指槽与导轨锁紧块) ──
        m.box("body", (0, y + 0.005, z), (0.028, 0.014, 0.045), M_DARK)
        m.box("body", (0, y - 0.055, z), (0.028, 0.095, 0.032), M_DARK)
        for i in range(3):
            m.box("body", (0, y - 0.035 - i * 0.022, z - 0.014), (0.030, 0.008, 0.006), _shade(M_DARK, 0.7))
        m.grip_l = (0.0, y - 0.075, z)

    elif aid == "agrip":
        # ── Magpul AFG 三角战术握把 (人体工程学导向) ──
        m.box("body", (0, y + 0.004, z), (0.032, 0.012, 0.095), M_DARK)
        m.box("body", (0, y - 0.024, z + 0.015), (0.030, 0.032, 0.090), M_DARK, rx=-18)
        m.box("body", (0, y - 0.038, z - 0.032), (0.030, 0.022, 0.015), M_DARK)  # 前挡手凸起
        m.grip_l = (-0.005, y - 0.032, z + 0.010)

    elif aid == "laser":
        # ── PEQ-15 战术红外激光指示器 ──
        if pistol:
            m.box("body", (0, y - 0.012, z), (0.024, 0.020, 0.048), M_DARK)
            m.box("body", (0.006, y - 0.012, z - 0.024), (0.008, 0.008, 0.004), DOT_GLOW)
        else:
            # 步枪右侧侧挂
            m.box("body", (0.032, y + 0.010, z), (0.020, 0.026, 0.068), M_DARK)
            m.box("body", (0.032, y + 0.014, z - 0.035), (0.008, 0.008, 0.004), DOT_GLOW)
            m.box("body", (0.032, y + 0.022, z + 0.010), (0.012, 0.008, 0.018), M_STEEL)  # 拨轮

    elif aid == "bipod":
        # ── 哈里斯可折叠战术双脚架 ──
        m.box("body", (0, y - 0.012, z - 0.02), (0.034, 0.020, 0.044), M_DARK)
        m.box("body", (0, y - 0.022, z - 0.02), (0.018, 0.010, 0.024), M_STEEL)
        for sx in (-0.014, 0.014):
            # 折叠收拢在护木下方两侧的腿杆与弹簧
            m.cyl("body", (sx, y - 0.028, z + 0.07), 0.005, 0.18, M_STEEL, seg=10)
            m.box("body", (sx, y - 0.028, z + 0.165), (0.012, 0.012, 0.014), M_DARK)  # 脚垫


def _mag(m: GunModel, style, x, y, z, color, ext=1.0, drum=False):
    """
    弹匣建模 (挂接在 'mag' 组，换弹动作将驱动整个弹匣)
    """
    if drum:
        # ── 60 发大容量弹鼓 ──
        m.box("mag", (0, y - 0.030, z), (0.028, 0.060, 0.065), color)
        m.cyl("mag", (0, y - 0.115, z + 0.006), 0.068, 0.075, color, axis="x", seg=22)
        m.cyl("mag", (0.038, y - 0.115, z + 0.006), 0.022, 0.010, _shade(color, 1.3), axis="x", seg=14)  # 发条轮
        m.box("mag", (0, y - 0.115, z + 0.006), (0.076, 0.014, 0.110), _shade(color, 0.75))  # 加强筋
        m.mag_pos = (0, y - 0.11, z)
        return

    if style in ("stanag", "curved", "ak"):
        # ── 弧形/香蕉形弹匣 (带加强筋与透明弹药余量窗) ──
        curve = {"stanag": 0.014, "curved": 0.032, "ak": 0.048}[style]
        segs = 4
        seg_h = (0.048 if style != "ak" else 0.052) * ext
        w = 0.026 if style == "stanag" else 0.028
        d = 0.065 if style == "stanag" else 0.070
        for i in range(segs):
            t = (i + 0.5) / segs
            cy = y - seg_h * (i + 0.5)
            cz = z - curve * (t ** 1.35) * 1.6
            tilt = -7.5 * i * (curve / 0.03)
            m.box("mag", (0, cy, cz), (w, seg_h + 0.002, d), color, rx=tilt)
            # 弹匣冲压横向加强槽
            m.box("mag", (0, cy, cz), (w + 0.003, seg_h * 0.35, d - 0.012), _shade(color, 0.8), rx=tilt)
            # 侧面透明余量窗 (露出铜黄色子弹)
            if i in (1, 2) and style in ("stanag", "curved"):
                for s in (-1, 1):
                    m.box("mag", (s * (w / 2 + 0.001), cy, cz), (0.001, seg_h * 0.75, 0.014), (0.1, 0.1, 0.1))
                    m.box("mag", (s * (w / 2 + 0.001), cy, cz), (0.001, seg_h * 0.50, 0.008), BRASS)
        # 底板与快拔环凸缘
        bot_z = z - curve * 1.6 - 0.004
        bot_y = y - seg_h * segs - 0.006
        m.box("mag", (0, bot_y, bot_z), (w + 0.008, 0.014, d + 0.012), _shade(color, 0.7))
        m.mag_pos = (0, y - seg_h * 1.6, z - curve)

    elif style == "pistol":
        # ── 手枪单/双排弹匣 ──
        L = 0.110 * ext
        m.box("mag", (0, y - L / 2, z), (0.022, L, 0.038), (0.12, 0.12, 0.13), rx=-12)
        # 金属托弹唇
        m.box("mag", (0, y - 0.004, z - 0.002), (0.018, 0.008, 0.030), M_STEEL, rx=-12)
        m.box("mag", (0, y - 0.004, z - 0.002), (0.009, 0.006, 0.020), BRASS, rx=-12)
        # 加厚工程塑料底板
        m.box("mag", (0, y - L + 0.002, z + L * 0.20), (0.028, 0.016, 0.048), color, rx=-12)
        m.mag_pos = (0, y - L * 0.65, z + 0.01)

    else:
        # ── 狙击/重型直列冲压钢弹匣 (5发/10发/20发) ──
        size = {"box20": (0.030, 0.125, 0.078), "box5": (0.035, 0.065, 0.088),
                "box10": (0.036, 0.105, 0.092), "saiga": (0.042, 0.135, 0.090)}.get(style, (0.032, 0.11, 0.075))
        h = size[1] * ext
        m.box("mag", (0, y - h / 2, z), (size[0], h, size[2]), color)
        # 钢板冲压凹凸加强筋
        for i in range(max(1, int(h / 0.025))):
            m.box("mag", (0, y - (i + 0.5) * 0.025, z), (size[0] + 0.003, 0.008, size[2] - 0.014), _shade(color, 0.8))
        m.box("mag", (0, y - h - 0.004, z), (size[0] + 0.006, 0.012, size[2] + 0.008), _shade(color, 0.65))
        m.mag_pos = (0, y - h * 0.55, z)


# ════════════════════ 枪系总装 ════════════════════
def _build_rifle(m: GunModel, d, atts, sniper=False):
    C = d.model.get("color", (0.14, 0.14, 0.14))
    F = d.model.get("furniture", C)
    B = d.model.get("barrel", 0.36)
    R = d.model.get("receiver", 0.42)
    stock = d.model.get("stock", "m4")
    mstyle = d.model.get("mag", "stanag")
    hg = d.model.get("handguard", "ris")
    thick = d.model.get("thick_barrel", False)
    big = d.id == "m82"

    rz_front = 0.08 - R * 0.68
    # ── 握把 / 扳机护圈 / 人体工学指槽 ──
    m.box("body", (0, -0.065, 0.035), (0.032, 0.105, 0.046), F, rx=18)
    m.box("body", (0, -0.035, 0.060), (0.032, 0.025, 0.020), F)           # 虎口海狸尾 (Beavertail)
    for i in range(3):
        m.box("body", (0, -0.042 - i * 0.022, 0.012), (0.033, 0.008, 0.008), _shade(F, 0.8), rx=18)
    m.box("body", (0, -0.032, -0.012), (0.014, 0.012, 0.065), M_DARK)     # 扳机护圈底板
    m.box("body", (0, -0.020, -0.004), (0.004, 0.020, 0.008), M_STEEL, rx=-15)  # 曲线扳机

    # ── 下机匣与弹匣井 ──
    lw = 0.054 if big else 0.044
    m.box("body", (0, -0.004, (0.08 + rz_front) / 2), (lw, 0.056, 0.08 - rz_front), C)
    m.box("body", (0, -0.036, -0.090), (lw - 0.002, 0.022, 0.082), C)      # 扩口喇叭弹匣井
    # 快慢机旋钮 (Safe / Semi / Auto)
    m.box("body", (-lw / 2 - 0.003, 0.008, 0.025), (0.005, 0.010, 0.018), M_STEEL, rz=25)
    # 弹匣卡榫与空仓挂机解脱钮
    m.box("body", (lw / 2 + 0.002, -0.015, -0.075), (0.004, 0.010, 0.012), M_STEEL)
    m.box("body", (-lw / 2 - 0.002, 0.015, -0.045), (0.004, 0.016, 0.010), M_STEEL)

    # ── 上机匣与抛壳窗 ──
    uh = 0.082 if big else 0.052
    m.box("body", (0, 0.022 + uh / 2, (0.085 + rz_front) / 2), (lw + 0.004, uh, 0.085 - rz_front), _shade(C, 1.08))
    # 顶部平顶全长皮卡汀尼导轨 (含精细凹凸齿)
    ry = 0.022 + uh + 0.004
    m.rail("body", ry, 0.08, rz_front - 0.02, w=0.025, col=M_RAIL)
    m.rail_y = ry + 0.004
    m.rail_z = (0.06 + rz_front) / 2
    # 右侧内凹抛壳窗 + 黄铜弹药显露 + 弹壳偏向块 (Brass Deflector)
    m.box("body", (lw / 2 + 0.002, 0.045, -0.050), (0.004, 0.018, 0.058), (0.02, 0.02, 0.02))
    m.box("body", (lw / 2 - 0.003, 0.045, -0.050), (0.006, 0.012, 0.038), BRASS)
    m.box("body", (lw / 2 + 0.008, 0.046, -0.012), (0.012, 0.016, 0.018), C, ry=35)  # 抛壳偏向块
    # 辅助推机柄 (Forward Assist)
    if not sniper and hg == "ris":
        m.cyl("body", (lw / 2 + 0.012, 0.052, 0.030), 0.007, 0.022, M_STEEL, axis="x")

    # ── 拉机柄 / 枪栓 ──
    if d.model.get("bolt"):
        # 旋转后拉式枪栓 (AWM / 狙击步枪)
        m.cyl("bolt", (lw / 2 + 0.030, ry - 0.018, 0.040), 0.006, 0.062, M_STEEL, axis="x")
        m.box("bolt", (lw / 2 + 0.062, ry - 0.024, 0.040), (0.018, 0.018, 0.018), M_DARK)  # 大水滴球头拉柄
        m.box("bolt", (0, ry - 0.018, 0.015), (lw * 0.65, 0.022, 0.11), M_STEEL)
        m.bolt_pos = (lw / 2 + 0.062, ry - 0.024, 0.040)
    else:
        # AR T型拉机柄 或 侧拉柄
        m.box("bolt", (0, ry - 0.010, 0.095), (0.036, 0.012, 0.024), M_DARK)
        m.box("bolt", (lw / 2 + 0.008, 0.047, -0.040), (0.010, 0.012, 0.018), M_STEEL)
        m.bolt_pos = (lw / 2 + 0.012, 0.047, -0.040)

    # ── 护木系统 ──
    HG = min(0.38, B * 0.85) if not sniper else B * 0.58
    hz = rz_front - HG / 2
    by = 0.022 + uh * 0.45
    if hg == "ris":
        # 四向皮卡汀尼导轨战术护木 (RIS II)
        m.box("body", (0, by, hz), (0.058, 0.062, HG), F)
        m.rail("body", by + 0.034, rz_front, rz_front - HG, w=0.024, col=M_RAIL)
        m.rail("body", by - 0.034, rz_front, rz_front - HG, w=0.024, col=M_RAIL)
        for s in (-1, 1):
            m.box("body", (s * 0.031, by, hz), (0.006, 0.022, HG * 0.95), M_RAIL)
    elif hg == "ak":
        # AK 战术木质/强化聚合物护木 + 顶部冲压导气管罩
        m.box("body", (0, by - 0.006, hz), (0.050, 0.052, HG), F)
        m.box("body", (0, by + 0.034, hz), (0.032, 0.024, HG * 0.92), _shade(F, 1.25))
        m.rail("body", by + 0.048, rz_front, rz_front - HG * 0.9, w=0.022, col=M_RAIL)
    elif hg == "scar":
        # SCAR 一体化挤压铝合金上机匣护木一体
        m.box("body", (0, by, hz), (0.052, 0.060, HG), C)
        m.rail("body", by + 0.034, rz_front, rz_front - HG, w=0.024, col=M_RAIL)
        m.rail("body", by - 0.034, rz_front, rz_front - HG * 0.8, w=0.024, col=M_RAIL)
        for s in (-1, 1):
            m.box("body", (s * 0.028, by - 0.006, hz), (0.006, 0.020, HG * 0.65), M_RAIL)
    else:  # QBZ-191 平滑护木 (带 M-LOK 散热切口)
        m.box("body", (0, by, hz), (0.054, 0.058, HG), F)
        m.rail("body", by + 0.033, rz_front, rz_front - HG, w=0.024, col=M_RAIL)
        # M-LOK 镂空槽
        for i in range(max(1, int(HG / 0.045))):
            sz = rz_front - 0.025 - i * 0.045
            for s in (-1, 1):
                m.box("body", (s * 0.028, by, sz), (0.002, 0.010, 0.028), (0.02, 0.02, 0.02))

    if sniper:
        # 重型狙击底盘下托
        m.box("body", (0, by - 0.014, (0.08 + rz_front - HG) / 2 - 0.02), (0.058, 0.054, HG + 0.14), F)

    # ── 枪管与导气箍 ──
    br = 0.018 if (thick or big) else (0.014 if sniper else 0.012)
    bz0 = rz_front - HG
    bl = B - HG * 0.40
    m.cyl("body", (0, by, bz0 - bl / 2 + 0.02), br, bl + 0.04, M_DARK, seg=14)
    # 导气箍与外露不锈钢导气管
    if hg != "ak" and not sniper:
        m.box("body", (0, by + 0.020, bz0 - 0.030), (0.022, 0.030, 0.032), M_DARK)
        m.cyl("body", (0, by + 0.025, bz0 + 0.04), 0.004, 0.12, M_STEEL)

    muzzle_z = _add_muzzle(m, atts["muzzle"], bz0 - bl, by, br)
    if d.model.get("brake") and atts["muzzle"] == "muzzle_std":
        # 巴雷特 M82 标志性巨型箭头箭镞双室制退器
        m.box("body", (0, by, bz0 - bl - 0.055), (0.068, 0.048, 0.11), M_DARK)
        for s in (-1, 1):
            m.box("body", (s * 0.024, by, bz0 - bl - 0.045), (0.018, 0.036, 0.024), (0.02, 0.02, 0.02), ry=-35 * s)
            m.box("body", (s * 0.024, by, bz0 - bl - 0.075), (0.018, 0.036, 0.024), (0.02, 0.02, 0.02), ry=-35 * s)
        muzzle_z = bz0 - bl - 0.12
    m.muzzle = (0, by, muzzle_z)

    # ── 枪托建模 ──
    sy = 0.030
    if stock == "m4":
        # 6 档缓冲管 + SOPMOD 战术海狸尾贴腮枪托 + 橡胶防滑底板
        m.cyl("body", (0, sy, 0.19), 0.017, 0.22, M_DARK, seg=14)
        m.box("body", (0, sy - 0.012, 0.25), (0.045, 0.078, 0.13), F)
        m.box("body", (0, sy + 0.032, 0.24), (0.048, 0.018, 0.11), F)     # 贴腮宽斜面
        m.box("body", (0, sy - 0.015, 0.320), (0.046, 0.105, 0.022), (0.06, 0.06, 0.06))  # 橡胶缓冲底垫
    elif stock == "191":
        # QBZ-191 伸缩托 (带加高贴腮板)
        m.cyl("body", (0, sy, 0.19), 0.018, 0.21, M_DARK, seg=14)
        m.box("body", (0, sy - 0.010, 0.25), (0.048, 0.082, 0.14), F)
        m.box("body", (0, sy + 0.036, 0.24), (0.042, 0.022, 0.11), _shade(F, 1.15))
        m.box("body", (0, sy - 0.015, 0.325), (0.050, 0.108, 0.022), M_DARK)
    elif stock == "folding":
        # 折叠钢丝骨架托 (AK-12 / Saiga-12)
        m.box("body", (0, sy + 0.022, 0.20), (0.022, 0.015, 0.24), F)
        m.box("body", (0, sy - 0.036, 0.20), (0.022, 0.015, 0.24), F)
        m.box("body", (0, sy - 0.008, 0.320), (0.038, 0.105, 0.024), M_DARK)
    elif stock == "scar":
        # SCAR "雪地靴" 复合折叠托 (带阶梯式高低贴腮板)
        m.box("body", (0, sy - 0.006, 0.20), (0.046, 0.072, 0.22), F)
        m.box("body", (0, sy + 0.038, 0.22), (0.038, 0.018, 0.14), _shade(F, 1.18))
        m.box("body", (0, sy - 0.010, 0.320), (0.048, 0.105, 0.022), M_DARK)
    elif stock == "aw":
        # Accuracy International Arctic Warfare 标志性绿色/沙色拇指孔复合底盘
        m.box("body", (0, sy - 0.006, 0.18), (0.046, 0.054, 0.18), F)
        m.box("body", (0, sy - 0.056, 0.25), (0.044, 0.044, 0.14), F)     # 拇指孔握把下框
        m.box("body", (0, sy + 0.038, 0.24), (0.038, 0.032, 0.13), _shade(F, 1.12))  # 高度可调贴腮垫
        m.box("body", (0, sy - 0.020, 0.335), (0.048, 0.135, 0.024), M_DARK)  # 垫片式调节尾板
    elif stock == "barrett":
        # 巴雷特重型缓冲后托 (带后握把与尾部驻锄)
        m.box("body", (0, sy, 0.20), (0.052, 0.084, 0.24), C)
        m.box("body", (0, sy - 0.020, 0.335), (0.054, 0.135, 0.032), M_DARK)
        m.box("body", (0, sy + 0.052, 0.24), (0.032, 0.024, 0.10), M_DARK)
    elif stock == "svd":
        # SVD 德拉贡诺夫经典镂空木质枪托 (曲面贴腮垫与真木质感)
        m.box("body", (0, sy + 0.012, 0.20), (0.042, 0.032, 0.22), F)
        m.box("body", (0, sy - 0.062, 0.25), (0.038, 0.032, 0.16), F)
        m.box("body", (0, sy - 0.032, 0.14), (0.038, 0.092, 0.032), F)
        m.box("body", (0, sy + 0.040, 0.22), (0.038, 0.024, 0.10), _shade(F, 0.8))  # 皮革贴腮
        m.box("body", (0, sy - 0.020, 0.325), (0.042, 0.125, 0.030), M_STEEL)

    # ── 弹匣安装 ──
    ext = 1.35 if atts["magazine"] == "mag_ext" else (0.85 if atts["magazine"] == "mag_fast" else 1.0)
    _mag(m, mstyle, 0, -0.035, -0.09, _shade(C, 1.15), ext, atts["magazine"] == "mag_drum")

    # ── 瞄具 / 导轨配件 ──
    _add_optic(m, atts["optic"], bz0 - 0.02)
    _add_underbarrel(m, atts["underbarrel"], hz, by - 0.045)

    m.grip_r = (0.0, -0.050, 0.030)
    if atts["underbarrel"] not in ("vgrip", "agrip"):
        m.grip_l = (0.0, by - 0.035, hz)
    m.length = 0.35 - muzzle_z


def _build_bullpup(m: GunModel, d, atts):
    """
    无托步枪 (QBZ-95-1 / QBU-88) 建模
    """
    C = d.model.get("color", (0.18, 0.19, 0.16))
    F = d.model.get("furniture", C)
    B = d.model.get("barrel", 0.32)
    R = d.model.get("receiver", 0.52)
    mstyle = d.model.get("mag", "curved")

    # ── 握把与前一体化护木 ──
    m.box("body", (0, -0.055, -0.08), (0.032, 0.105, 0.045), F, rx=18)
    m.box("body", (0, -0.025, -0.12), (0.014, 0.014, 0.065), M_DARK)
    m.box("body", (0, -0.015, -0.11), (0.004, 0.020, 0.008), M_STEEL)
    # 前手托一体式护木
    m.box("body", (0, -0.022, -0.20), (0.048, 0.055, 0.15), F)

    # ── 机匣与托底板 (弹匣在握把后方) ──
    m.box("body", (0, 0.005, 0.05), (0.050, 0.075, 0.42), C)
    m.box("body", (0, 0.005, 0.26), (0.052, 0.110, 0.030), M_DARK)  # 橡胶托底

    # ── 提把与顶部战术导轨 ──
    m.box("body", (0, 0.065, -0.06), (0.036, 0.055, 0.28), F)
    m.rail("body", 0.098, 0.06, -0.18, w=0.024, col=M_RAIL)
    m.rail_y = 0.102
    m.rail_z = -0.06

    # ── 拉机柄 ──
    m.box("bolt", (0, 0.055, -0.02), (0.022, 0.014, 0.032), M_DARK)
    m.bolt_pos = (0.0, 0.060, -0.02)

    # ── 枪管与枪口 ──
    by = 0.020
    bz0 = -0.24
    m.cyl("body", (0, by, bz0 - B / 2), 0.013, B, M_DARK, seg=14)
    muzzle_z = _add_muzzle(m, atts["muzzle"], bz0 - B, by, 0.013)
    m.muzzle = (0, by, muzzle_z)

    # ── 弹匣 (后置) ──
    ext = 1.35 if atts["magazine"] == "mag_ext" else (0.85 if atts["magazine"] == "mag_fast" else 1.0)
    _mag(m, mstyle, 0, -0.035, 0.12, _shade(C, 1.15), ext, atts["magazine"] == "mag_drum")

    # ── 瞄具与下挂 ──
    _add_optic(m, atts["optic"], -0.12)
    if atts["optic"] == "iron":
        m.sight_y = 0.120
        m.eye_ref_z = 0.16
        m.relief = 0.22
    _add_underbarrel(m, atts["underbarrel"], -0.18, -0.035)

    m.grip_r = (0.0, -0.045, -0.07)
    if atts["underbarrel"] not in ("vgrip", "agrip"):
        m.grip_l = (0.0, -0.025, -0.18)
    m.length = 0.34 - muzzle_z


def _build_pistol(m: GunModel, d, atts):
    """
    手枪建模 (P320 / Glock / Desert Eagle)
    套筒 (slide) 独立，射击时后坐、空仓挂机时后退
    """
    C = d.model.get("color", (0.12, 0.12, 0.12))
    SL = d.model.get("slide", (0.16, 0.16, 0.17))
    L = d.model.get("length", 0.19)
    big = d.model.get("big", False)
    k = 1.25 if big else 1.0

    # ── 握把与套筒座底把 (Frame) ──
    m.box("body", (0, -0.052, 0.014), (0.030 * k, 0.105, 0.048 * k), C, rx=-14)
    # 握把防滑颗粒侧板
    for s in (-1, 1):
        m.box("body", (s * 0.016 * k, -0.052, 0.014), (0.002, 0.075, 0.035 * k), _shade(C, 0.8), rx=-14)
    m.box("body", (0, -0.002, -L * 0.35), (0.028 * k, 0.026, L * 0.75), C)
    m.box("body", (0, -0.026, -0.030), (0.010, 0.020, 0.052), C)           # 扳机护圈
    m.box("body", (0, -0.018, -0.020), (0.004, 0.018, 0.008), M_STEEL)     # 扳机
    # 空仓挂机柄与分解杆
    m.box("body", (-0.016 * k, 0.014, -0.020), (0.003, 0.008, 0.014), M_STEEL)

    # ── 套筒 (slide 组) ──
    sh = 0.035 * k
    slide_z = -L * 0.42 + 0.02
    m.box("slide", (0, 0.028, slide_z), (0.027 * k, sh, L), SL)
    # 抛壳窗凹陷与黄铜弹壳
    m.box("slide", (0.014 * k, 0.031, -0.015), (0.003, 0.014, 0.036), M_DARK)
    m.box("slide", (0.010 * k, 0.031, -0.015), (0.004, 0.010, 0.022), BRASS)
    # 前后防滑锯齿槽 (Front & Rear Cocking Serrations)
    for i in range(5):
        m.box("slide", (0, 0.028, 0.055 - i * 0.008), (0.029 * k, sh * 0.85, 0.003), _shade(SL, 0.65))
        m.box("slide", (0, 0.028, slide_z - L * 0.35 + i * 0.008), (0.029 * k, sh * 0.85, 0.003), _shade(SL, 0.65))

    front = slide_z - L / 2
    if big:
        # 沙漠之鹰经典顶部凸起导轨台
        m.box("slide", (0, 0.028 + sh / 2 + 0.004, slide_z), (0.014, 0.008, L), _shade(SL, 1.15))

    ry = 0.028 + sh / 2 + (0.008 if big else 0.0)
    m.rail_y = ry
    m.rail_z = 0.0

    # ── 手枪机瞄 (三点式氚光机械瞄具) ──
    m.box("slide", (0, ry + 0.006, 0.052), (0.022, 0.011, 0.008), M_DARK)
    m.box("slide", (-0.007, ry + 0.008, 0.052), (0.002, 0.004, 0.004), TRITIUM)
    m.box("slide", (0.007, ry + 0.008, 0.052), (0.002, 0.004, 0.004), TRITIUM)
    m.box("slide", (0, ry + 0.006, front + 0.012), (0.005, 0.011, 0.006), M_DARK)
    m.box("slide", (0, ry + 0.008, front + 0.012), (0.003, 0.004, 0.004), TRITIUM)

    m.sight_y = ry + 0.009
    m.eye_ref_z = 0.05
    m.relief = 0.38

    # ── 枪管与枪口 ──
    by = 0.028
    m.cyl("body", (0, by, front + 0.005), 0.009 * k, 0.024, M_DARK)
    bz = front
    if d.model.get("comp") and atts["muzzle"] == "muzzle_std":
        # G18C 枪口泄气补偿开孔
        m.box("slide", (0, by + 0.018, front + 0.025), (0.008, 0.006, 0.022), (0.02, 0.02, 0.02))

    muzzle_z = bz if atts["muzzle"] == "muzzle_std" else _add_muzzle(m, atts["muzzle"], front, by, 0.009, pistol=True)
    m.muzzle = (0, by, muzzle_z)

    # ── 弹匣 ──
    ext = 1.55 if (d.model.get("long_mag") or atts["magazine"] == "mag_ext") else 1.0
    _mag(m, "pistol", 0, -0.008, 0.012, (0.11, 0.11, 0.12), ext)

    if atts["optic"] == "rmr":
        # RMR 微型红点安装在套筒后部上方，放进 slide 组随套筒同步后坐
        before = len(m.parts["body"])
        _add_optic(m, "rmr", 0, pistol=True)
        moved = m.parts["body"][before:]
        m.parts["body"] = m.parts["body"][:before]
        m.parts["slide"].extend(moved)

    _add_underbarrel(m, atts["underbarrel"], -L * 0.55, -0.012, pistol=True)
    m.grip_r = (0.0, -0.045, 0.018)
    m.grip_l = (-0.012, -0.055, 0.008)
    m.bolt_pos = (0.0, 0.030, 0.04)
    m.length = 0.10 - muzzle_z


def _build_shotgun(m: GunModel, d, atts):
    """
    战术霰弹枪建模 (M870 / SPAS-12 / QBS-09)
    泵动护木 (pump) 独立，射击后泵动上膛
    """
    C = d.model.get("color", (0.12, 0.12, 0.12))
    F = d.model.get("furniture", C)
    B = d.model.get("barrel", 0.46)
    R = d.model.get("receiver", 0.25)
    stock = d.model.get("stock", "m4")

    # ── 握把与机匣 ──
    m.box("body", (0, -0.065, 0.030), (0.034, 0.105, 0.046), F, rx=18)
    m.box("body", (0, -0.032, -0.012), (0.014, 0.014, 0.065), M_DARK)
    m.box("body", (0, -0.018, -0.004), (0.004, 0.020, 0.008), M_STEEL)
    m.box("body", (0, 0.025, 0.04 - R / 2), (0.048, 0.072, R), C)
    # 底部装弹口 (弹仓托板)
    m.box("body", (0, -0.010, 0.04 - R / 2), (0.022, 0.008, R * 0.75), BRASS)

    # 顶部导轨
    ry = 0.062
    m.rail("body", ry, 0.04, 0.04 - R, w=0.024, col=M_RAIL)
    m.rail_y = ry + 0.004
    m.rail_z = 0.04 - R / 2

    # ── 枪管与平行管式弹仓 ──
    bz0 = 0.04 - R
    by = 0.042
    m.cyl("body", (0, by, bz0 - B / 2), 0.014, B, M_DARK, seg=16)
    # 下方加长管式弹仓
    mag_len = B * 0.88
    m.cyl("body", (0, by - 0.028, bz0 - mag_len / 2), 0.013, mag_len, _shade(C, 1.1), seg=14)
    # 枪管与弹仓前端固定联接环
    m.box("body", (0, by - 0.014, bz0 - mag_len + 0.015), (0.014, 0.035, 0.022), M_DARK)

    if d.model.get("heatshield"):
        # SPAS-12 / 战术防烫散热网罩 (带散热圆孔特征)
        m.box("body", (0, by + 0.014, bz0 - B * 0.35), (0.032, 0.022, B * 0.52), (0.22, 0.22, 0.24))

    # ── 泵动护木 (挂在 pump 组，泵动动画驱动) ──
    pz = bz0 - B * 0.36
    m.box("pump", (0, by - 0.028, pz), (0.054, 0.046, 0.16), F)
    # 战术防滑肋条
    for i in range(7):
        m.box("pump", (0, by - 0.028, pz - 0.065 + i * 0.022), (0.056, 0.048, 0.008), _shade(F, 0.7))
    m.pump_pos = (0, by - 0.048, pz)

    muzzle_z = _add_muzzle(m, atts["muzzle"], bz0 - B, by, 0.014)
    m.muzzle = (0, by, muzzle_z)

    # ── 枪托 ──
    if stock == "folding":
        # SPAS-12 经典折叠金属骨架托 (带标志性弯钩)
        m.box("body", (0, 0.065, 0.18), (0.018, 0.014, 0.26), M_STEEL)
        m.box("body", (0, 0.020, 0.31), (0.032, 0.095, 0.022), M_DARK)
        m.box("body", (0, 0.085, 0.31), (0.018, 0.040, 0.018), M_STEEL, rx=25)  # 提枪弯钩
    elif stock == "fixed":
        # 猎枪/警用固定工程塑料托
        m.box("body", (0, 0.010, 0.20), (0.042, 0.082, 0.28), F)
        m.box("body", (0, 0.000, 0.34), (0.048, 0.115, 0.024), M_DARK)
    else:
        # M4 伸缩托
        m.cyl("body", (0, 0.030, 0.19), 0.017, 0.22, M_DARK)
        m.box("body", (0, 0.018, 0.25), (0.044, 0.078, 0.13), F)
        m.box("body", (0, 0.015, 0.318), (0.046, 0.105, 0.020), M_DARK)

    # ── 瞄具 ──
    if atts["optic"] == "iron":
        # 珠形准星 / 鬼环瞄具 (Ghost Ring)
        m.box("body", (0, by + 0.020, bz0 - B + 0.02), (0.006, 0.010, 0.006), (0.95, 0.95, 0.95))
        m.box("body", (0, ry + 0.012, 0.00), (0.022, 0.014, 0.014), M_DARK)
        m.sight_y = ry + 0.014
        m.eye_ref_z = 0.0
        m.relief = 0.26
    else:
        _add_optic(m, atts["optic"], bz0 - B + 0.02)

    _add_underbarrel(m, atts["underbarrel"], pz, by - 0.065)
    m.grip_r = (0.0, -0.045, 0.030)
    m.grip_l = (0.0, by - 0.055, pz)
    m.length = 0.34 - muzzle_z


def build_gun_model(wid, atts) -> GunModel:
    d = WEAPONS[wid]
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
        draw_cylinder(x, y, z, 0.0095, 0.05, RED_SHELL, axis="z", segments=10)
        draw_cylinder(x, y, z + 0.022, 0.010, 0.012, BRASS, axis="z", segments=10)
    else:
        draw_cylinder(x, y, z, 0.005, 0.030, BRASS, axis="z", segments=8)
