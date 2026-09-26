"""
World —— 权威游戏模拟 (无渲染依赖)。

职责:
  * 持有地图碰撞、所有玩家状态
  * apply_command(): 用 InputCommand 推进某个玩家
  * 命中判定 (射线 vs 地图 / 球形命中盒)、伤害、击杀、重生、比分
  * 产出可序列化事件 (events) 与快照 (snapshot)

多人模式下它只运行在服务器上 (客户端仅用 simulate_player 做本地预测)。
"""
import math
import random
from core import settings as S
from core.commands import InputCommand
from core.mathutil import v_add, v_mul, v_sub, v_dot, clamp
from player.player_state import PlayerState, STAND, CROUCH, PRONE, M_SLIDE
from player.controller import simulate_player, eye_position
from weapons.definitions import WEAPONS, primary_weapons, secondary_weapons
from weapons.attachments import sanitize, default_attachments
from weapons.weapon_state import WeaponInstance
from .collision import CollisionWorld
from .map_data import build_harbor

MAX_RANGE = 320.0
ZONE_HEAD, ZONE_BODY, ZONE_LIMB = "head", "body", "limb"


def hitboxes(p: PlayerState):
    """返回 [(zone, center, radius)] — 根据姿态变化"""
    x, y, z = p.pos
    if p.stance == PRONE and p.move != M_SLIDE:
        fx, fz = math.sin(p.yaw), -math.cos(p.yaw)
        pts = [(ZONE_HEAD, 0.72, 0.30, 0.15), (ZONE_BODY, 0.36, 0.25, 0.24), (ZONE_BODY, -0.02, 0.22, 0.23),
               (ZONE_LIMB, -0.45, 0.15, 0.17), (ZONE_LIMB, -0.85, 0.12, 0.16)]
        return [(zn, (x + fx * f, y + h, z + fz * f), r) for zn, f, h, r in pts]
    e = p.eye_h
    boxes = [(ZONE_HEAD, (x, y + e + 0.04, z), 0.15),
             (ZONE_BODY, (x, y + e - 0.33, z), 0.26),
             (ZONE_BODY, (x, y + e - 0.68, z), 0.24)]
    leg_top = e - 0.9
    if leg_top > 0.35:
        boxes.append((ZONE_LIMB, (x, y + leg_top * 0.72, z), 0.2))
        boxes.append((ZONE_LIMB, (x, y + 0.2, z), 0.18))
    else:
        boxes.append((ZONE_LIMB, (x, y + 0.25, z), 0.25))
    return boxes


def ray_sphere(o, d, c, r):
    oc = v_sub(c, o)
    t = v_dot(oc, d)
    if t < 0:
        return None
    d2 = v_dot(oc, oc) - t * t
    if d2 > r * r:
        return None
    return t - math.sqrt(r * r - d2)


def damage_at(stats, dist):
    if dist <= stats.range_near:
        return stats.damage_near
    if dist >= stats.range_far:
        return stats.damage_far
    t = (dist - stats.range_near) / (stats.range_far - stats.range_near)
    return stats.damage_near + (stats.damage_far - stats.damage_near) * t


class World:
    def __init__(self, map_builder=build_harbor, seed=0):
        self.map = map_builder()
        self.col = CollisionWorld(self.map.boxes)
        self.players = {}
        self.events = []
        self.tick = 0
        self.time = 0.0
        self.team_scores = [0, 0]
        self.match_over = False
        self.winner = -1
        self.reset_timer = 0.0
        self.rng = random.Random(seed)
        self.friendly_fire = False

    # ════════════════ 玩家管理 ════════════════
    def add_player(self, pid, name, team, is_bot=False):
        p = PlayerState(pid, name, team, is_bot)
        p.respawn_t = 0.0
        self.players[pid] = p
        self.events.append(dict(e="join", pid=pid, name=name, team=team))
        return p

    def remove_player(self, pid):
        if self.players.pop(pid, None):
            self.events.append(dict(e="leave", pid=pid))

    @staticmethod
    def validate_loadout(lo):
        lo = dict(lo or {})
        prim = lo.get("primary") if lo.get("primary") in WEAPONS else "m4a1"
        sec = lo.get("secondary") if lo.get("secondary") in WEAPONS else "p320"
        if WEAPONS[prim].slot != "primary":
            prim = "m4a1"
        if WEAPONS[sec].slot != "secondary":
            sec = "p320"
        return dict(primary=prim, secondary=sec,
                    primary_atts=sanitize(WEAPONS[prim], lo.get("primary_atts") or default_attachments(WEAPONS[prim])),
                    secondary_atts=sanitize(WEAPONS[sec], lo.get("secondary_atts") or default_attachments(WEAPONS[sec])))

    def request_deploy(self, pid, loadout):
        """客户端请求部署 (重生界面选完武器后)"""
        p = self.players.get(pid)
        if not p or p.alive or p.respawn_t > 0 or self.match_over:
            return False
        p.loadout = self.validate_loadout(loadout)
        self.spawn(p)
        return True

    def set_attachments(self, pid, slot_index, atts):
        """游戏内 Z 菜单修改配件"""
        p = self.players.get(pid)
        if not p or slot_index >= len(p.weapons):
            return False
        w = p.weapons[slot_index]
        changed = w.set_attachments(atts)
        if changed and p.loadout:
            key = "primary_atts" if slot_index == 0 else "secondary_atts"
            p.loadout[key] = dict(w.atts)
        return changed

    def spawn(self, p: PlayerState):
        pts = self.map.spawns[p.team]
        enemies = [q for q in self.players.values() if q.alive and q.team != p.team]

        def score(pt):
            if not enemies:
                return self.rng.random()
            return min(math.dist(pt, q.pos) for q in enemies) + self.rng.random() * 8

        pt = max(pts, key=score)
        lo = p.loadout or self.validate_loadout(None)
        p.loadout = lo
        p.weapons = [WeaponInstance(lo["primary"], lo["primary_atts"]),
                     WeaponInstance(lo["secondary"], lo["secondary_atts"])]
        p.active = 0
        p.pos = [pt[0] + self.rng.uniform(-0.6, 0.6), pt[1], pt[2]]
        p.vel = [0.0, 0.0, 0.0]
        p.yaw = 0.0 if p.team == S.TEAM_BLUE else math.pi
        p.pitch = 0.0
        p.health = float(S.MAX_HEALTH)
        p.alive = True
        p.stance = STAND
        p.move = "idle"
        p.eye_h = S.EYE_STAND
        p.ads = 0.0
        p.recoil_p = p.recoil_y = 0.0
        p.slide_t = p.mantle_t = p.prone_t = 0.0
        p.lean = 0.0
        p.spawn_protect = 2.0
        p.last_damage_t = 99.0
        self.events.append(dict(e="spawn", pid=p.pid, pos=list(p.pos), yaw=p.yaw))

    # ════════════════ 模拟 ════════════════
    def apply_command(self, pid, cmd: InputCommand):
        p = self.players.get(pid)
        if not p:
            return
        shots = simulate_player(p, cmd, self.col)
        for s in shots:
            self._resolve_shot(p, s)
        if p.alive and p.health <= 0:
            self._kill(p, None, None, False)

    def step(self, dt):
        """每 tick 调用一次 (在所有 apply_command 之后)"""
        self.tick += 1
        self.time += dt
        for p in self.players.values():
            if p.alive:
                p.last_damage_t += dt
                if p.last_damage_t > S.REGEN_DELAY and p.health < S.MAX_HEALTH:
                    p.health = min(S.MAX_HEALTH, p.health + S.REGEN_RATE * dt)
            else:
                p.respawn_t = max(0.0, p.respawn_t - dt)
        if self.match_over:
            self.reset_timer -= dt
            if self.reset_timer <= 0:
                self._reset_match()

    def _reset_match(self):
        self.match_over = False
        self.team_scores = [0, 0]
        for p in self.players.values():
            p.kills = p.deaths = p.score = 0
            p.alive = False
            p.respawn_t = 0.0
        self.events.append(dict(e="match_start"))

    # ════════════════ 命中判定 ════════════════
    def _resolve_shot(self, shooter: PlayerState, shot):
        w = shooter.weapons[shooter.active]
        stats = w.stats
        o = shot.origin
        per_victim = {}
        ends, normals, hitflags = [], [], []
        candidates = [q for q in self.players.values()
                      if q.alive and q.pid != shooter.pid and (self.friendly_fire or q.team != shooter.team)]
        for d in shot.dirs:
            wall = self.col.raycast(o, d, MAX_RANGE)
            wall_t = wall[0] if wall else MAX_RANGE
            best_t, best_q, best_zone = wall_t, None, None
            for q in candidates:
                # 宽相位: 射线到玩家中心的距离
                c = (q.pos[0], q.pos[1] + 0.9, q.pos[2])
                oc = v_sub(c, o)
                t = v_dot(oc, d)
                if t < 0 or t > best_t + 2:
                    continue
                if v_dot(oc, oc) - t * t > 2.2 * 2.2:
                    continue
                for zone, cen, r in hitboxes(q):
                    ht = ray_sphere(o, d, cen, r)
                    if ht is not None and ht < best_t:
                        # 头部优先 (同一球距离非常接近时)
                        best_t, best_q, best_zone = ht, q, zone
            end = v_add(o, v_mul(d, best_t))
            ends.append([round(end[0], 3), round(end[1], 3), round(end[2], 3)])
            if best_q is not None:
                dmg = damage_at(stats, best_t)
                if best_zone == ZONE_HEAD:
                    dmg *= w.defn.headshot_mult
                elif best_zone == ZONE_LIMB:
                    dmg *= w.defn.limb_mult
                acc = per_victim.setdefault(best_q.pid, [0.0, False, best_q])
                acc[0] += dmg
                acc[1] = acc[1] or best_zone == ZONE_HEAD
                normals.append(None)
                hitflags.append(best_q.pid)
            else:
                normals.append(list(wall[1]) if wall else None)
                hitflags.append(-1 if wall is None else -2)   # -1 空中, -2 墙面
        self.events.append(dict(e="shot", pid=shooter.pid, w=w.id, o=[round(v, 3) for v in o],
                                ends=ends, n=normals, h=hitflags, sup=stats.suppressed,
                                fh=stats.flash_hidden, sc=shot.counter))
        for vid, (dmg, head, q) in per_victim.items():
            self.damage(q, shooter, dmg, head, w.id)

    def damage(self, victim, attacker, amount, headshot, weapon_id):
        if not victim.alive or victim.spawn_protect > 0:
            return
        amount = round(amount, 1)
        victim.health -= amount
        victim.last_damage_t = 0.0
        self.events.append(dict(e="hit", a=attacker.pid if attacker else -1, v=victim.pid, d=amount,
                                hs=headshot, hp=round(max(0.0, victim.health), 1),
                                ap=[round(c, 2) for c in attacker.pos] if attacker else None,
                                k=victim.health <= 0))
        if victim.health <= 0:
            self._kill(victim, attacker, weapon_id, headshot)

    def _kill(self, victim, killer, weapon_id, headshot):
        victim.alive = False
        victim.health = 0.0
        victim.deaths += 1
        victim.respawn_t = S.RESPAWN_TIME
        victim.ads = 0.0
        if killer and killer.pid != victim.pid:
            killer.kills += 1
            killer.score += 100 + (25 if headshot else 0)
            self.team_scores[killer.team] += 1
        self.events.append(dict(e="kill", k=killer.pid if killer else -1, v=victim.pid, w=weapon_id,
                                hs=headshot, pos=[round(c, 2) for c in victim.pos]))
        if not self.match_over and max(self.team_scores) >= S.SCORE_LIMIT:
            self.match_over = True
            self.winner = 0 if self.team_scores[0] >= S.SCORE_LIMIT else 1
            self.reset_timer = 12.0
            self.events.append(dict(e="match_over", winner=self.winner))

    # ════════════════ 视线工具 (机器人用) ════════════════
    def can_see(self, a: PlayerState, b: PlayerState):
        ea = eye_position(a)
        tb = (b.pos[0], b.pos[1] + max(0.3, b.eye_h - 0.3), b.pos[2])
        return self.col.line_clear(ea, tb)

    # ════════════════ 网络快照 ════════════════
    def drain_events(self):
        ev, self.events = self.events, []
        return ev

    def snapshot(self, full_for=None):
        return dict(
            tick=self.tick, time=round(self.time, 3), scores=list(self.team_scores),
            mo=self.match_over, win=self.winner, rst=round(self.reset_timer, 2),
            players=[p.to_dict(full=(p.pid == full_for)) for p in self.players.values()],
        )

    def apply_snapshot(self, snap):
        self.tick = snap["tick"]
        self.time = snap["time"]
        self.team_scores = list(snap["scores"])
        self.match_over, self.winner, self.reset_timer = snap["mo"], snap["win"], snap["rst"]
        seen = set()
        for d in snap["players"]:
            pid = d["pid"]
            seen.add(pid)
            p = self.players.get(pid)
            if p is None:
                p = PlayerState(pid, d["n"], d["tm"], d["bot"])
                self.players[pid] = p
            p.apply_dict(d)
        for pid in list(self.players):
            if pid not in seen:
                del self.players[pid]
