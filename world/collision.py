"""
碰撞 / 射线检测 (纯 Python, 服务器可用)。
地图由轴对齐包围盒 (AABB) 组成, 使用均匀网格做宽相位加速。
"""
import math
from core.settings import STEP_HEIGHT

EPS = 1e-4


class Box:
    __slots__ = ("minx", "miny", "minz", "maxx", "maxy", "maxz", "mat", "idx", "solid")

    def __init__(self, minx, miny, minz, maxx, maxy, maxz, mat="concrete", solid=True):
        self.minx, self.miny, self.minz = min(minx, maxx), min(miny, maxy), min(minz, maxz)
        self.maxx, self.maxy, self.maxz = max(minx, maxx), max(miny, maxy), max(minz, maxz)
        self.mat = mat
        self.idx = -1
        self.solid = solid

    def overlaps(self, a0, a1, a2, b0, b1, b2):
        return (a0 < self.maxx and b0 > self.minx and a1 < self.maxy and b1 > self.miny
                and a2 < self.maxz and b2 > self.minz)


class CollisionWorld:
    CELL = 6.0

    def __init__(self, boxes):
        self.boxes = boxes
        self.grid = {}
        for i, b in enumerate(boxes):
            b.idx = i
            if not b.solid:
                continue
            for cx in range(int(math.floor(b.minx / self.CELL)), int(math.floor(b.maxx / self.CELL)) + 1):
                for cz in range(int(math.floor(b.minz / self.CELL)), int(math.floor(b.maxz / self.CELL)) + 1):
                    self.grid.setdefault((cx, cz), []).append(b)

    def query(self, minx, minz, maxx, maxz):
        c = self.CELL
        out = {}
        for cx in range(int(math.floor(minx / c)), int(math.floor(maxx / c)) + 1):
            for cz in range(int(math.floor(minz / c)), int(math.floor(maxz / c)) + 1):
                cell = self.grid.get((cx, cz))
                if cell:
                    for b in cell:
                        out[b.idx] = b
        return out.values()

    # ── AABB 重叠 ──
    def overlap_box(self, x0, y0, z0, x1, y1, z1):
        for b in self.query(x0, z0, x1, z1):
            if b.overlaps(x0, y0, z0, x1, y1, z1):
                return b
        return None

    def body_free(self, x, y, z, r, h):
        return self.overlap_box(x - r, y + EPS, z - r, x + r, y + h, z + r) is None

    # ── 角色移动 (分轴解算 + 自动上台阶) ──
    def move(self, pos, vel, dt, r, h, on_ground):
        x, y, z = pos
        vx, vy, vz = vel
        dx, dy, dz = vx * dt, vy * dt, vz * dt
        n = max(1, int(math.ceil(max(abs(dx), abs(dz), abs(dy)) / (r * 0.7))))
        dx, dy, dz = dx / n, dy / n, dz / n
        stepped = 0.0
        was_ground = on_ground
        for _ in range(n):
            # —— X ——
            if dx:
                x += dx
                for _i in range(3):
                    b = self.overlap_box(x - r, y + EPS, z - r, x + r, y + h, z + r)
                    if not b:
                        break
                    rise = b.maxy - y
                    if on_ground and 0 < rise <= STEP_HEIGHT and self.body_free(x, b.maxy + EPS, z, r, h):
                        y = b.maxy + EPS
                        stepped += rise
                        continue
                    x = (b.minx - r - EPS) if dx > 0 else (b.maxx + r + EPS)
                    vx = 0.0
                    dx = 0.0
            # —— Z ——
            if dz:
                z += dz
                for _i in range(3):
                    b = self.overlap_box(x - r, y + EPS, z - r, x + r, y + h, z + r)
                    if not b:
                        break
                    rise = b.maxy - y
                    if on_ground and 0 < rise <= STEP_HEIGHT and self.body_free(x, b.maxy + EPS, z, r, h):
                        y = b.maxy + EPS
                        stepped += rise
                        continue
                    z = (b.minz - r - EPS) if dz > 0 else (b.maxz + r + EPS)
                    vz = 0.0
                    dz = 0.0
            # —— Y ——
            if dy:
                y += dy
                b = self.overlap_box(x - r, y, z - r, x + r, y + h, z + r)
                if b:
                    if dy < 0:
                        y = b.maxy
                        on_ground = True
                    else:
                        y = b.miny - h - EPS
                    vy = 0.0
                    dy = 0.0
                elif dy < 0:
                    on_ground = False
        # 贴地: 下楼梯时不腾空
        if was_ground and not on_ground and vy <= 0:
            for b in self.query(x - r, z - r, x + r, z + r):
                if (b.maxy <= y + EPS and y - b.maxy <= STEP_HEIGHT + 0.05 and
                        b.minx < x + r and b.maxx > x - r and b.minz < z + r and b.maxz > z - r):
                    if self.body_free(x, b.maxy, z, r, h):
                        y = b.maxy
                        on_ground = True
                        vy = 0.0
                        break
        return (x, y, z), (vx, vy, vz), on_ground, stepped

    # ── 射线 ──
    def raycast(self, o, d, maxdist):
        """返回 (距离, 法线, box) 或 None"""
        ex, ey, ez = o[0] + d[0] * maxdist, o[1] + d[1] * maxdist, o[2] + d[2] * maxdist
        cand = self.query(min(o[0], ex), min(o[2], ez), max(o[0], ex), max(o[2], ez))
        best = maxdist
        best_n = None
        best_b = None
        inv = [1.0 / c if abs(c) > 1e-12 else 1e12 for c in d]
        for b in cand:
            t0, t1 = 0.0, best
            n = None
            ok = True
            for axis, (mn, mx) in enumerate(((b.minx, b.maxx), (b.miny, b.maxy), (b.minz, b.maxz))):
                oa = o[axis]
                ia = inv[axis]
                ta = (mn - oa) * ia
                tb = (mx - oa) * ia
                sign = -1.0
                if ta > tb:
                    ta, tb = tb, ta
                    sign = 1.0
                if ta > t0:
                    t0 = ta
                    n = (axis, sign)
                if tb < t1:
                    t1 = tb
                if t0 > t1:
                    ok = False
                    break
            if ok and n is not None and t0 < best:
                best = t0
                best_n = n
                best_b = b
        if best_b is None:
            return None
        nv = [0.0, 0.0, 0.0]
        nv[best_n[0]] = best_n[1]
        return best, tuple(nv), best_b

    def line_clear(self, a, b):
        dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 1e-6:
            return True
        return self.raycast(a, (dx / dist, dy / dist, dz / dist), dist) is None

    def safe_offset(self, origin, offset, margin=0.12):
        """把偏移量限制在墙体前 (侧身 / 趴下时的眼睛位置)"""
        l = math.sqrt(offset[0] ** 2 + offset[1] ** 2 + offset[2] ** 2)
        if l < 1e-6:
            return offset
        d = (offset[0] / l, offset[1] / l, offset[2] / l)
        hit = self.raycast(origin, d, l + margin)
        if hit:
            l2 = max(0.0, hit[0] - margin)
            return (d[0] * l2, d[1] * l2, d[2] * l2)
        return offset

    def ledge_for_mantle(self, x, y, z, fx, fz, r, lo, hi, need_h):
        """在前方寻找可翻越的平台顶面, 返回落点或 None (多个探测距离, 近处优先)"""
        for probe in (0.25, 0.5, 0.8):
            px, pz = x + fx * (r + probe), z + fz * (r + probe)
            top = None
            for b in self.query(px - 0.1, pz - 0.1, px + 0.1, pz + 0.1):
                if b.minx <= px <= b.maxx and b.minz <= pz <= b.maxz:
                    if b.maxy - y > hi:
                        top = None
                        break
                    rise = b.maxy - y
                    if lo <= rise <= hi and (top is None or b.maxy > top):
                        top = b.maxy
            if top is None:
                continue
            # 头顶必须空旷 (从当前位置到平台上空)
            if not self.body_free(x, y + 0.05, z, r * 0.9, top - y + need_h * 0.6):
                return None
            for push in (0.3, 0.55, 0.8):
                d = probe + push
                tx, tz = x + fx * (r + d), z + fz * (r + d)
                if self.body_free(tx, top + 0.01, tz, r * 0.9, need_h):
                    # 路径上方不能有阻挡
                    if self.line_clear((x, top + need_h * 0.5, z), (tx, top + need_h * 0.5, tz)):
                        return (tx, top + 0.01, tz)
            return None
        return None
