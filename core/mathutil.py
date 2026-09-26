"""轻量数学工具 (纯 Python, 服务器端可用)"""
import math


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def approach(cur, target, rate_dt):
    """以指数方式逼近目标 (帧率无关)"""
    return target + (cur - target) * math.exp(-rate_dt)


def move_towards(cur, target, max_delta):
    if abs(target - cur) <= max_delta:
        return target
    return cur + math.copysign(max_delta, target - cur)


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_out_back(t, s=1.7):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def forward_vec(yaw, pitch):
    """yaw=0 朝 -Z, yaw 增大向右转; pitch 向上为正"""
    cp = math.cos(pitch)
    return (math.sin(yaw) * cp, math.sin(pitch), -math.cos(yaw) * cp)


def right_vec(yaw):
    return (math.cos(yaw), 0.0, math.sin(yaw))


def v_add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def v_sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def v_mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def v_dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def v_len(a): return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def v_norm(a):
    l = v_len(a)
    return (a[0] / l, a[1] / l, a[2] / l) if l > 1e-9 else (0.0, 0.0, 0.0)


def v_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def wrap_angle(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


# ── 确定性随机数 (客户端预测和服务器结果一致) ──
def hash_rand(*ints):
    """返回 [0,1) 的确定性伪随机数"""
    h = 2166136261
    for i in ints:
        h ^= (int(i) & 0xFFFFFFFF)
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= h >> 13
        h = (h * 0x5bd1e995) & 0xFFFFFFFF
        h ^= h >> 15
    return (h & 0xFFFFFF) / float(0x1000000)


def spread_dir(dir_vec, spread_deg, r1, r2):
    """在圆锥内对方向加随机偏移"""
    if spread_deg <= 0.0001:
        return dir_vec
    ang = math.radians(spread_deg) * math.sqrt(r1)
    phi = r2 * math.pi * 2
    d = v_norm(dir_vec)
    up = (0.0, 1.0, 0.0) if abs(d[1]) < 0.95 else (1.0, 0.0, 0.0)
    rx = v_norm(v_cross(d, up))
    ry = v_cross(rx, d)
    s = math.tan(ang)
    off = v_add(v_mul(rx, math.cos(phi) * s), v_mul(ry, math.sin(phi) * s))
    return v_norm(v_add(d, off))
