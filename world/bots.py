"""
机器人 AI —— 只生成 InputCommand, 与真人玩家共用 simulate_player。
这样机器人天然支持多人服务器 (服务器端运行 BotManager 即可)。
"""
import math
import heapq
import random
from core import settings as S
from core.commands import InputCommand, Btn
from core.mathutil import clamp, wrap_angle
from player.player_state import STAND, CROUCH, PRONE, M_SPRINT
from player.controller import eye_position
from weapons.definitions import WEAPONS, primary_weapons, secondary_weapons, PISTOL, RIFLE, SNIPER, SHOTGUN
from weapons.attachments import options_for, SLOTS, default_attachments

BOT_NAMES = ["Falck", "Irish", "Casper", "Boris", "Mackay", "Dozer", "Sundance", "Paik", "Angel",
             "Rao", "Lis", "Zain", "Blasco", "Crawford", "Hwang", "Kovac", "Lin", "Wang", "Chen",
             "Zhou", "Viper", "Ghost", "Havoc", "Nomad"]

PREF_RANGE = {PISTOL: 14, RIFLE: 28, SNIPER: 60, SHOTGUN: 8}


class NavGraph:
    """网格导航图 (启动时根据碰撞体自动生成)"""

    def __init__(self, col, half, spacing=4.0):
        self.nodes = []
        self.edges = []
        idx = {}
        n = int(half * 2 / spacing)
        for i in range(n + 1):
            for j in range(n + 1):
                x = -half + 2 + i * spacing
                z = -half + 2 + j * spacing
                if abs(x) > half - 1.5 or abs(z) > half - 1.5:
                    continue
                if col.body_free(x, 0.0, z, S.PLAYER_RADIUS * 1.6, S.BODY_STAND):
                    idx[(i, j)] = len(self.nodes)
                    self.nodes.append((x, z))
                    self.edges.append([])
        for (i, j), a in idx.items():
            for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
                b = idx.get((i + di, j + dj))
                if b is None:
                    continue
                ax, az = self.nodes[a]
                bx, bz = self.nodes[b]
                if self._clear(col, ax, az, bx, bz):
                    d = math.hypot(bx - ax, bz - az)
                    self.edges[a].append((b, d))
                    self.edges[b].append((a, d))

    @staticmethod
    def _clear(col, ax, az, bx, bz):
        dx, dz = bx - ax, bz - az
        l = math.hypot(dx, dz)
        px, pz = -dz / l * 0.45, dx / l * 0.45
        for h in (0.3, 1.2):
            for s in (-1, 1):
                if not col.line_clear((ax + px * s, h, az + pz * s), (bx + px * s, h, bz + pz * s)):
                    return False
        return True

    def nearest(self, x, z):
        best, bd = 0, 1e18
        for i, (nx, nz) in enumerate(self.nodes):
            d = (nx - x) ** 2 + (nz - z) ** 2
            if d < bd and self.edges[i]:
                best, bd = i, d
        return best

    def path(self, a, b):
        if a == b:
            return [b]
        goal = self.nodes[b]
        openq = [(0.0, a)]
        came = {a: None}
        g = {a: 0.0}
        while openq:
            _, cur = heapq.heappop(openq)
            if cur == b:
                break
            for nb, d in self.edges[cur]:
                ng = g[cur] + d
                if ng < g.get(nb, 1e18):
                    g[nb] = ng
                    came[nb] = cur
                    nx, nz = self.nodes[nb]
                    heapq.heappush(openq, (ng + math.hypot(goal[0] - nx, goal[1] - nz), nb))
        if b not in came:
            return []
        out = []
        c = b
        while c is not None:
            out.append(c)
            c = came[c]
        return out[::-1]


class BotBrain:
    def __init__(self, pid, world, nav, skill=0.5, seed=0):
        self.pid = pid
        self.world = world
        self.nav = nav
        self.skill = skill
        self.rng = random.Random(seed * 7919 + pid)
        self.seq = 0
        self.yaw = 0.0
        self.pitch = 0.0
        self.path = []
        self.target = None
        self.seen_t = 0.0
        self.lost_t = 0.0
        self.think_t = 0.0
        self.strafe = 1
        self.strafe_t = 0.0
        self.burst_t = 0.0
        self.pause_t = 0.0
        self.fire_toggle = False
        self.stuck_t = 0.0
        self.stuck_hits = 0
        self.last_pos = (0, 0, 0)
        self.err_y = 0.0
        self.err_p = 0.0
        self.want_stance = STAND
        self.stance_t = 0.0
        self.alert_pid = None
        self.alert_t = 0.0
        self.jump_pulse = 0
        self.slide_pulse = 0
        self.was_alive = False

    def alert(self, attacker_pid):
        self.alert_pid = attacker_pid
        self.alert_t = 2.5

    # ── 目标选择 ──
    def _find_target(self, p):
        best, bd = None, 1e9
        fx, fz = math.sin(self.yaw), -math.cos(self.yaw)
        for q in self.world.players.values():
            if not q.alive or q.team == p.team:
                continue
            dx, dz = q.pos[0] - p.pos[0], q.pos[2] - p.pos[2]
            d = math.hypot(dx, dz)
            if d > 95:
                continue
            in_fov = (dx * fx + dz * fz) / max(d, 0.01) > math.cos(math.radians(70))
            if not in_fov and not (self.alert_pid == q.pid and self.alert_t > 0) and d > 6:
                continue
            if d < bd and self.world.can_see(p, q):
                best, bd = q, d
        return best

    def _repath(self, p):
        a = self.nav.nearest(p.pos[0], p.pos[2])
        # 偏向地图中部与敌方区域
        enemy_z = -40 if p.team == S.TEAM_BLUE else 40
        for _ in range(6):
            gx = self.rng.uniform(-50, 50)
            gz = self.rng.uniform(-35, 35) * 0.8 + (enemy_z * 0.35 if self.rng.random() < 0.5 else 0)
            b = self.nav.nearest(gx, gz)
            path = self.nav.path(a, b)
            if len(path) > 1:
                self.path = path[1:]
                return
        self.path = []

    def command(self, dt):
        self.seq += 1
        p = self.world.players.get(self.pid)
        cmd = InputCommand(seq=self.seq, dt=dt, yaw=self.yaw, pitch=self.pitch)
        if p is None or not p.alive:
            self.was_alive = False
            return cmd
        if not self.was_alive:
            self.was_alive = True
            self.yaw = p.yaw
            self.path = []
            self.target = None
            self.want_stance = STAND
        w = p.weapon
        btn = 0
        self.alert_t -= dt
        self.think_t -= dt
        self.strafe_t -= dt
        self.stance_t -= dt

        # ── 感知 (低频) ──
        if self.think_t <= 0:
            self.think_t = 0.12 + self.rng.random() * 0.1
            t = self._find_target(p)
            if t is not None:
                if self.target is None or self.target.pid != t.pid:
                    self.seen_t = 0.0
                    spread = (1.0 - self.skill) * 9 + 2
                    self.err_y = math.radians(self.rng.uniform(-spread, spread))
                    self.err_p = math.radians(self.rng.uniform(-spread, spread) * 0.6)
                self.target = t
                self.lost_t = 0.0
            else:
                if self.target is not None:
                    self.lost_t += 0.15
                    if self.lost_t > 2.0 or not self.target.alive:
                        self.target = None
                        self.path = []

        tgt = self.target if (self.target and self.target.alive) else None
        move_f, move_r = 0.0, 0.0
        cat = w.defn.category if w else RIFLE

        if tgt is not None:
            self.seen_t += dt
            eye = eye_position(p)
            aim_h = tgt.eye_h - (0.05 if self.rng.random() < 0.15 + self.skill * 0.2 else 0.35)
            tx, ty, tz = tgt.pos[0], tgt.pos[1] + aim_h, tgt.pos[2]
            if tgt.stance == PRONE:
                ty = tgt.pos[1] + 0.25
            dx, dy, dz = tx - eye[0], ty - eye[1], tz - eye[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            # 提前量
            lead = dist / 400.0
            dx += tgt.vel[0] * lead
            dz += tgt.vel[2] * lead
            want_yaw = math.atan2(dx, -dz)
            want_pitch = math.atan2(dy, math.hypot(dx, dz))
            decay = math.exp(-dt * (1.2 + self.skill * 3.0))
            self.err_y *= decay
            self.err_p *= decay
            want_yaw += self.err_y - p.recoil_y * (0.4 + 0.5 * self.skill)
            want_pitch += self.err_p - p.recoil_p * (0.4 + 0.5 * self.skill)
            turn = math.radians(220 + 300 * self.skill) * dt
            dy_ = wrap_angle(want_yaw - self.yaw)
            self.yaw += clamp(dy_, -turn, turn)
            self.pitch += clamp(want_pitch - self.pitch, -turn, turn)
            aim_off = abs(wrap_angle(want_yaw - self.yaw)) + abs(want_pitch - self.pitch) + \
                abs(self.err_y) + abs(self.err_p)
            tolerance = max(0.012, math.atan2(0.45, dist)) * (2.0 - self.skill)
            reaction = 0.55 - self.skill * 0.3
            can_shoot = self.seen_t > reaction and aim_off < tolerance
            if self.world.can_see(p, tgt) is False:
                can_shoot = False
            # 开镜
            if dist > 12 or cat == SNIPER:
                if self.seen_t > reaction * 0.5:
                    btn |= Btn.ADS
            # 射击节奏
            if can_shoot and w:
                mode = w.fire_mode
                if mode == "auto":
                    if self.pause_t > 0:
                        self.pause_t -= dt
                    else:
                        btn |= Btn.FIRE
                        self.burst_t += dt
                        limit = 0.35 + 0.4 * self.rng.random() if dist > 20 else 0.9
                        if self.burst_t > limit:
                            self.burst_t = 0.0
                            self.pause_t = 0.2 + self.rng.random() * (0.2 + dist / 60)
                else:
                    self.fire_toggle = not self.fire_toggle
                    if self.fire_toggle and (cat != SNIPER or p.ads > 0.95):
                        if self.rng.random() < 0.35 + self.skill * 0.5:
                            btn |= Btn.FIRE
            # 战术移动
            pref = PREF_RANGE.get(cat, 25)
            if self.strafe_t <= 0:
                self.strafe = self.rng.choice((-1, 1, 1, -1, 0))
                self.strafe_t = 0.6 + self.rng.random() * 1.4
                r = self.rng.random()
                if cat == SNIPER and dist > 35 and r < 0.4:
                    self.want_stance = PRONE
                elif r < 0.3:
                    self.want_stance = CROUCH
                else:
                    self.want_stance = STAND
            move_r = self.strafe * (0.6 if p.ads > 0.5 else 1.0)
            if dist > pref * 1.3:
                move_f = 1.0
            elif dist < pref * 0.4:
                move_f = -0.7
            if self.want_stance == PRONE:
                move_r = 0.0
                move_f = 0.0
            if w and w.ammo == 0:
                btn |= Btn.RELOAD
            self.path = []
        else:
            # ── 巡逻 ──
            self.seen_t = 0.0
            self.want_stance = STAND
            if self.alert_t > 0 and self.alert_pid in self.world.players:
                a = self.world.players[self.alert_pid]
                ay = math.atan2(a.pos[0] - p.pos[0], -(a.pos[2] - p.pos[2]))
                self.yaw += clamp(wrap_angle(ay - self.yaw), -6 * dt, 6 * dt)
            if not self.path:
                self._repath(p)
            if self.path:
                nx, nz = self.nav.nodes[self.path[0]]
                dx, dz = nx - p.pos[0], nz - p.pos[2]
                d = math.hypot(dx, dz)
                if d < 1.4:
                    self.path.pop(0)
                else:
                    want = math.atan2(dx, -dz)
                    if self.alert_t <= 0:
                        self.yaw += clamp(wrap_angle(want - self.yaw), -5 * dt, 5 * dt)
                    rel = wrap_angle(want - self.yaw)
                    move_f = math.cos(rel)
                    move_r = math.sin(rel)
                    if abs(rel) < 0.5 and len(self.path) > 2:
                        btn |= Btn.SPRINT
                        # 偶尔滑铲
                        if p.move == M_SPRINT and self.rng.random() < 0.004:
                            self.slide_pulse = 2
            self.pitch *= 0.9
            if w and w.ammo < w.stats.mag_size * 0.4 and w.reserve > 0:
                btn |= Btn.RELOAD

        # ── 姿态 ──
        if self.slide_pulse > 0:
            self.slide_pulse -= 1
            if self.slide_pulse == 1:
                btn |= Btn.CROUCH
        elif p.stance != self.want_stance and self.stance_t <= 0 and not p.last_buttons & (Btn.CROUCH | Btn.PRONE):
            self.stance_t = 0.3
            if self.want_stance == PRONE:
                btn |= Btn.PRONE
            elif p.stance == PRONE:
                btn |= Btn.PRONE if self.want_stance == STAND else Btn.CROUCH
            else:
                btn |= Btn.CROUCH

        # ── 卡住检测 ──
        self.stuck_t += dt
        if self.stuck_t > 0.8:
            moved = math.dist(self.last_pos, p.pos)
            self.last_pos = tuple(p.pos)
            self.stuck_t = 0.0
            if abs(move_f) + abs(move_r) > 0.5 and moved < 0.5 and tgt is None:
                self.stuck_hits += 1
                self.jump_pulse = 2
                if self.stuck_hits >= 2:
                    self.path = []
                    self._repath(p)
                    self.stuck_hits = 0
            else:
                self.stuck_hits = 0
        if self.jump_pulse > 0:
            self.jump_pulse -= 1
            if self.jump_pulse == 1:
                btn |= Btn.JUMP

        cmd.yaw = self.yaw
        cmd.pitch = clamp(self.pitch, -1.4, 1.4)
        cmd.move_f = move_f
        cmd.move_r = move_r
        cmd.buttons = btn
        return cmd


def random_loadout(rng):
    prim = rng.choice(primary_weapons())
    sec = rng.choice(secondary_weapons())

    def rand_atts(w):
        atts = default_attachments(w)
        for slot in SLOTS:
            if rng.random() < 0.5:
                atts[slot] = rng.choice(options_for(w, slot)).id
        return atts

    return dict(primary=prim.id, primary_atts=rand_atts(prim),
                secondary=sec.id, secondary_atts=rand_atts(sec))


class BotManager:
    """服务器/单机端: 管理所有机器人"""

    def __init__(self, world, skill=0.5, seed=1):
        self.world = world
        self.nav = NavGraph(world.col, 60.0)
        self.brains = {}
        self.skill = skill
        self.rng = random.Random(seed)
        self._names = list(BOT_NAMES)
        self.rng.shuffle(self._names)

    def add_bot(self, pid, team):
        name = self._names[len(self.brains) % len(self._names)]
        self.world.add_player(pid, name, team, is_bot=True)
        self.brains[pid] = BotBrain(pid, self.world, self.nav,
                                    clamp(self.skill + self.rng.uniform(-0.15, 0.15), 0.05, 1.0), seed=pid)

    def remove_bot(self, pid):
        self.brains.pop(pid, None)
        self.world.remove_player(pid)

    def on_events(self, events):
        for e in events:
            if e["e"] == "hit" and e["v"] in self.brains and e["a"] >= 0:
                self.brains[e["v"]].alert(e["a"])

    def update(self, dt):
        """自动部署 + 生成命令; 返回 {pid: InputCommand}"""
        cmds = {}
        for pid, brain in self.brains.items():
            p = self.world.players.get(pid)
            if p and not p.alive and p.respawn_t <= 0:
                self.world.request_deploy(pid, random_loadout(self.rng))
            cmds[pid] = brain.command(dt)
        return cmds
