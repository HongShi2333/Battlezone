"""
PlayerState —— 玩家的完整可序列化状态。
真人、机器人、远程玩家都用这个结构; 网络快照即为它的 to_dict()。
"""
import math
from core import settings as S
from weapons.weapon_state import WeaponInstance

# 姿态
STAND, CROUCH, PRONE = "stand", "crouch", "prone"
# 移动状态
M_IDLE, M_WALK, M_SPRINT, M_SLIDE, M_AIR, M_MANTLE = "idle", "walk", "sprint", "slide", "air", "mantle"


class PlayerState:
    def __init__(self, pid, name="Player", team=0, is_bot=False):
        self.pid = pid
        self.name = name
        self.team = team
        self.is_bot = is_bot
        self.alive = False
        self.health = float(S.MAX_HEALTH)
        self.pos = [0.0, 0.0, 0.0]          # 脚底位置
        self.vel = [0.0, 0.0, 0.0]
        self.yaw = 0.0
        self.pitch = 0.0
        self.on_ground = True
        self.stance = STAND
        self.move = M_IDLE
        self.eye_h = S.EYE_STAND
        # 动作计时器
        self.slide_t = 0.0
        self.slide_cd = 0.0
        self.crouch_hold = 0.0
        self.crouch_consumed = False
        self.prone_t = 0.0                  # 趴下/起身 过渡
        self.mantle_t = 0.0
        self.mantle_from = (0.0, 0.0, 0.0)
        self.mantle_to = (0.0, 0.0, 0.0)
        self.lean = 0.0
        self.ads = 0.0                      # 开镜进度 0..1
        self.ads_held = False
        self.sprint_cool = 0.0              # 冲刺→开火 延迟
        self.recoil_p = 0.0                 # 后坐力造成的视角偏移 (弧度)
        self.recoil_y = 0.0
        self.air_time = 0.0
        # 动画同步计数器 (渲染层检测变化来触发动画/音效)
        self.land_counter = 0
        self.land_speed = 0.0
        self.jump_counter = 0
        self.step_phase = 0.0
        # 武器
        self.weapons = []                   # [primary, secondary]
        self.active = 0
        self.last_buttons = 0
        self.last_seq = -1
        # 战斗
        self.kills = 0
        self.deaths = 0
        self.score = 0
        self.last_damage_t = 99.0
        self.respawn_t = 0.0
        self.spawn_protect = 0.0
        self.loadout = None                 # 最近一次部署的配置

    # ── 便捷属性 ──
    @property
    def weapon(self):
        if not self.weapons:
            return None
        return self.weapons[self.active % len(self.weapons)]

    def body_height(self):
        if self.move == M_SLIDE:
            return S.BODY_SLIDE
        return {STAND: S.BODY_STAND, CROUCH: S.BODY_CROUCH, PRONE: S.BODY_PRONE}[self.stance]

    def target_eye(self):
        if self.move == M_SLIDE:
            return S.EYE_SLIDE
        return {STAND: S.EYE_STAND, CROUCH: S.EYE_CROUCH, PRONE: S.EYE_PRONE}[self.stance]

    def hspeed(self):
        return math.hypot(self.vel[0], self.vel[2])

    # ── 序列化 ──
    def to_dict(self, full=True):
        d = dict(
            pid=self.pid, n=self.name, tm=self.team, bot=self.is_bot, al=self.alive,
            hp=round(self.health, 1), p=[round(v, 3) for v in self.pos], v=[round(v, 3) for v in self.vel],
            yw=round(self.yaw, 4), pt=round(self.pitch, 4), og=self.on_ground, st=self.stance, mv=self.move,
            eh=round(self.eye_h, 3), sl=round(self.slide_t, 3), ln=round(self.lean, 3), ads=round(self.ads, 3),
            rp=round(self.recoil_p, 4), ry=round(self.recoil_y, 4), act=self.active,
            lc=self.land_counter, ls=round(self.land_speed, 2), jc=self.jump_counter,
            k=self.kills, dt=self.deaths, sc=self.score, rt=round(self.respawn_t, 2),
            w=[w.to_dict() for w in self.weapons],
        )
        if full:
            d.update(slcd=round(self.slide_cd, 3), ch=round(self.crouch_hold, 3), cc=self.crouch_consumed,
                     prt=round(self.prone_t, 3), mt=round(self.mantle_t, 3), mf=self.mantle_from,
                     mto=self.mantle_to, adh=self.ads_held, spc=round(self.sprint_cool, 3),
                     at=round(self.air_time, 3), lb=self.last_buttons, seq=self.last_seq,
                     ldt=round(self.last_damage_t, 2), sp=round(self.spawn_protect, 2))
        return d

    def apply_dict(self, d):
        self.name, self.team, self.is_bot, self.alive = d["n"], d["tm"], d["bot"], d["al"]
        self.health = d["hp"]
        self.pos, self.vel = list(d["p"]), list(d["v"])
        self.yaw, self.pitch, self.on_ground = d["yw"], d["pt"], d["og"]
        self.stance, self.move, self.eye_h = d["st"], d["mv"], d["eh"]
        self.slide_t, self.lean, self.ads = d["sl"], d["ln"], d["ads"]
        self.recoil_p, self.recoil_y, self.active = d["rp"], d["ry"], d["act"]
        self.land_counter, self.land_speed, self.jump_counter = d["lc"], d["ls"], d["jc"]
        self.kills, self.deaths, self.score, self.respawn_t = d["k"], d["dt"], d["sc"], d["rt"]
        old = self.weapons
        self.weapons = [WeaponInstance.from_dict(wd, old[i] if i < len(old) else None)
                        for i, wd in enumerate(d["w"])]
        if "slcd" in d:
            self.slide_cd, self.crouch_hold, self.crouch_consumed = d["slcd"], d["ch"], d["cc"]
            self.prone_t, self.mantle_t = d["prt"], d["mt"]
            self.mantle_from, self.mantle_to = tuple(d["mf"]), tuple(d["mto"])
            self.ads_held, self.sprint_cool, self.air_time = d["adh"], d["spc"], d["at"]
            self.last_buttons, self.last_seq = d["lb"], d["seq"]
            self.last_damage_t, self.spawn_protect = d["ldt"], d["sp"]
