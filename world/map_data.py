"""
地图: "HARBOR 2042" —— 港口工业区
由程序化的 AABB 组成; 服务器与客户端生成完全相同的数据。
材质字符串只影响渲染。
"""
import random
from .collision import Box

HALF = 62.0          # 地图半边长
WALL_H = 7.0


class MapData:
    def __init__(self, name):
        self.name = name
        self.boxes = []
        self.spawns = {0: [], 1: []}
        self.decor = []          # 仅渲染: (kind, params)
        self.lights = []

    def add(self, x0, y0, z0, x1, y1, z1, mat="concrete", solid=True):
        self.boxes.append(Box(x0, y0, z0, x1, y1, z1, mat, solid))

    def addc(self, cx, cz, sx, sy, sz, mat="concrete", y=0.0):
        """中心 + 尺寸"""
        self.add(cx - sx / 2, y, cz - sz / 2, cx + sx / 2, y + sy, cz + sz / 2, mat)


# ─────────────────────────── 构件 ───────────────────────────
def container(m, cx, cz, rot=False, color="red", level=0):
    L, H, W = 6.06, 2.59, 2.44
    sx, sz = (W, L) if rot else (L, W)
    m.addc(cx, cz, sx, H, sz, "container_" + color, y=level * H)


def barrier(m, cx, cz, rot=False):
    sx, sz = (0.6, 3.0) if rot else (3.0, 0.6)
    m.addc(cx, cz, sx, 0.85, sz, "barrier")


def sandbags(m, cx, cz, length=3.0, rot=False):
    sx, sz = (0.9, length) if rot else (length, 0.9)
    m.addc(cx, cz, sx, 0.95, sz, "sandbag")


def crate(m, cx, cz, s=1.2, level=0.0):
    m.addc(cx, cz, s, s, s, "crate", y=level)


def stairs(m, x, z, direction, steps, step_h=0.3, step_d=0.42, width=2.0, mat="metal"):
    """direction: (dx,dz) 单位方向, 楼梯向该方向上升"""
    dx, dz = direction
    for i in range(steps):
        top = step_h * (i + 1)
        cx = x + dx * (i + 0.5) * step_d
        cz = z + dz * (i + 0.5) * step_d
        sx = width if dx == 0 else step_d
        sz = width if dz == 0 else step_d
        m.add(cx - sx / 2, 0, cz - sz / 2, cx + sx / 2, top, cz + sz / 2, mat)


def wall_x(m, x0, x1, z, h, t=0.3, gaps=(), mat="building", door_h=2.6, windows=()):
    """沿 X 的墙, gaps=[(中心x, 宽)] 门洞, windows=[(中心x, 宽, 底, 顶)]"""
    cuts = sorted([(g[0] - g[1] / 2, g[0] + g[1] / 2, 0.0, door_h) for g in gaps] +
                  [(w[0] - w[1] / 2, w[0] + w[1] / 2, w[2], w[3]) for w in windows])
    cur = x0
    for a, b, lo, hi in cuts:
        if a > cur:
            m.add(cur, 0, z - t / 2, a, h, z + t / 2, mat)
        if lo > 0:
            m.add(a, 0, z - t / 2, b, lo, z + t / 2, mat)
        m.add(a, hi, z - t / 2, b, h, z + t / 2, mat)
        cur = b
    if cur < x1:
        m.add(cur, 0, z - t / 2, x1, h, z + t / 2, mat)


def wall_z(m, z0, z1, x, h, t=0.3, gaps=(), mat="building", door_h=2.6, windows=()):
    cuts = sorted([(g[0] - g[1] / 2, g[0] + g[1] / 2, 0.0, door_h) for g in gaps] +
                  [(w[0] - w[1] / 2, w[0] + w[1] / 2, w[2], w[3]) for w in windows])
    cur = z0
    for a, b, lo, hi in cuts:
        if a > cur:
            m.add(x - t / 2, 0, cur, x + t / 2, h, a, mat)
        if lo > 0:
            m.add(x - t / 2, 0, a, x + t / 2, lo, b, mat)
        m.add(x - t / 2, hi, a, x + t / 2, h, b, mat)
        cur = b
    if cur < z1:
        m.add(x - t / 2, 0, cur, x + t / 2, h, z1, mat)


# ─────────────────────────── 地图 ───────────────────────────
def build_harbor():
    m = MapData("HARBOR 2042")
    rng = random.Random(2042)

    # 地面 (多块, 不同材质用于视觉)
    m.add(-HALF - 5, -1.0, -HALF - 5, HALF + 5, 0.0, HALF + 5, "ground")

    # 外围围墙
    t = 1.0
    m.add(-HALF - t, 0, -HALF - t, HALF + t, WALL_H, -HALF, "perimeter")
    m.add(-HALF - t, 0, HALF, HALF + t, WALL_H, HALF + t, "perimeter")
    m.add(-HALF - t, 0, -HALF, -HALF, WALL_H, HALF, "perimeter")
    m.add(HALF, 0, -HALF, HALF + t, WALL_H, HALF, "perimeter")

    # ═══ 中央仓库 (两层, 可进入) ═══
    wx0, wx1, wz0, wz1, wh = -13.0, 13.0, -9.0, 9.0, 7.5
    wall_x(m, wx0, wx1, wz0, wh, gaps=[(-6, 3.6), (7, 3.6)], windows=[(0, 3.0, 4.2, 5.6)], door_h=3.4)
    wall_x(m, wx0, wx1, wz1, wh, gaps=[(-7, 3.6), (6, 3.6)], windows=[(0, 3.0, 4.2, 5.6)], door_h=3.4)
    wall_z(m, wz0, wz1, wx0, wh, gaps=[(0, 3.0)], windows=[(-5, 2.0, 1.2, 2.3), (5, 2.0, 1.2, 2.3)])
    wall_z(m, wz0, wz1, wx1, wh, gaps=[(0, 3.0)], windows=[(-5, 2.0, 1.2, 2.3), (5, 2.0, 1.2, 2.3)])
    m.add(wx0 - 0.3, wh, wz0 - 0.3, wx1 + 0.3, wh + 0.35, wz1 + 0.3, "roof")
    # 夹层平台 (3.3m) + 楼梯
    m.add(-12.8, 3.0, -8.8, -4.0, 3.3, -4.5, "metal_floor")
    m.add(4.0, 3.0, 4.5, 12.8, 3.3, 8.8, "metal_floor")
    stairs(m, 0.2, -5.6, (-1, 0), 10, step_h=0.33, step_d=0.42, width=2.0)
    stairs(m, -0.2, 5.6, (1, 0), 10, step_h=0.33, step_d=0.42, width=2.0)
    # 夹层护栏
    m.add(-12.8, 3.3, -4.6, -6.4, 4.3, -4.5, "railing")
    m.add(6.4, 3.3, 4.5, 12.8, 4.3, 4.6, "railing")
    # 仓库内部货物
    for (cx, cz) in [(-9, 2), (-7.6, 2), (-9, 3.4), (8, -3), (9.4, -3), (8.7, -1.6)]:
        crate(m, cx, cz, 1.35)
    crate(m, -8.3, 2.7, 1.2, level=1.35)
    m.addc(0, 0, 4.0, 1.1, 1.8, "crate_long")
    m.addc(-4.5, 5.5, 1.2, 2.2, 3.2, "shelf")
    m.addc(4.5, -5.5, 1.2, 2.2, 3.2, "shelf")

    # ═══ 集装箱堆场 (西侧) ═══
    colors = ["red", "blue", "green", "orange", "gray"]
    for i, (cx, cz, rot, lvl) in enumerate([
        (-30, -20, False, 0), (-30, -20, False, 1), (-30, -16.5, False, 0),
        (-38, -12, True, 0), (-34.8, -12, True, 0), (-34.8, -12, True, 1),
        (-26, -4, False, 0), (-44, 0, True, 0), (-44, 6.1, True, 0), (-44, 6.1, True, 1),
        (-30, 8, False, 0), (-30, 10.6, False, 0), (-30, 10.6, False, 1),
        (-22, 18, True, 0), (-38, 20, False, 0), (-38, 22.6, False, 0),
        (-50, -24, False, 0), (-50, -21.4, False, 0), (-50, -21.4, False, 1),
        (-20, -28, True, 0), (-52, 16, True, 0),
    ]):
        container(m, cx, cz, rot, colors[(i * 3 + int(cx)) % len(colors)], lvl)
    # 木箱台阶: 可以 "翻越" 上集装箱顶 (1.2m 木箱 → 2.59m 集装箱)
    for cx, cz in [(-26.3, -21.6), (-40.0, 8.0), (-34.0, 10.6), (-46.2, -21.4)]:
        crate(m, cx, cz, 1.2)

    # ═══ 集装箱堆场 (东侧) ═══
    for i, (cx, cz, rot, lvl) in enumerate([
        (30, 20, False, 0), (30, 20, False, 1), (30, 16.5, False, 0),
        (38, 12, True, 0), (34.8, 12, True, 0), (34.8, 12, True, 1),
        (26, 4, False, 0), (44, 0, True, 0), (44, -6.1, True, 0), (44, -6.1, True, 1),
        (30, -8, False, 0), (30, -10.6, False, 0), (30, -10.6, False, 1),
        (22, -18, True, 0), (38, -20, False, 0), (38, -22.6, False, 0),
        (50, 24, False, 0), (50, 21.4, False, 0), (50, 21.4, False, 1),
        (20, 28, True, 0), (52, -16, True, 0),
    ]):
        container(m, cx, cz, rot, colors[(i * 2 + 1) % len(colors)], lvl)
    for cx, cz in [(26.3, 21.6), (40.0, -8.0), (34.0, -10.6), (46.2, 21.4)]:
        crate(m, cx, cz, 1.2)

    # ═══ 瞭望塔 x2 (狙击位) ═══
    for sx, sz, d in [(-48, -44, (0, 1)), (48, 44, (0, -1))]:
        m.addc(sx, sz, 5.0, 4.5, 5.0, "tower")
        m.addc(sx, sz, 5.4, 0.25, 5.4, "metal_floor", y=4.5)
        # 护墙
        m.add(sx - 2.7, 4.75, sz - 2.7, sx + 2.7, 5.75, sz - 2.5, "railing")
        m.add(sx - 2.7, 4.75, sz + 2.5, sx + 2.7, 5.75, sz + 2.7, "railing")
        m.add(sx - 2.7, 4.75, sz - 2.5, sx - 2.5, 5.75, sz + 2.5, "railing")
        m.add(sx + 2.5, 4.75, sz - 2.5, sx + 2.7, 5.75, sz + 2.5, "railing")
        m.addc(sx, sz, 5.6, 0.2, 5.6, "roof", y=8.2)
        for ox in (-2.6, 2.6):
            for oz in (-2.6, 2.6):
                m.addc(sx + ox, sz + oz, 0.2, 3.5, 0.2, "metal", y=4.75)
        # 楼梯: 从塔前方上升到平台
        n = 15
        start_z = sz + d[1] * (-2.5 - n * 0.42) if d[1] > 0 else sz + 2.5 + n * 0.42
        stairs(m, sx + 3.6, start_z, d, n, step_h=0.3, step_d=0.42, width=1.6)
        # 楼梯顶到平台的连接
        m.add(sx + 2.5, 4.3, sz - 1.0 if d[1] > 0 else sz - 0.5, sx + 4.4, 4.5,
              sz + 0.5 if d[1] > 0 else sz + 1.0, "metal_floor")

    # ═══ 办公楼 (北 / 南) ═══
    for (bx, bz, flip) in [(0, -34, False), (0, 34, True)]:
        x0, x1, z0, z1, h = bx - 8, bx + 8, bz - 5, bz + 5, 4.0
        gz_front = z1 if not flip else z0
        gz_back = z0 if not flip else z1
        wall_x(m, x0, x1, gz_front, h, gaps=[(bx, 2.2)], windows=[(bx - 5, 2.2, 1.0, 2.3), (bx + 5, 2.2, 1.0, 2.3)])
        wall_x(m, x0, x1, gz_back, h, windows=[(bx - 4, 2.0, 1.0, 2.3), (bx + 4, 2.0, 1.0, 2.3)])
        wall_z(m, z0, z1, x0, h, gaps=[(bz, 2.0)])
        wall_z(m, z0, z1, x1, h, gaps=[(bz, 2.0)])
        wall_z(m, z0, z1 - 0.0, bx, h, gaps=[(bz + (2.5 if not flip else -2.5), 1.8)], mat="interior")
        m.add(x0 - 0.3, h, z0 - 0.3, x1 + 0.3, h + 0.3, z1 + 0.3, "roof")
        m.addc(bx - 5, bz, 1.6, 0.8, 0.8, "desk")
        m.addc(bx + 5, bz, 1.6, 0.8, 0.8, "desk")
        m.addc(bx - 3, bz + (3 if flip else -3), 0.8, 1.9, 2.4, "shelf")

    # ═══ 掩体: 水泥隔离墩 / 沙袋 / 矮墙 ═══
    for (cx, cz, r) in [(-8, -18, False), (8, -18, False), (-8, 18, False), (8, 18, False),
                        (-18, 0, True), (18, 0, True), (0, -22, False), (0, 22, False),
                        (-14, -26, True), (14, 26, True), (-22, 26, False), (22, -26, False),
                        (-40, -34, False), (40, 34, False), (-12, 44, False), (12, -44, False)]:
        barrier(m, cx, cz, r)
    for (cx, cz, l, r) in [(-20, -12, 4, False), (20, 12, 4, False), (-4, -46, 5, False), (4, 46, 5, False),
                           (-54, 0, 4, True), (54, 0, 4, True), (-24, 40, 3, False), (24, -40, 3, False),
                           (-17, 12, 3, True), (17, -12, 3, True)]:
        sandbags(m, cx, cz, l, r)
    # 可翻越矮墙 (1.2m)
    for (cx, cz, sx, sz) in [(-24, -34, 8, 0.5), (24, 34, 8, 0.5), (-36, 32, 0.5, 8), (36, -32, 0.5, 8),
                             (-10, -52, 10, 0.5), (10, 52, 10, 0.5)]:
        m.addc(cx, cz, sx, 1.2, sz, "lowwall")

    # 散落的木箱
    for _ in range(26):
        cx = rng.uniform(-55, 55)
        cz = rng.uniform(-48, 48)
        if abs(cx) < 15 and abs(cz) < 11:
            continue
        if abs(cz) > 28 and abs(cx) < 10:
            continue
        s = rng.choice([1.0, 1.2, 1.4])
        tmp = Box(cx - s / 2 - 0.4, 0, cz - s / 2 - 0.4, cx + s / 2 + 0.4, s, cz + s / 2 + 0.4)
        if any(tmp.overlaps(b.minx, 0.01, b.minz, b.maxx, b.maxy, b.maxz) for b in m.boxes[5:]):
            continue
        crate(m, cx, cz, s)
        if rng.random() < 0.3:
            crate(m, cx + rng.uniform(-0.1, 0.1), cz, s * 0.8, level=s)

    # 起重机 (装饰性, 高大地标)
    for (cx, cz) in [(-56, -56 + 10), (56, 56 - 10)]:
        for ox in (-2, 2):
            m.addc(cx + ox, cz, 0.8, 22, 0.8, "crane")
        m.addc(cx, cz, 5.0, 1.2, 1.2, "crane", y=21)
        m.add(cx - 2.5, 21, cz - 0.6, cx + 2.5 + (-20 if cx > 0 else 20) * 0 + 0, 22.2, cz + 0.6, "crane")

    # ═══ 出生点 ═══
    for i in range(8):
        m.spawns[0].append((-14 + i * 4.0, 0.05, 55.0 + (i % 2) * 2.0))
        m.spawns[1].append((-14 + i * 4.0, 0.05, -55.0 - (i % 2) * 2.0))

    return m
