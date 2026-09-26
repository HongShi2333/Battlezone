"""战斗 HUD: 准星 / 命中反馈 / 受击方向 / 小地图 / 比分 / 击杀信息 / 弹药 / 生命 / 瞄具覆盖"""
import math
import time
from OpenGL.GL import *
from core import settings as S
from core.mathutil import clamp, smoothstep
from player.player_state import STAND, CROUCH, PRONE, M_SPRINT, M_SLIDE, M_MANTLE, M_AIR
from player.controller import current_spread, eye_position
from weapons.definitions import WEAPONS, CATEGORY_NAMES
from weapons.attachments import ATTACHMENTS, SLOTS
from render.gl_util import rect, rect_outline, rect_grad, line, circle, arc
from .widgets import ACCENT, WHITE, GREY, ENEMY, FRIEND, GOLD, PANEL, c255

MODE_NAMES = {"auto": "全自动", "semi": "半自动", "burst": "点射", "bolt": "手动枪机", "pump": "泵动"}
MOVE_NAMES = {M_SPRINT: "冲刺", M_SLIDE: "滑铲", M_MANTLE: "翻越", M_AIR: "空中"}
STANCE_NAMES = {STAND: "站立", CROUCH: "半蹲", PRONE: "趴下"}


class HUD:
    def __init__(self, ui):
        self.ui = ui
        self.hit_t = 0.0
        self.hit_kill = False
        self.hit_head = False
        self.dmg_dirs = []          # [(world_angle, t)]
        self.killfeed = []          # [(killer, kteam, weapon, victim, vteam, hs, t)]
        self.notices = []           # [(text, sub, t, color)]
        self.hurt_flash = 0.0
        self.spotted = {}           # pid -> 剩余时间
        self.show_help = True
        self.help_t = 14.0
        self.fps = 0.0
        self.minimap_boxes = None

    # ── 事件 ──
    def on_event(self, e, local_pid, world):
        t = e["e"]
        if t == "hit":
            if e["a"] == local_pid and e["v"] != local_pid:
                self.hit_t = 0.28
                self.hit_kill = e["k"]
                self.hit_head = e["hs"]
            if e["v"] == local_pid and e.get("ap"):
                me = world.players.get(local_pid)
                if me:
                    ang = math.atan2(e["ap"][0] - me.pos[0], -(e["ap"][2] - me.pos[2]))
                    self.dmg_dirs.append([ang, 1.6])
                    self.hurt_flash = min(1.0, self.hurt_flash + e["d"] / 45)
        elif t == "kill":
            k = world.players.get(e["k"])
            v = world.players.get(e["v"])
            wname = WEAPONS[e["w"]].name if e.get("w") in WEAPONS else "—"
            self.killfeed.append([k.name if k else "", k.team if k else -1, wname,
                                  v.name if v else "?", v.team if v else -1, e["hs"], 6.0,
                                  e["k"] == local_pid or e["v"] == local_pid])
            self.killfeed = self.killfeed[-6:]
            if e["k"] == local_pid and e["v"] != local_pid:
                self.notices.append(["击杀  " + (v.name if v else ""), "+%d" % (100 + (25 if e["hs"] else 0)) +
                                     ("  爆头" if e["hs"] else ""), 2.6, GOLD if e["hs"] else WHITE])
                self.notices = self.notices[-3:]
        elif t == "shot":
            if not e.get("sup"):
                self.spotted[e["pid"]] = 2.5

    def update(self, dt):
        self.hit_t = max(0.0, self.hit_t - dt)
        self.hurt_flash = max(0.0, self.hurt_flash - dt * 0.8)
        for d in self.dmg_dirs:
            d[1] -= dt
        self.dmg_dirs = [d for d in self.dmg_dirs if d[1] > 0]
        for k in self.killfeed:
            k[6] -= dt
        self.killfeed = [k for k in self.killfeed if k[6] > 0]
        for n in self.notices:
            n[2] -= dt
        self.notices = [n for n in self.notices if n[2] > 0]
        for pid in list(self.spotted):
            self.spotted[pid] -= dt
            if self.spotted[pid] <= 0:
                del self.spotted[pid]
        self.help_t -= dt

    # ════════════════ 主绘制 ════════════════
    def draw(self, p, world, renderer, vm, fov, view_yaw, status_text=""):
        ui = self.ui
        W, H = ui.w, ui.h
        cx, cy = W / 2, H / 2
        w = p.weapon if p else None
        if p and p.alive and w:
            st = w.stats
            scoped = st.scope_overlay and vm.visual_ads > 0.9
            if scoped:
                self._scope(st, vm.visual_ads)
            elif vm.visual_ads > 0.85 and st.reticle in ("dot", "holo"):
                self._reddot(st.reticle, (vm.visual_ads - 0.85) / 0.15)
            if not scoped:
                self._crosshair(p, w, fov)
            self._hitmarker(cx, cy)
            self._damage_dirs(cx, cy, view_yaw)
        self._name_tags(p, world, renderer)
        # 低血量暗角
        if p and p.alive:
            low = clamp((55 - p.health) / 55, 0, 1)
            a = max(low * 0.55, self.hurt_flash * 0.5)
            if a > 0.01:
                self._vignette(a)
        self._minimap(p, world, view_yaw)
        self._scores(world)
        self._killfeed()
        self._notices(cx, cy)
        if p and p.alive:
            self._weapon_panel(p, w)
            self._health_panel(p)
            self._prompts(p, w)
        ui.label("FPS %d" % self.fps, W - 10, H - 20, 12, GREY, align="right", shadow=False)
        if status_text:
            ui.label(status_text, W - 70, H - 20, 12, GREY, align="right", shadow=False)
        if self.help_t > 0 and self.show_help:
            self._help(min(1.0, self.help_t))

    # ── 准星 (随散布扩张) ──
    def _crosshair(self, p, w, fov):
        cx, cy = self.ui.w / 2, self.ui.h / 2
        if p.move == M_SPRINT or p.move == M_MANTLE:
            circle(cx, cy, 2, WHITE, 0.6, 12)
            return
        a = 1.0 - smoothstep(p.ads * 1.4)
        if a <= 0.02:
            return
        spread = current_spread(p, w)
        px = math.tan(math.radians(spread)) / math.tan(math.radians(fov / 2)) * (self.ui.h / 2)
        gap = max(5.0, px)
        if w.defn.category == "shotgun" and w.stats.pellets > 1:
            circle(cx, cy, gap, WHITE, 0.7 * a, 40, filled=False, width=1.5)
            circle(cx, cy, 1.6, WHITE, a, 8)
            return
        L = 9
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            line(cx + dx * gap + 1, cy + dy * gap + 1, cx + dx * (gap + L) + 1, cy + dy * (gap + L) + 1,
                 (0, 0, 0), 0.5 * a, 2)
            line(cx + dx * gap, cy + dy * gap, cx + dx * (gap + L), cy + dy * (gap + L), WHITE, 0.95 * a, 2)
        circle(cx, cy, 1.3, WHITE, 0.9 * a, 8)

    def _hitmarker(self, cx, cy):
        if self.hit_t <= 0:
            return
        a = self.hit_t / 0.28
        col = ENEMY if self.hit_kill else (GOLD if self.hit_head else WHITE)
        s0, s1 = 7, 16 if self.hit_kill else 13
        wdt = 3 if self.hit_kill else 2
        for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            line(cx + dx * s0, cy + dy * s0, cx + dx * s1, cy + dy * s1, col, a, wdt)

    def _damage_dirs(self, cx, cy, yaw):
        for ang, t in self.dmg_dirs:
            rel = ang - yaw
            a = min(1.0, t)
            center = rel - math.pi / 2
            arc(cx, cy, 110, center - 0.28, center + 0.28, (1.0, 0.2, 0.1), a * 0.9, 6, 12)

    def _reddot(self, kind, a):
        cx, cy = self.ui.w / 2, self.ui.h / 2
        a = clamp(a, 0, 1)
        if kind == "holo":
            circle(cx, cy, 22, (1.0, 0.2, 0.15), 0.85 * a, 48, filled=False, width=1.6)
            for ang in (0, math.pi / 2, math.pi, math.pi * 1.5):
                line(cx + math.cos(ang) * 22, cy + math.sin(ang) * 22, cx + math.cos(ang) * 27,
                     cy + math.sin(ang) * 27, (1.0, 0.2, 0.15), 0.85 * a, 1.6)
        circle(cx, cy, 5, (1.0, 0.25, 0.2), 0.25 * a, 16)
        circle(cx, cy, 2.2, (1.0, 0.2, 0.15), a, 12)

    def _scope(self, st, ads):
        W, H = self.ui.w, self.ui.h
        cx, cy = W / 2, H / 2
        a = clamp((ads - 0.9) / 0.1, 0, 1)
        R = H * 0.45
        # 外圈黑色遮罩 (多边形环)
        glColor4f(0, 0, 0, a)
        glBegin(GL_TRIANGLE_STRIP)
        seg = 64
        big = max(W, H) * 1.2
        for i in range(seg + 1):
            ang = i / seg * math.pi * 2
            glVertex2f(cx + math.cos(ang) * R, cy + math.sin(ang) * R)
            glVertex2f(cx + math.cos(ang) * big, cy + math.sin(ang) * big)
        glEnd()
        # 镜片边缘暗化
        for i in range(6):
            circle(cx, cy, R - i * 3, (0, 0, 0), 0.12 * a, 64, filled=False, width=4)
        col = (0.02, 0.02, 0.02)
        if st.reticle == "mildot":
            line(cx - R, cy, cx - 18, cy, col, a, 2)
            line(cx + 18, cy, cx + R, cy, col, a, 2)
            line(cx, cy - R, cx, cy - 18, col, a, 2)
            line(cx, cy + 18, cx, cy + R, col, a, 2)
            line(cx - R, cy, cx - R * 0.55, cy, col, a, 5)
            line(cx + R * 0.55, cy, cx + R, cy, col, a, 5)
            line(cx, cy + R * 0.55, cx, cy + R, col, a, 5)
            for i in range(1, 6):
                d = i * R * 0.08
                circle(cx + d, cy, 2, col, a, 8)
                circle(cx - d, cy, 2, col, a, 8)
                circle(cx, cy + d, 2, col, a, 8)
                circle(cx, cy - d, 2, col, a, 8)
            circle(cx, cy, 1.5, (1.0, 0.15, 0.1), a, 8)
        else:
            # ACOG 红色 V 形 + 测距刻度
            rc = (1.0, 0.25, 0.1)
            line(cx - 12, cy + 10, cx, cy, rc, a, 2.5)
            line(cx, cy, cx + 12, cy + 10, rc, a, 2.5)
            line(cx, cy + 14, cx, cy + R * 0.5, col, a, 1.5)
            for i in range(1, 6):
                yy = cy + 14 + i * R * 0.07
                ww = 16 - i * 2
                line(cx - ww, yy, cx + ww, yy, col, a, 1.5)
            line(cx - R, cy, cx - R * 0.25, cy, col, a, 1.5)
            line(cx + R * 0.25, cy, cx + R, cy, col, a, 1.5)
        self.ui.label("%gx" % st.zoom, cx + R - 30, cy + R - 40, 14, GREY, alpha=a)

    def _vignette(self, a):
        W, H = self.ui.w, self.ui.h
        b = 140
        red = (0.7, 0.0, 0.0)
        rect_grad(0, 0, W, b, red, red, a, 0)
        rect_grad(0, H - b, W, b, red, red, 0, a)
        rect_grad(0, 0, b, H, red, red, a, 0, horizontal=True)
        rect_grad(W - b, 0, b, H, red, red, 0, a, horizontal=True)

    # ── 名字标签 ──
    def _name_tags(self, p, world, renderer):
        if not p:
            return
        ui = self.ui
        cx, cy = ui.w / 2, ui.h / 2
        eye = eye_position(p)
        for q in world.players.values():
            if q.pid == p.pid or not q.alive:
                continue
            e = renderer.ents.get(q.pid)
            if not e:
                continue
            head = (e["pos"][0], e["pos"][1] + e["eye"] + 0.45, e["pos"][2])
            sp = renderer.project(head)
            if sp is None:
                continue
            x, y, dist = sp
            if q.team == p.team:
                if dist > 70:
                    continue
                a = clamp(1.2 - dist / 70, 0.3, 1)
                self._diamond(x, y, 6, FRIEND, a)
                if dist < 30:
                    ui.label(q.name, x, y - 22, 13, FRIEND, alpha=a, align="center")
            else:
                aimed = abs(x - cx) < 45 and abs(y - cy) < 90 and dist < 90
                spotted = q.pid in self.spotted
                if (aimed or spotted) and world.col.line_clear(eye, head):
                    self._diamond(x, y, 6, ENEMY, 0.9)
                    if aimed:
                        ui.label(q.name, x, y - 22, 13, ENEMY, align="center")

    def _diamond(self, x, y, s, col, a):
        glColor4f(0, 0, 0, a * 0.5)
        glBegin(GL_QUADS)
        glVertex2f(x, y - s - 1.5); glVertex2f(x + s + 1.5, y); glVertex2f(x, y + s + 1.5); glVertex2f(x - s - 1.5, y)
        glColor4f(col[0], col[1], col[2], a)
        glVertex2f(x, y - s); glVertex2f(x + s, y); glVertex2f(x, y + s); glVertex2f(x - s, y)
        glEnd()

    # ── 小地图 ──
    def _minimap(self, p, world, yaw):
        ui = self.ui
        X, Y, SZ = 18, 18, 200
        scale = SZ / 90.0
        rect(X, Y, SZ, SZ, (0.03, 0.05, 0.07), 0.72)
        if self.minimap_boxes is None:
            self.minimap_boxes = [(b.minx, b.minz, b.maxx, b.maxz, b.maxy) for b in world.map.boxes
                                  if b.mat not in ("ground", "roof") and b.maxy > 0.5 and b.maxx - b.minx < 60]
        if p is None:
            return
        px, pz = p.pos[0], p.pos[2]
        glEnable(GL_SCISSOR_TEST)
        glScissor(X, ui.h - Y - SZ, SZ, SZ)
        glPushMatrix()
        glTranslatef(X + SZ / 2, Y + SZ / 2, 0)
        glRotatef(-math.degrees(yaw), 0, 0, 1)
        glScalef(scale, scale, 1)
        glTranslatef(-px, -pz, 0)
        if getattr(self, "_mm_list", None) is None:
            self._mm_list = glGenLists(1)
            glNewList(self._mm_list, GL_COMPILE)
            glColor4f(0.13, 0.15, 0.17, 0.9)
            glBegin(GL_QUADS)
            glVertex2f(-62, -62); glVertex2f(62, -62); glVertex2f(62, 62); glVertex2f(-62, 62)
            for x0, z0, x1, z1, h in self.minimap_boxes:
                g = 0.28 + min(0.3, h * 0.04)
                glColor4f(g, g + 0.02, g + 0.04, 0.85)
                glVertex2f(x0, z0); glVertex2f(x1, z0); glVertex2f(x1, z1); glVertex2f(x0, z1)
            glEnd()
            glEndList()
        glCallList(self._mm_list)
        glPopMatrix()
        # 玩家点
        cyaw, syaw = math.cos(-yaw), math.sin(-yaw)
        for q in world.players.values():
            if not q.alive or q.pid == p.pid:
                continue
            if q.team != p.team and q.pid not in self.spotted:
                continue
            dx, dz = (q.pos[0] - px) * scale, (q.pos[2] - pz) * scale
            rx = dx * cyaw - dz * syaw
            rz = dx * syaw + dz * cyaw
            sx, sy = X + SZ / 2 + rx, Y + SZ / 2 + rz
            col = FRIEND if q.team == p.team else ENEMY
            circle(sx, sy, 4, (0, 0, 0), 0.6, 10)
            circle(sx, sy, 3, col, 1.0, 10)
        glDisable(GL_SCISSOR_TEST)
        # 自己 (箭头)
        c = (X + SZ / 2, Y + SZ / 2)
        glColor4f(1, 1, 1, 1)
        glBegin(GL_TRIANGLES)
        glVertex2f(c[0], c[1] - 8); glVertex2f(c[0] - 5, c[1] + 5); glVertex2f(c[0] + 5, c[1] + 5)
        glEnd()
        # 视野扇形
        glColor4f(1, 1, 1, 0.08)
        glBegin(GL_TRIANGLES)
        glVertex2f(*c); glVertex2f(c[0] - 55, c[1] - 90); glVertex2f(c[0] + 55, c[1] - 90)
        glEnd()
        rect_outline(X, Y, SZ, SZ, (1, 1, 1), 0.15)
        ui.label("N", X + SZ / 2 + math.sin(-yaw) * (SZ / 2 - 10), Y + SZ / 2 - math.cos(-yaw) * (SZ / 2 - 10),
                 13, GREY, align="center", valign="middle")
        ui.label(world.map.name, X, Y + SZ + 6, 13, GREY)

    # ── 比分 ──
    def _scores(self, world):
        ui = self.ui
        cx = ui.w / 2
        y = 16
        bw = 150
        s0, s1 = world.team_scores
        rect(cx - bw - 32, y, bw, 34, (0.05, 0.1, 0.16), 0.75)
        rect(cx + 32, y, bw, 34, (0.16, 0.06, 0.05), 0.75)
        rect(cx - bw - 32 + bw * (1 - s0 / S.SCORE_LIMIT), y + 30, bw * s0 / S.SCORE_LIMIT, 4, FRIEND, 1)
        rect(cx + 32, y + 30, bw * s1 / S.SCORE_LIMIT, 4, ENEMY, 1)
        ui.label(str(s0), cx - 42, y + 15, 24, FRIEND, align="right", valign="middle", bold=True)
        ui.label(str(s1), cx + 42, y + 15, 24, ENEMY, align="left", valign="middle", bold=True)
        ui.label(S.TEAM_NAMES[0], cx - bw - 24, y + 15, 13, WHITE, valign="middle")
        ui.label(S.TEAM_NAMES[1], cx + bw + 24, y + 15, 13, WHITE, align="right", valign="middle")
        rect(cx - 28, y, 56, 34, (0.03, 0.04, 0.05), 0.85)
        ui.label("TDM", cx, y + 9, 12, GREY, align="center", valign="middle")
        ui.label(str(S.SCORE_LIMIT), cx, y + 23, 13, WHITE, align="center", valign="middle")

    def _killfeed(self):
        ui = self.ui
        x = ui.w - 18
        y = 18
        for killer, kt, wname, victim, vt, hs, t, mine in self.killfeed:
            a = min(1.0, t)
            parts = []
            wv = ui.text.size(victim, 14)[0]
            ww = ui.text.size("[%s]" % wname, 13)[0]
            wk = ui.text.size(killer, 14)[0] if killer else 0
            total = wv + ww + wk + 30 + (26 if hs else 0)
            rect(x - total - 10, y - 2, total + 12, 24, (0.9, 0.9, 0.9) if mine else (0, 0, 0), 0.25 * a)
            xx = x
            xx -= ui.label(victim, xx, y + 10, 14, FRIEND if vt == 0 else ENEMY, alpha=a, align="right",
                           valign="middle") + 8
            if hs:
                xx -= ui.label("◎", xx, y + 10, 14, GOLD, alpha=a, align="right", valign="middle") + 6
            xx -= ui.label("[%s]" % wname, xx, y + 10, 13, WHITE, alpha=a, align="right", valign="middle") + 8
            if killer:
                ui.label(killer, xx, y + 10, 14, FRIEND if kt == 0 else ENEMY, alpha=a, align="right",
                         valign="middle")
            y += 27

    def _notices(self, cx, cy):
        y = cy + 70
        for text, sub, t, col in self.notices:
            a = min(1.0, t * 2)
            self.ui.label(text, cx, y, 18, col, alpha=a, align="center", bold=True)
            self.ui.label(sub, cx, y + 24, 15, GOLD, alpha=a, align="center")
            y += 48

    # ── 武器面板 ──
    def _weapon_panel(self, p, w):
        ui = self.ui
        W, H = ui.w, ui.h
        x1 = W - 24
        y = H - 150
        st = w.stats
        rect_grad(W - 380, H - 170, 380, 170, (0, 0, 0), (0, 0, 0), 0.0, 0.55, horizontal=True)
        ui.label(w.defn.name, x1, y, 20, WHITE, align="right", bold=True)
        ui.label(CATEGORY_NAMES[w.defn.category] + " · " + w.defn.caliber, x1, y + 26, 13, GREY, align="right")
        low = w.ammo <= max(1, st.mag_size // 4)
        ammo_col = ENEMY if w.ammo == 0 else (GOLD if low else WHITE)
        res_w = ui.label(str(w.reserve), x1, y + 58, 22, GREY, align="right", valign="middle")
        ui.label(str(w.ammo), x1 - res_w - 26, y + 55, 46, ammo_col, align="right", valign="middle", bold=True)
        rect(x1 - res_w - 16, y + 42, 2, 30, GREY, 0.6)
        ui.label(MODE_NAMES.get(w.fire_mode, w.fire_mode), x1, y + 88, 13, ACCENT, align="right")
        atts = " · ".join(ATTACHMENTS[w.atts[s]].name for s in SLOTS
                          if w.atts[s] not in ("muzzle_std", "ub_none", "mag_std"))
        ui.label(atts or "无配件", x1, y + 108, 12, GREY, align="right")
        # 武器槽
        yy = H - 36
        xx = x1
        for i in reversed(range(len(p.weapons))):
            wi = p.weapons[i]
            active = i == p.active
            txt = "%d  %s" % (i + 1, wi.defn.name)
            tw = ui.text.size(txt, 13)[0] + 16
            xx -= tw
            rect(xx, yy, tw, 22, ACCENT if active else (0, 0, 0), 0.9 if active else 0.45)
            ui.label(txt, xx + 8, yy + 11, 13, (0.02, 0.05, 0.07) if active else GREY, valign="middle",
                     shadow=not active)
            xx -= 6
        # 状态
        if w.state in ("reload", "shell"):
            self._progress_ring(W / 2, H / 2 + 48, w.progress if w.state == "reload" else w.ammo / st.mag_size,
                                "换弹中")
        elif w.state == "attach":
            self._progress_ring(W / 2, H / 2 + 48, w.progress, "改装中")

    def _progress_ring(self, x, y, t, label):
        arc(x, y, 14, -math.pi / 2, -math.pi / 2 + math.pi * 2, (1, 1, 1), 0.2, 3, 32)
        arc(x, y, 14, -math.pi / 2, -math.pi / 2 + math.pi * 2 * clamp(t, 0, 1), ACCENT, 0.95, 3, 32)
        self.ui.label(label, x, y + 22, 12, WHITE, align="center")

    def _health_panel(self, p):
        ui = self.ui
        H = ui.h
        x, y = 24, H - 70
        rect_grad(0, H - 110, 380, 110, (0, 0, 0), (0, 0, 0), 0.55, 0.0, horizontal=True)
        hp = max(0.0, p.health)
        col = WHITE if hp > 50 else (GOLD if hp > 25 else ENEMY)
        ui.label("%d" % math.ceil(hp), x, y - 6, 34, col, bold=True, valign="middle")
        bx = x + 70
        rect(bx, y - 8, 200, 8, (1, 1, 1), 0.15)
        rect(bx, y - 8, 200 * hp / S.MAX_HEALTH, 8, col, 0.95)
        if p.spawn_protect > 0:
            ui.label("出生保护 %.1fs" % p.spawn_protect, bx, y - 30, 12, ACCENT)
        # 姿态图标 + 状态
        self._stance_icon(x + 8, y + 32, p)
        state = MOVE_NAMES.get(p.move) or STANCE_NAMES[p.stance]
        if abs(p.lean) > 0.3:
            state += " · 侧身" + ("左" if p.lean < 0 else "右")
        if p.ads > 0.5:
            state += " · 瞄准"
        ui.label(state, x + 34, y + 32, 14, GREY, valign="middle")
        ui.label(S.TEAM_NAMES[p.team], bx + 200, y - 30, 12, FRIEND if p.team == 0 else ENEMY, align="right")

    def _stance_icon(self, x, y, p):
        c = WHITE
        if p.move == M_SLIDE:
            circle(x - 6, y - 4, 3, c, 1, 10)
            line(x - 4, y - 2, x + 8, y + 4, c, 1, 3)
        elif p.stance == PRONE:
            circle(x - 9, y + 3, 3, c, 1, 10)
            line(x - 6, y + 5, x + 12, y + 6, c, 1, 3)
        elif p.stance == CROUCH:
            circle(x, y - 8, 3, c, 1, 10)
            line(x, y - 5, x + 2, y + 2, c, 1, 3)
            line(x + 2, y + 2, x - 3, y + 8, c, 1, 3)
        else:
            circle(x, y - 11, 3, c, 1, 10)
            line(x, y - 8, x, y + 3, c, 1, 3)
            line(x, y + 3, x - 3, y + 11, c, 1, 2.5)
            line(x, y + 3, x + 3, y + 11, c, 1, 2.5)

    def _prompts(self, p, w):
        ui = self.ui
        cx, H = ui.w / 2, ui.h
        msg = None
        if w.ammo == 0 and w.reserve == 0:
            msg = "弹药耗尽 — 切换武器 [1/2]"
        elif w.ammo == 0 and w.state == "idle":
            msg = "[R] 换弹"
        elif w.ammo <= max(1, w.stats.mag_size // 4) and w.state == "idle":
            msg = "弹药不足  [R] 换弹"
        if msg:
            ui.label(msg, cx, H - 150, 16, GOLD, align="center")

    def _help(self, a):
        ui = self.ui
        lines = ["WASD 移动  ·  Shift 冲刺  ·  空格 跳跃/翻越  ·  C 半蹲 (冲刺中=滑铲, 长按=趴下)  ·  X 趴下",
                 "右键 瞄准  ·  左键 射击  ·  R 换弹  ·  1/2/滚轮 切枪  ·  B 射击模式  ·  Q/E 侧身  ·  T 检视",
                 "Z 配件菜单  ·  Tab 计分板  ·  Esc 暂停  ·  F1 显示/隐藏帮助"]
        y = 70
        for l in lines:
            ui.label(l, ui.w / 2, y, 13, WHITE, alpha=0.85 * a, align="center")
            y += 20

    # ── 计分板 ──
    def draw_scoreboard(self, world, local_pid):
        ui = self.ui
        W, H = ui.w, ui.h
        pw, ph = 900, 480
        x0, y0 = (W - pw) / 2, (H - ph) / 2
        rect(x0, y0, pw, ph, (0.03, 0.04, 0.06), 0.88)
        ui.label("计分板  ·  团队死斗", x0 + 20, y0 + 16, 20, WHITE, bold=True)
        for team in (0, 1):
            tx = x0 + 20 + team * (pw / 2)
            col = FRIEND if team == 0 else ENEMY
            ui.label("%s   %d" % (S.TEAM_NAMES[team], world.team_scores[team]), tx, y0 + 56, 18, col, bold=True)
            ui.label("玩家", tx, y0 + 90, 13, GREY)
            ui.label("击杀", tx + 230, y0 + 90, 13, GREY)
            ui.label("阵亡", tx + 290, y0 + 90, 13, GREY)
            ui.label("得分", tx + 350, y0 + 90, 13, GREY)
            ps = sorted([q for q in world.players.values() if q.team == team], key=lambda q: -q.score)
            y = y0 + 114
            for q in ps:
                if q.pid == local_pid:
                    rect(tx - 6, y - 3, pw / 2 - 30, 24, ACCENT, 0.22)
                name = q.name + ("" if q.alive else "  ✝")
                ui.label(name + ("  [BOT]" if q.is_bot else ""), tx, y, 14, WHITE if q.alive else GREY)
                ui.label(str(q.kills), tx + 230, y, 14, WHITE)
                ui.label(str(q.deaths), tx + 290, y, 14, WHITE)
                ui.label(str(q.score), tx + 350, y, 14, WHITE)
                y += 26
