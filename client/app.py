"""
客户端主程序: 窗口 / 主循环 / 固定步长模拟 / 渲染管线 / 界面状态机

  主循环 (每帧):
    1. 事件 → InputSampler / UI
    2. 鼠标视角 (每帧, 保证流畅)
    3. 固定步长 (60Hz): 生成 InputCommand → session.tick()  → 处理事件(音效/特效/HUD)
    4. 渲染: 世界 → 士兵 → 特效 → 第一人称武器 → HUD / 菜单
"""
import math
import os
import random
import sys
import time
import pygame
from pygame.locals import DOUBLEBUF, OPENGL
from OpenGL.GL import *

from core import settings as S
from core.commands import Btn
from core.mathutil import clamp, forward_vec, right_vec
from player.player_state import PRONE, M_SLIDE, M_SPRINT, CROUCH
from player.controller import eye_position
from weapons.definitions import WEAPONS
from net.session import LocalSession
from render.gl_util import generate_textures, begin_2d, end_2d, rect, perspective
from render.gun_models import GunModelCache
from render.world_renderer import WorldRenderer
from render.viewmodel import ViewModel
from render.camera import CameraRig, zoom_fov
from ui.widgets import UI, WHITE, GREY, ENEMY, GOLD, ACCENT
from ui.hud import HUD
from ui.menus import MainMenu, LoadoutScreen, PlusMenu, PauseMenu, DIFFICULTY
from .audio import Audio
from .input import InputSampler
from .prefs import Prefs


class ActionSounds:
    """根据本地玩家状态变化触发动作音效 (换弹各阶段 / 脚步 / 滑铲 / 落地...)"""

    def __init__(self, audio):
        self.a = audio
        self.prev = {}

    def update(self, p):
        if p is None or not p.alive or p.weapon is None:
            self.prev = {}
            return
        w = p.weapon
        pv = self.prev
        key = (w.id, w.state, w.phase)
        prog = w.progress
        last_prog = pv.get("prog", 0.0) if pv.get("key") == key else -1.0

        def cross(t):
            return last_prog < t <= prog

        if w.state == "reload":
            if cross(0.18):
                self.a.play("mag_out", 0.8)
            if cross(0.62):
                self.a.play("mag_in", 0.9)
            if w.empty_reload and cross(0.79):
                self.a.play("bolt", 0.8)
        elif w.state == "shell":
            if w.phase == "loop" and cross(0.5):
                self.a.play("shell", 0.8)
            if w.phase == "end" and w.empty_reload and (cross(0.3) or cross(0.55)):
                self.a.play("pump", 0.8)
        elif w.state == "cycle":
            if w.defn.fire_modes[w.mode_idx % len(w.defn.fire_modes)] == "bolt":
                if cross(0.3):
                    self.a.play("bolt_back", 0.8)
                if cross(0.62):
                    self.a.play("bolt", 0.8)
            else:
                if cross(0.2) or cross(0.6):
                    self.a.play("pump", 0.8)
        elif w.state == "draw" and pv.get("key") != key:
            self.a.play("switch", 0.7)
        elif w.state == "attach" and pv.get("key") != key:
            self.a.play("attach", 0.8)
        if pv.get("mode") is not None and pv.get("mode") != w.mode_idx and pv.get("wid") == w.id:
            self.a.play("firemode", 0.8)
        # 移动
        step_len = 2.3 if p.move != M_SPRINT else 2.9
        sidx = int(p.step_phase / step_len)
        if pv.get("step") is not None and sidx != pv["step"] and p.on_ground and p.stance != PRONE and p.move != M_SLIDE:
            vol = 0.55 if p.move == M_SPRINT else (0.2 if p.stance == CROUCH else 0.35)
            self.a.play("step%d" % random.randint(0, 3), vol, random.uniform(-0.15, 0.15))
        if p.move == M_SLIDE and pv.get("move") != M_SLIDE:
            self.a.play("slide", 0.8)
        if pv.get("lc") is not None and p.land_counter != pv["lc"]:
            self.a.play("land", min(1.0, 0.3 + p.land_speed * 0.08))
        if pv.get("jc") is not None and p.jump_counter != pv["jc"]:
            self.a.play("cloth", 0.7)
        if pv.get("stance") is not None and pv["stance"] != p.stance:
            self.a.play("cloth", 0.6)
        self.prev = dict(key=key, prog=prog, mode=w.mode_idx, wid=w.id, step=sidx, move=p.move,
                         lc=p.land_counter, jc=p.jump_counter, stance=p.stance)


class App:
    def __init__(self, width=S.SCREEN_WIDTH, height=S.SCREEN_HEIGHT, fullscreen=False, autotest=None,
                 connect=None):
        pygame.init()
        self.W, self.H = width, height
        try:
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
            flags = DOUBLEBUF | OPENGL | (pygame.FULLSCREEN if fullscreen else 0)
            self.screen = pygame.display.set_mode((width, height), flags)
        except pygame.error:
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 0)
            pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 0)
            self.screen = pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL)
        pygame.display.set_caption(S.WINDOW_TITLE)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glShadeModel(GL_SMOOTH)
        try:
            glEnable(GL_MULTISAMPLE)
        except Exception:
            pass
        self.clock = pygame.time.Clock()
        self.tex = generate_textures()
        self.prefs = Prefs()
        self.audio = Audio()
        self.ui = UI(width, height)
        self.ui.sound_cb = lambda: self.audio.play("ui", 0.5)
        self.cache = GunModelCache()
        self.hud = HUD(self.ui)
        self.plus = PlusMenu(self.ui, self.cache)
        self.loadout = LoadoutScreen(self.ui, self.cache, self.prefs)
        self.menu = MainMenu(self.ui, self.prefs)
        self.pause_menu = PauseMenu(self.ui, self.prefs)
        self.input = InputSampler()
        self.vm = ViewModel(self.cache, self.tex)
        self.rig = CameraRig()
        self.sounds = ActionSounds(self.audio)
        self.autotest = autotest
        self.running = True
        self.mode = "menu"          # menu / play / loadout
        self.paused = False
        self.show_scores = False
        self.acc = 0.0
        self.prev_pos = {}
        self.cur_pos = {}
        self.death_info = None
        self.death_t = 0.0
        self.info = ""
        self.mouse_grabbed = False
        self.frame_dt = 0.016
        self.t = 0.0
        self.menu_cam_t = 0.0
        # 主菜单背景: 一场机器人之间的实时战斗
        self.session = None
        self.bg_session = LocalSession("Spectator", 4, 4, 0.5)
        self.renderer = WorldRenderer(self.bg_session.world, self.tex)
        if connect:
            self.start_network(*connect)

    # ════════════════ 会话管理 ════════════════
    def start_single(self):
        d = self.prefs.data
        skill = DIFFICULTY[d.get("difficulty", 1)][1]
        self._set_session(LocalSession(d.get("name", "Player") or "Player", int(d.get("friendly_bots", 4)),
                                       int(d.get("enemy_bots", 5)), skill))

    def start_network(self, host, port):
        from net.net_session import NetworkSession
        try:
            s = NetworkSession(host, port, self.prefs.data.get("name", "Player"))
        except OSError as e:
            self.info = "连接失败: %s" % e
            return
        self._set_session(s)

    def _set_session(self, s):
        if self.session:
            self.session.close()
        self.session = s
        self.renderer.world = s.world
        self.renderer.ents.clear()
        self.renderer.corpses.clear()
        self.renderer.tracers.clear()
        self.renderer.decals.clear()
        self.hud = HUD(self.ui)
        self.mode = "loadout"
        self.paused = False
        self.death_info = None
        self.acc = 0.0

    def end_session(self):
        if self.session:
            self.session.close()
        self.session = None
        self.renderer.world = self.bg_session.world
        self.renderer.ents.clear()
        self.renderer.corpses.clear()
        self.mode = "menu"
        self.plus.close()

    @property
    def me(self):
        if not self.session:
            return None
        return self.session.world.players.get(self.session.local_pid)

    # ════════════════ 主循环 ════════════════
    def run(self):
        while self.running:
            dt = min(0.1, self.clock.tick(S.FPS_CAP) / 1000.0)
            if self.autotest:
                dt = 1 / 60.0
            self.frame_dt = dt
            self.t += dt
            self.hud.fps = self.clock.get_fps()
            self._events()
            self._update(dt)
            self._render(dt)
            pygame.display.flip()
            if self.autotest:
                self.autotest.step(self)
        if self.session:
            self.session.close()
        self.prefs.save()
        pygame.quit()

    def _events(self):
        clicked = right = False
        playing = self.mode == "play" and not self.paused
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if self.plus.is_open:
                        self.plus.close()
                    elif self.mode == "play" and self.me and self.me.alive:
                        self.paused = not self.paused
                    elif self.mode == "menu" and self.menu.page != "main":
                        self.menu.page = "main"
                elif e.key == pygame.K_z and self.mode in ("play", "loadout") and not self.paused:
                    if self.plus.is_open:
                        self.plus.close()
                    elif self.mode == "play" and self.me and self.me.alive:
                        self._open_plus_ingame()
                    elif self.mode == "loadout":
                        self.loadout.open_plus(self.plus)
                elif e.key == pygame.K_F1:
                    self.hud.show_help = not self.hud.show_help
                    self.hud.help_t = 30.0
                elif e.key in (pygame.K_RETURN, pygame.K_SPACE) and self.mode == "loadout" and not self.plus.is_open:
                    self._deploy()
                elif e.key == pygame.K_BACKSPACE and self.mode == "menu":
                    self.menu.backspace()
                elif e.key == pygame.K_TAB:
                    self.show_scores = True
            elif e.type == pygame.KEYUP and e.key == pygame.K_TAB:
                self.show_scores = False
            elif e.type == pygame.TEXTINPUT and self.mode == "menu":
                self.menu.text_input(e.text)
            elif e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    clicked = True
                elif e.button == 3:
                    right = True
            if playing and not self.plus.is_open:
                self.input.handle_event(e)
        mx, my = pygame.mouse.get_pos()
        self.ui.begin_frame(mx, my, clicked, right)

    def _open_plus_ingame(self):
        p = self.me
        tabs = []
        for i, label in enumerate(("主武器", "副武器")):
            if i < len(p.weapons):
                w = p.weapons[i]
                tabs.append((label, w.id, dict(w.atts), (lambda idx, wid: (lambda a: self._apply_atts(idx, wid, a)))(i, w.id)))
        self.plus.open(tabs, p.active, in_game=True)

    def _apply_atts(self, idx, wid, atts):
        self.session.set_attachments(idx, atts)
        self.loadout.set_atts(wid, atts)

    def _deploy(self):
        p = self.me
        if p is None or p.alive or p.respawn_t > 0:
            return
        self.session.deploy(self.loadout.loadout())
        self.plus.close()

    def _grab(self, on):
        if on != self.mouse_grabbed:
            self.mouse_grabbed = on
            pygame.event.set_grab(on)
            pygame.mouse.set_visible(not on)
            pygame.mouse.get_rel()

    # ════════════════ 更新 ════════════════
    def _update(self, dt):
        # 背景战斗 (主菜单)
        if self.mode == "menu":
            self._grab(False)
            self._tick_session(self.bg_session, dt, spectator=True)
            return
        s = self.session
        if s is None:
            return
        p = self.me
        alive = p is not None and p.alive
        want_grab = self.mode == "play" and alive and not self.paused and not self.plus.is_open
        self._grab(want_grab and not self.autotest)
        if want_grab:
            dx, dy = pygame.mouse.get_rel()
            if self.autotest:
                dx, dy = self.autotest.mouse
            sens = self.prefs.data.get("sens", 1.0) * (self.rig.fov / self.rig.base_fov) ** 0.9
            self.input.look(dx, dy, sens)
        else:
            self.input.last_dx = self.input.last_dy = 0
            pygame.mouse.get_rel()
        self.rig.base_fov = self.prefs.data.get("fov", S.FOV_BASE)
        if not (self.paused and not s.is_network):
            self._tick_session(s, dt)
        p = self.me
        # 模式切换
        if p is not None:
            if p.alive:
                if self.mode == "loadout":
                    self.mode = "play"
                    self.plus.close()
                self.death_info = None
            else:
                if self.mode == "play":
                    self.paused = False
                    if self.death_info is None:
                        self.mode = "loadout"
                    else:
                        self.death_t += dt
                        if self.death_t > 2.6:
                            self.mode = "loadout"
                            self.plus.close()
        self.hud.update(dt)
        self.sounds.update(p if self.mode == "play" else None)
        if p is not None and p.alive:
            self.vm.team_color = (0.30, 0.33, 0.26) if p.team == 0 else (0.36, 0.32, 0.25)
            self.vm.update(dt, p, self.input.last_dx, self.input.last_dy)

    def _tick_session(self, s, dt, spectator=False):
        self.acc += dt
        n = 0
        world = s.world
        while self.acc >= S.TICK_DT and n < 5:
            self.acc -= S.TICK_DT
            n += 1
            self.prev_pos = {pid: tuple(q.pos) for pid, q in world.players.items()}
            p = world.players.get(s.local_pid)
            allow_move = not spectator and self.mode == "play" and not self.paused
            allow_combat = allow_move and not self.plus.is_open
            cmd = self.input.build(S.TICK_DT, allow_move, allow_combat)
            if spectator:
                cmd.buttons = 0
                cmd.move_f = cmd.move_r = 0
            s.tick(cmd)
            self._process_events(s.poll_events(), s, spectator)
        if n >= 5:
            self.acc = 0.0
        alpha = self.acc / S.TICK_DT
        self.cur_pos = {}
        for pid, q in world.players.items():
            a = self.prev_pos.get(pid)
            if a is None or math.dist(a, q.pos) > 3:
                self.cur_pos[pid] = tuple(q.pos)
            else:
                self.cur_pos[pid] = tuple(a[i] + (q.pos[i] - a[i]) * alpha for i in range(3))
        self.renderer.update_entities(dt, world, s.local_pid, self.cur_pos)
        self.renderer.update_effects(dt)

    def _process_events(self, events, s, spectator):
        world = s.world
        lp = s.local_pid
        me = world.players.get(lp)
        listener = eye_position(me) if (me and me.alive) else self.renderer.cam_pos
        lyaw = self.input.yaw if not spectator else 0.0
        for e in events:
            if not spectator:
                self.hud.on_event(e, lp, world)
            t = e["e"]
            if t == "shot":
                shooter = world.players.get(e["pid"])
                wdef = WEAPONS.get(e["w"])
                if not wdef:
                    continue
                local = e["pid"] == lp and not spectator
                o = e["o"]
                if local and me:
                    f = forward_vec(me.yaw + me.recoil_y, me.pitch + me.recoil_p)
                    r = right_vec(me.yaw)
                    k = 0.0 if me.ads > 0.6 else 0.1
                    o = (o[0] + f[0] * 0.6 + r[0] * k, o[1] + f[1] * 0.6 - 0.08 * (1 - me.ads), o[2] + f[2] * 0.6 + r[2] * k)
                else:
                    if shooter:
                        f = forward_vec(shooter.yaw, shooter.pitch)
                        o = (o[0] + f[0] * 0.7, o[1] - 0.15 + f[1] * 0.7, o[2] + f[2] * 0.7)
                    if not e.get("sup"):
                        self.renderer.add_world_flash(o, 0.5 if e.get("fh") else 1.0)
                ends = e["ends"]
                step = max(1, len(ends) // 4)
                for i, end in enumerate(ends):
                    if i % step == 0 and not (local and me and me.ads > 0.9 and wdef.category == "sniper"):
                        self.renderer.add_tracer(o, end, wdef.tracer_color)
                    h = e["h"][i]
                    if h == -2:
                        self.renderer.add_impact(end, e["n"][i], "wall", 4 if len(ends) > 1 else 7)
                    elif h is not None and h >= 0:
                        self.renderer.add_impact(end, None, "blood")
                # 音效
                snd = "shot_suppressed" if e.get("sup") else "shot_" + wdef.sound
                if local:
                    self.audio.play(snd, 0.85)
                else:
                    self.audio.play_at(snd, o, listener, lyaw, 150, 0.9,
                                       far_name=None if e.get("sup") else "far_" + wdef.sound)
                    # 子弹掠过
                    if me and me.alive and shooter and shooter.team != me.team and not spectator:
                        end = ends[0]
                        if self._near_miss(o, end, listener):
                            self.audio.play("whiz", 0.6)
            elif t == "hit" and not spectator:
                if e["a"] == lp and e["v"] != lp:
                    self.audio.play("kill" if e["k"] else ("headshot" if e["hs"] else "hit"), 0.8)
                if e["v"] == lp:
                    self.audio.play("hurt", 0.7)
                    self.rig.hurt(e["d"])
            elif t == "kill":
                v = world.players.get(e["v"])
                if v:
                    self.renderer.add_corpse(v, e["pos"])
                if e["v"] == lp and not spectator:
                    k = world.players.get(e["k"])
                    self.death_info = dict(killer=k.name if k else "", kteam=k.team if k else -1,
                                           w=WEAPONS[e["w"]].name if e.get("w") in WEAPONS else "",
                                           hs=e["hs"], kpid=e["k"], pos=list(e["pos"]),
                                           dist=math.dist(k.pos, e["pos"]) if k else 0)
                    self.death_t = 0.0
            elif t == "spawn" and e["pid"] == lp and not spectator:
                self.input.yaw = e["yaw"]
                self.input.pitch = 0.0
                self.audio.play("deploy", 0.6)
                self.rig = CameraRig()
                self.rig.base_fov = self.prefs.data.get("fov", S.FOV_BASE)
                self.hud.help_t = max(self.hud.help_t, 0.0)
            elif t == "match_over" and not spectator:
                win = e["winner"]
                self.hud.notices.append(["%s 获胜!" % S.TEAM_NAMES[win], "新一局将在 12 秒后开始", 8.0, GOLD])

    @staticmethod
    def _near_miss(o, end, ear):
        dx, dy, dz = end[0] - o[0], end[1] - o[1], end[2] - o[2]
        L = math.sqrt(dx * dx + dy * dy + dz * dz) or 1
        ux, uy, uz = dx / L, dy / L, dz / L
        ex, ey, ez = ear[0] - o[0], ear[1] - o[1], ear[2] - o[2]
        t = ex * ux + ey * uy + ez * uz
        if t < 0 or t > L:
            return False
        cx, cy, cz = o[0] + ux * t - ear[0], o[1] + uy * t - ear[1], o[2] + uz * t - ear[2]
        return cx * cx + cy * cy + cz * cz < 2.5 * 2.5

    # ════════════════ 渲染 ════════════════
    def _render(self, dt):
        W, H = self.W, self.H
        glViewport(0, 0, W, H)
        if self.mode == "menu":
            self._render_overview(dt, self.bg_session)
            begin_2d(W, H)
            res = self.menu.draw(dt, self.info)
            end_2d()
            if res:
                if res[0] == "quit":
                    self.running = False
                elif res[0] == "single":
                    self.start_single()
                elif res[0] == "connect":
                    self.start_network(res[1], res[2])
            return
        s = self.session
        p = self.me
        if p is not None and p.alive and self.mode == "play":
            self._render_fps(dt, p)
        elif self.mode == "play" and self.death_info:
            self._render_deathcam(dt)
        else:
            self._render_overview(dt, s)
        # ── 2D ──
        begin_2d(W, H)
        world = s.world
        if self.mode == "play":
            if p is not None and p.alive:
                self.hud.draw(p, world, self.renderer, self.vm, self.rig.fov, self.input.yaw,
                              s.status_text() if s.is_network else "")
            elif self.death_info:
                self._death_overlay()
                self.hud.draw(None, world, self.renderer, self.vm, self.rig.fov, self.input.yaw)
            if self.plus.is_open:
                self.plus.draw(dt)
            if self.paused:
                r = self.pause_menu.draw()
                if r == "resume":
                    self.paused = False
                elif r == "redeploy":
                    self.paused = False
                    if isinstance(s, LocalSession) and p:
                        s.world._kill(p, None, None, False)
                        p.respawn_t = 0.0
                        self.death_info = None
                        self.mode = "loadout"
                elif r == "menu":
                    self.prefs.save()
                    end_2d()
                    self.end_session()
                    return
        elif self.mode == "loadout":
            if p is None:
                self.ui.label(s.status_text() or "连接中...", W / 2, H / 2, 20, WHITE, align="center")
                if self.ui.button(30, H - 70, 150, 40, "返回主菜单", size=14):
                    end_2d()
                    self.end_session()
                    return
            else:
                r = self.loadout.draw(dt, p.respawn_t, p.team, self.plus, s.status_text())
                if self.plus.is_open:
                    self.plus.draw(dt)
                elif r == "deploy":
                    self._deploy()
                elif r == "menu":
                    end_2d()
                    self.end_session()
                    return
        if self.show_scores and self.mode != "menu":
            self.hud.draw_scoreboard(world, s.local_pid)
        end_2d()

    def _render_fps(self, dt, p):
        W, H = self.W, self.H
        world = self.session.world
        ipos = self.cur_pos.get(p.pid, tuple(p.pos))
        real = p.pos
        p.pos = list(ipos)
        eye_raw = eye_position(p, world.col)
        p.pos = real
        st = p.weapon.stats if p.weapon else None
        zoom = st.zoom if st else 1.0
        eye, yo, po, roll, fov = self.rig.update(dt, p, zoom, self.vm.visual_ads, eye_raw)
        yaw = self.input.yaw + p.recoil_y + yo
        pitch = self.input.pitch + p.recoil_p + po
        if self.session.is_network:
            yaw = p.yaw + p.recoil_y + yo
            pitch = p.pitch + p.recoil_p + po
        self.renderer.setup_camera(eye, yaw, pitch, roll, fov, W, H)
        self.renderer.draw_world(eye)
        self.renderer.draw_soldiers(world, self.session.local_pid, self.cache, dt)
        self.renderer.draw_effects()
        scoped = st is not None and st.scope_overlay and self.vm.visual_ads > 0.93
        self.vm.draw(p, W, H, hide_for_scope=scoped)

    def _render_overview(self, dt, s):
        """主菜单 / 部署界面背景: 环绕战场的航拍镜头"""
        W, H = self.W, self.H
        self.menu_cam_t += dt * 0.05
        a = self.menu_cam_t
        eye = (math.cos(a) * 58, 26 + math.sin(a * 0.7) * 4, math.sin(a) * 58)
        yaw = math.atan2(-eye[0], eye[2])
        pitch = -math.atan2(eye[1] - 2, math.hypot(eye[0], eye[2]))
        self.renderer.setup_camera(eye, yaw, pitch, 0.0, 60, W, H)
        self.renderer.draw_world(eye)
        self.renderer.draw_soldiers(s.world, s.local_pid, self.cache, dt, show_local=False)
        self.renderer.draw_effects()

    def _render_deathcam(self, dt):
        W, H = self.W, self.H
        di = self.death_info
        world = self.session.world
        pos = di["pos"]
        k = world.players.get(di["kpid"])
        t = min(1.0, self.death_t / 1.2)
        eye = (pos[0], pos[1] + 0.5 + 2.0 * t, pos[2])
        if k and k.alive and k.pid != self.session.local_pid:
            e = self.renderer.ents.get(k.pid)
            kp = e["pos"] if e else k.pos
            dx, dy, dz = kp[0] - eye[0], kp[1] + 1.2 - eye[1], kp[2] - eye[2]
            yaw = math.atan2(dx, -dz)
            pitch = math.atan2(dy, math.hypot(dx, dz))
            fov = 70 - 30 * t
        else:
            yaw, pitch, fov = self.input.yaw, -0.6 * t, 70
        self.renderer.setup_camera(eye, yaw, pitch, 8 * (1 - t), fov, W, H)
        self.renderer.draw_world(eye)
        self.renderer.draw_soldiers(world, self.session.local_pid, self.cache, dt)
        self.renderer.draw_effects()

    def _death_overlay(self):
        ui = self.ui
        W, H = self.W, self.H
        di = self.death_info
        rect(0, 0, W, H, (0.25, 0.0, 0.0), 0.22)
        ui.label("阵亡", W / 2, H * 0.68, 34, WHITE, align="center", bold=True)
        if di["killer"]:
            txt = "被 %s 击杀  ·  %s  ·  %.0f 米%s" % (di["killer"], di["w"], di["dist"], "  ·  爆头" if di["hs"] else "")
            ui.label(txt, W / 2, H * 0.68 + 46, 17, ENEMY if di["kteam"] != (self.me.team if self.me else 0) else WHITE,
                     align="center")
        ui.label("即将进入部署界面...", W / 2, H * 0.68 + 76, 14, GREY, align="center")

    # ── 截图 (自动测试) ──
    def screenshot(self, path):
        data = glReadPixels(0, 0, self.W, self.H, GL_RGB, GL_UNSIGNED_BYTE)
        surf = pygame.image.fromstring(data, (self.W, self.H), "RGB", True)
        pygame.image.save(surf, path)
