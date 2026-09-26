"""
无头测试: 动作系统 / 武器 / 网络确定性
    cd fps_game && python -m pytest tests -q      (或 python tests/test_mechanics.py)
"""
import os
import sys
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import settings as S
from core.commands import InputCommand, Btn
from world.world import World
from player.player_state import STAND, CROUCH, PRONE, M_SPRINT, M_SLIDE, M_MANTLE
from player.controller import simulate_player
from world.collision import Box, CollisionWorld

DT = S.TICK_DT


def flat_world():
    """空旷平地 + 一堵 1.2m 矮墙 (z=-10)"""
    w = World()
    w.col = CollisionWorld([Box(-50, -1, -50, 50, 0, 50, "ground"), Box(-3, 0, -10.5, 3, 1.2, -10.0, "lowwall")])
    return w


def spawn(w, loadout=None):
    p = w.add_player(1, "T", 0)
    w.request_deploy(1, loadout or {"primary": "m4a1", "secondary": "p320"})
    p.pos = [0.0, 0.0, 0.0]
    p.yaw = 0.0
    p.spawn_protect = 0
    return p


class Driver:
    def __init__(self, w, p):
        self.w, self.p, self.seq = w, p, 0

    def run(self, ticks, mf=0.0, mr=0.0, btn=0, yaw=0.0, pitch=0.0):
        for _ in range(ticks):
            self.seq += 1
            self.w.apply_command(self.p.pid, InputCommand(self.seq, DT, mf, mr, yaw, pitch, btn))
            self.w.step(DT)

    def tap(self, btn, **kw):
        self.run(1, btn=btn, **kw)
        self.run(1, **kw)


def test_sprint_faster_than_walk():
    w = flat_world(); p = spawn(w); d = Driver(w, p)
    d.run(40)  # 拔枪
    p.pos = [0.0, 0.0, 30.0]
    d.run(60, mf=1.0)
    walk = p.hspeed()
    d.run(60, mf=1.0, btn=Btn.SPRINT)
    assert p.move == M_SPRINT
    assert p.hspeed() > walk * 1.4


def test_slide_from_sprint_and_ends_crouched():
    w = flat_world(); p = spawn(w); d = Driver(w, p)
    d.run(40)
    p.pos = [0.0, 0.0, 30.0]
    d.run(60, mf=1.0, btn=Btn.SPRINT)
    d.run(1, mf=1.0, btn=Btn.SPRINT | Btn.CROUCH)
    assert p.move == M_SLIDE and p.hspeed() >= S.SLIDE_BOOST - 0.5
    d.run(int(S.SLIDE_DURATION / DT) + 10, mf=0.0)
    assert p.move != M_SLIDE and p.stance == CROUCH


def test_crouch_toggle_and_hold_prone():
    w = flat_world(); p = spawn(w); d = Driver(w, p)
    d.run(40)
    d.tap(Btn.CROUCH)
    assert p.stance == CROUCH
    d.tap(Btn.CROUCH)
    assert p.stance == STAND
    d.run(int(S.PRONE_HOLD_TIME / DT) + 3, btn=Btn.CROUCH)   # 长按 C
    assert p.stance == PRONE
    d.run(60)
    assert p.eye_h < S.EYE_CROUCH
    d.tap(Btn.PRONE)
    d.run(60)
    assert p.stance == STAND and abs(p.eye_h - S.EYE_STAND) < 0.05


def test_cannot_fire_while_prone_crawling():
    w = flat_world(); p = spawn(w); d = Driver(w, p)
    d.run(40)
    d.tap(Btn.PRONE)
    d.run(60)
    ammo = p.weapon.ammo
    d.run(30, mf=1.0, btn=Btn.FIRE)
    assert p.weapon.ammo == ammo


def test_mantle_low_wall():
    w = flat_world(); p = spawn(w); d = Driver(w, p)
    d.run(40)
    p.pos = [0.0, 0.0, -9.0]
    d.run(1, mf=1.0, btn=Btn.JUMP)
    assert p.move == M_MANTLE
    d.run(int(S.MANTLE_TIME / DT) + 5, mf=1.0)
    assert p.pos[1] > 1.1 or p.pos[2] < -10.5   # 站上了墙 / 翻过了墙


def test_reload_cycle():
    w = flat_world(); p = spawn(w); d = Driver(w, p)
    d.run(40)
    d.run(20, btn=Btn.FIRE)
    wpn = p.weapon
    assert wpn.ammo < wpn.stats.mag_size
    d.tap(Btn.RELOAD)
    assert wpn.state == "reload"
    d.run(int(wpn.stats.reload_time / DT) + 5)
    assert wpn.state == "idle" and wpn.ammo == wpn.stats.mag_size


def test_shotgun_shell_reload_and_pump():
    w = flat_world(); p = spawn(w, {"primary": "m870", "secondary": "g17"}); d = Driver(w, p)
    d.run(40)
    d.tap(Btn.FIRE)
    assert p.weapon.state == "cycle"          # 泵动
    d.run(60)
    d.tap(Btn.RELOAD)
    assert p.weapon.state == "shell"
    d.run(120)
    assert p.weapon.ammo == p.weapon.stats.mag_size


def test_attachment_change_updates_stats():
    w = flat_world(); p = spawn(w); d = Driver(w, p)
    d.run(40)
    base = p.weapon.stats.mag_size
    assert w.set_attachments(1, 0, dict(p.weapon.atts, magazine="mag_ext"))
    assert p.weapon.stats.mag_size > base and p.weapon.state == "attach"


def test_prediction_matches_server():
    """客户端预测与服务器权威模拟逐 tick 完全一致 (确定性)"""
    ws, wc = flat_world(), flat_world()
    ps, pc = spawn(ws), spawn(wc)
    pattern = [(1, 0, Btn.SPRINT), (1, 0, Btn.SPRINT | Btn.CROUCH), (0, 1, 0), (0, 0, Btn.FIRE | Btn.ADS),
               (-1, 0, Btn.JUMP), (0, 0, Btn.PRONE), (0, -1, 0), (0, 0, Btn.RELOAD)]
    for i in range(600):
        mf, mr, b = pattern[(i // 25) % len(pattern)]
        cmd = InputCommand(i, DT, mf, mr, math.sin(i * 0.01), 0.0, b)
        ws.apply_command(1, cmd)
        simulate_player(pc, cmd, wc.col)
    assert all(abs(a - b) < 1e-9 for a, b in zip(ps.pos, pc.pos))
    assert ps.weapon.ammo == pc.weapon.ammo and ps.stance == pc.stance


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
