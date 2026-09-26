"""菜单: 主菜单 / 部署(选枪) / Plus 配件菜单 (Z) / 暂停"""
import math
from OpenGL.GL import *
from core import settings as S
from core.mathutil import clamp
from weapons.definitions import (WEAPONS, CATEGORY_NAMES, PRIMARY_CATEGORIES, weapons_in, secondary_weapons,
                                 PISTOL, RIFLE, SNIPER, SHOTGUN)
from weapons.attachments import (ATTACHMENTS, SLOTS, SLOT_NAMES, options_for, compute_stats, sanitize,
                                 default_attachments, DEFAULT_BY_SLOT)
from render.gl_util import rect, rect_outline, rect_grad, line, circle
from .widgets import (ACCENT, ACCENT_DIM, WHITE, GREY, ENEMY, FRIEND, GOLD, PANEL, DARK_TEXT,
                      draw_gun_preview)

DIFFICULTY = [("简单", 0.25), ("普通", 0.5), ("困难", 0.72), ("精英", 0.92)]


# ════════════════ 属性归一化 (用于属性条) ════════════════
def stat_values(wdef, st):
    return {
        "伤害": (clamp(st.damage_near * st.pellets / 110.0, 0, 1), "%.0f%s" % (st.damage_near, (" x%d" % st.pellets) if st.pellets > 1 else "")),
        "射速": (clamp(wdef.rpm / 1150.0, 0, 1), "%d RPM" % wdef.rpm),
        "射程": (clamp(st.range_far / 240.0, 0, 1), "%d m" % st.range_far),
        "后坐控制": (clamp(1 - st.recoil_v / 6.5, 0, 1), "%.2f°" % st.recoil_v),
        "腰射精度": (clamp(1 - st.spread_hip / 8.0, 0, 1), "%.1f°" % st.spread_hip),
        "开镜速度": (clamp(1 - (st.ads_time - 0.1) / 0.55, 0, 1), "%d ms" % (st.ads_time * 1000)),
        "机动性": (clamp(st.move_mult / 1.08, 0, 1), "%d%%" % (st.move_mult * 100)),
    }


def draw_stats(ui, x, y, w, wdef, atts, preview_atts=None):
    st = compute_stats(wdef, atts)
    base = compute_stats(wdef, default_attachments(wdef))
    sv = stat_values(wdef, st)
    bv = stat_values(wdef, base)
    pv = stat_values(wdef, compute_stats(wdef, preview_atts)) if preview_atts else None
    pst = compute_stats(wdef, preview_atts) if preview_atts else None

    for k, (v, txt) in sv.items():
        if pv is not None:
            prev_v, prev_txt = pv[k]
            delta = prev_v - v
            ui.stat_bar(x, y, w, k, prev_v, delta, prev_txt)
        else:
            delta = v - bv[k][0]
            ui.stat_bar(x, y, w, k, v, delta, txt)
        y += 38

    ui.label("弹匣容量", x, y, 13, GREY, shadow=False)
    cur_mag = st.mag_size
    show_mag = pst.mag_size if pst else cur_mag
    col = WHITE
    if pst and show_mag > cur_mag:
        col = (0.3, 1.0, 0.45)
    elif pst and show_mag < cur_mag:
        col = (1.0, 0.35, 0.3)
    ui.label("%d / %d" % (show_mag, show_mag * wdef.reserve_mags), x + w, y, 13, col, align="right", shadow=False)
    y += 20

    ui.label("换弹时间", x, y, 13, GREY, shadow=False)
    cur_rt = pst.reload_time if pst else st.reload_time
    cur_et = pst.reload_empty_time if pst else st.reload_empty_time
    txt = ("%.1fs/发" % (pst.shell_time if pst else st.shell_time)) if wdef.shell_reload else ("%.1fs / %.1fs" % (cur_rt, cur_et))
    ui.label(txt, x + w, y, 13, WHITE, align="right", shadow=False)
    y += 20

    ui.label("射击模式", x, y, 13, GREY, shadow=False)
    names = {"auto": "全自动", "semi": "半自动", "burst": "%d连发" % wdef.burst_count, "bolt": "手动", "pump": "泵动"}
    ui.label(" / ".join(names[m] for m in wdef.fire_modes), x + w, y, 13, WHITE, align="right", shadow=False)
    return y + 20


# ════════════════ Plus 配件菜单 ════════════════
class PlusMenu:
    """BF2042 风格: 四个方向对应四个配件槽, 中间显示武器"""

    def __init__(self, ui, gun_cache):
        self.ui = ui
        self.cache = gun_cache
        self.is_open = False
        self.wid = None
        self.atts = None
        self.on_change = None
        self.hover_att = None
        self.t = 0.0
        self.tabs = None          # [(label, wid, atts, callback)]
        self.tab_idx = 0
        self.in_game = False

    def open(self, tabs, tab_idx=0, in_game=False):
        self.tabs = tabs
        self.tab_idx = tab_idx
        self.is_open = True
        self.in_game = in_game
        self._select_tab(tab_idx)

    def _select_tab(self, i):
        self.tab_idx = i
        _, self.wid, atts, self.on_change = self.tabs[i]
        self.atts = dict(atts)

    def close(self):
        self.is_open = False

    def draw(self, dt):
        if not self.is_open:
            return
        self.t += dt
        ui = self.ui
        W, H = ui.w, ui.h
        cx, cy = W / 2, H / 2 + 10
        wdef = WEAPONS[self.wid]
        rect(0, 0, W, H, (0.01, 0.02, 0.03), 0.55 if self.in_game else 0.75)
        rect_grad(0, cy - 110, W, 220, (0.1, 0.4, 0.5), (0.1, 0.4, 0.5), 0.0, 0.0)
        # 标题 + 标签页
        ui.label("配件  ·  " + wdef.name, cx, 26, 22, WHITE, align="center", bold=True)
        ui.label("按 Z / Esc 关闭    点击选择配件" + ("    (更换配件时无法射击)" if self.in_game else ""),
                 cx, 56, 13, GREY, align="center")
        if len(self.tabs) > 1:
            tw = 160
            x0 = cx - tw * len(self.tabs) / 2
            for i, (label, wid, _, _) in enumerate(self.tabs):
                if ui.button(x0 + i * tw, 80, tw - 6, 30, label + " · " + WEAPONS[wid].name, i == self.tab_idx, size=13):
                    self._select_tab(i)
                    wdef = WEAPONS[self.wid]
        # 中央武器预览
        pw, ph = 460, 200
        model = self.cache.get(self.wid, self.atts)
        rect_outline(cx - pw / 2, cy - ph / 2, pw, ph, ACCENT, 0.25)
        ui.corner_frame(cx - pw / 2, cy - ph / 2, pw, ph)
        draw_gun_preview(model, cx - pw / 2, cy - ph / 2, pw, ph, W, H, self.t, spin=False,
                         yaw=90 + math.sin(self.t * 0.6) * 12)
        glEnable(GL_BLEND)
        self.hover_att = None
        bw, bh = 176, 38
        # 上: 瞄具
        self._slot_row("optic", cx, cy - ph / 2 - 20 - bh, bw, bh, horizontal=True, label_above=True)
        # 下: 弹匣
        self._slot_row("magazine", cx, cy + ph / 2 + 24, bw, bh, horizontal=True, label_above=False)
        # 左: 枪口
        self._slot_row("muzzle", cx - pw / 2 - 30 - bw, cy, bw, bh, horizontal=False, label_above=True)
        # 右: 下挂
        self._slot_row("underbarrel", cx + pw / 2 + 30, cy, bw, bh, horizontal=False, label_above=True)
        # 说明 & 属性
        if self.hover_att:
            a = ATTACHMENTS[self.hover_att]
            ui.label(a.name + " — " + a.desc, cx, H - 150, 15, WHITE, align="center")
        draw_stats_compact(ui, W - 250, 130, 220, wdef, self.atts)

    def _slot_row(self, slot, x, y, bw, bh, horizontal, label_above):
        ui = self.ui
        wdef = WEAPONS[self.wid]
        opts = options_for(wdef, slot)
        n = len(opts)
        arrow = {"optic": "▲", "magazine": "▼", "muzzle": "◀", "underbarrel": "▶"}[slot]
        if horizontal:
            total = n * (bw + 6) - 6
            x0 = x - total / 2
            ly = y - 22 if label_above else y + bh + 6
            ui.label(arrow + " " + SLOT_NAMES[slot], x, ly, 14, ACCENT, align="center", bold=True)
            for i, a in enumerate(opts):
                self._opt(slot, a, x0 + i * (bw + 6), y, bw, bh)
        else:
            total = n * (bh + 6) - 6
            y0 = y - total / 2
            ui.label(arrow + " " + SLOT_NAMES[slot], x + bw / 2, y0 - 24, 14, ACCENT, align="center", bold=True)
            for i, a in enumerate(opts):
                self._opt(slot, a, x, y0 + i * (bh + 6), bw, bh)

    def _opt(self, slot, a, x, y, w, h):
        ui = self.ui
        sel = self.atts.get(slot) == a.id
        if ui.hover(x, y, w, h):
            self.hover_att = a.id
        if ui.button(x, y, w, h, a.name, selected=sel, size=14):
            if not sel:
                self.atts[slot] = a.id
                self.atts = sanitize(WEAPONS[self.wid], self.atts)
                label, wid, _, cb = self.tabs[self.tab_idx]
                self.tabs[self.tab_idx] = (label, wid, dict(self.atts), cb)
                if cb:
                    cb(dict(self.atts))


def draw_stats_compact(ui, x, y, w, wdef, atts):
    ui.panel(x - 12, y - 12, w + 24, 350, 0.6)
    ui.label("属性", x, y, 14, ACCENT, bold=True)
    draw_stats(ui, x, y + 26, w, wdef, atts)


# ════════════════ 全新战备部署界面 (直观易用 · 零繁琐) ════════════════
class LoadoutScreen:
    """
    全新编写的战备部署界面:
    1. 左侧: 清晰的主/副武器切换与类别标签，单机即换枪。
    2. 中间: 3D 高精战术模型舞台，下方直出 4 个改装槽位，点击即可就地展开配件抽屉，支持即时对比。
    3. 右侧: 武器性能雷达属性板，悬停配件即时红绿对比。
    4. 底部: 醒目的巨型部署按钮，支持 空格/回车 极速部署。
    """

    def __init__(self, ui, gun_cache, prefs):
        self.ui = ui
        self.cache = gun_cache
        self.prefs = prefs
        self.t = 0.0
        self.focus = "primary"        # "primary" | "secondary"
        p = WEAPONS.get(prefs.data.get("primary", "m4a1"))
        self.category = p.category if p else RIFLE
        self.active_slot = None       # None | "optic" | "muzzle" | "underbarrel" | "magazine"
        self.hovered_att = None       # 悬停配件用于属性对比

    def atts_for(self, wid):
        saved = self.prefs.data.setdefault("atts", {}).get(wid)
        return sanitize(WEAPONS[wid], saved) if saved else default_attachments(WEAPONS[wid])

    def set_atts(self, wid, atts):
        self.prefs.data.setdefault("atts", {})[wid] = dict(atts)
        self.prefs.save()

    def loadout(self):
        d = self.prefs.data
        prim = d.get("primary", "m4a1")
        sec = d.get("secondary", "p320")
        return dict(primary=prim, secondary=sec, primary_atts=self.atts_for(prim), secondary_atts=self.atts_for(sec))

    def draw(self, dt, respawn_t, team, plus_menu, status=""):
        """返回 'deploy' / 'menu' / None"""
        self.t += dt
        ui = self.ui
        W, H = ui.w, ui.h
        d = self.prefs.data
        result = None

        # ── 战术深色渐变背景 ──
        rect(0, 0, W, H, (0.03, 0.04, 0.06), 0.82)
        rect_grad(0, 0, W, 72, (0.01, 0.02, 0.03), (0.03, 0.04, 0.06), 0.95, 0.75)
        rect(0, 72, W, 2, ACCENT, 0.35)

        # ── 顶栏: 部署标题与阵营状态 ──
        ui.label("战备部署", 32, 16, 26, WHITE, bold=True)
        ui.label("LOADOUT & DEPLOYMENT · 战备配置与直观改装", 155, 26, 12, GREY)

        team_name = S.TEAM_NAMES.get(team, "BLUFOR")
        team_col = FRIEND if team == 0 else ENEMY
        ui.label(team_name, W - 32, 18, 18, team_col, align="right", bold=True)
        if status:
            ui.label(status, W - 32, 44, 12, GREY, align="right")
        else:
            ui.label("准备就绪 · 随时投入交火", W - 32, 44, 12, (0.35, 0.85, 0.5), align="right")

        # ── 当前选中的主/副武器 ID ──
        prim_id = d.get("primary", "m4a1")
        sec_id = d.get("secondary", "p320")
        cur_id = prim_id if self.focus == "primary" else sec_id
        wdef = WEAPONS[cur_id]
        cur_atts = self.atts_for(cur_id)

        # ════════════════ 左侧: 武器库选择栏 (W: 320) ════════════════
        lx, ly = 32, 88
        lw = 320

        # 主武器 / 副武器 切换大卡片
        pw_btn = (lw - 8) / 2
        prim_def = WEAPONS[prim_id]
        sec_def = WEAPONS[sec_id]

        if ui.button(lx, ly, pw_btn, 48, "主武器", selected=(self.focus == "primary"), size=14, sub=prim_def.name):
            self.focus = "primary"
            self.active_slot = None
            self.category = prim_def.category
        if ui.button(lx + pw_btn + 8, ly, pw_btn, 48, "副武器", selected=(self.focus == "secondary"), size=14, sub=sec_def.name):
            self.focus = "secondary"
            self.active_slot = None
            self.category = PISTOL

        ly += 56

        # 武器类别筛选器
        if self.focus == "primary":
            cat_w = (lw - 10) / 3
            for i, cat in enumerate(PRIMARY_CATEGORIES):
                is_sel = cat == self.category
                if ui.button(lx + i * (cat_w + 5), ly, cat_w, 30, CATEGORY_NAMES[cat], selected=is_sel, size=13):
                    self.category = cat
                    self.active_slot = None
            ly += 38
            available_weapons = weapons_in(self.category)
        else:
            ui.label("副手随身武器 · 手枪系列", lx, ly + 6, 13, ACCENT_DIM, bold=True)
            ly += 34
            available_weapons = secondary_weapons()

        # 武器卡片列表
        card_h = 52
        for w in available_weapons:
            is_active = (cur_id == w.id)
            sub_info = "%s · %s" % (w.caliber, " / ".join(w.fire_modes[:2]))
            if ui.button(lx, ly, lw, card_h, w.name, selected=is_active, size=15, sub=sub_info, align="left"):
                if self.focus == "primary":
                    d["primary"] = w.id
                else:
                    d["secondary"] = w.id
                self.prefs.save()
                self.active_slot = None
            ly += card_h + 6

        # ════════════════ 中间: 3D 展台与直接配件改装 (W: 530) ════════════════
        cx = 372
        cy = 88
        cw = 530
        stage_h = 245

        # 3D 武器展台面板
        ui.panel(cx, cy, cw, stage_h, 0.40)
        ui.corner_frame(cx, cy, cw, stage_h)

        # 渲染 3D 枪械模型
        model = self.cache.get(cur_id, cur_atts)
        draw_gun_preview(model, cx, cy, cw, stage_h, W, H, self.t, spin=True)
        glEnable(GL_BLEND)

        # 展台左上角标签
        ui.label(wdef.name, cx + 16, cy + 12, 22, WHITE, bold=True)
        ui.label(CATEGORY_NAMES[wdef.category] + "  ·  " + wdef.caliber, cx + 16, cy + 40, 13, GREY)
        ui.label(wdef.real, cx + 16, cy + stage_h - 22, 12, (0.7, 0.72, 0.75))

        # ── 4 个直观配件卡片 ──
        slot_y = cy + stage_h + 16
        slot_w = (cw - 18) / 4

        ui.label("配件快速改装 (点击槽位展开直选 · 悬停对比属性)", cx, slot_y, 13, ACCENT, bold=True)
        slot_y += 24

        for i, slot in enumerate(SLOTS):
            aid = cur_atts[slot]
            a = ATTACHMENTS[aid]
            is_slot_open = (self.active_slot == slot)
            sx = cx + i * (slot_w + 6)
            if ui.button(sx, slot_y, slot_w, 54, a.name, selected=is_slot_open, size=13, sub=SLOT_NAMES[slot]):
                self.active_slot = None if is_slot_open else slot
                self.hovered_att = None

        # ── 直观展开的配件抽屉 (INLINE TRAY) ──
        tray_y = slot_y + 62
        tray_h = H - tray_y - 84

        self.hovered_att = None
        if self.active_slot is not None:
            opts = options_for(wdef, self.active_slot)
            ui.panel(cx, tray_y, cw, tray_h, 0.65)
            ui.corner_frame(cx, tray_y, cw, tray_h, color=ACCENT_DIM)
            ui.label("选择 %s (%d 项可用)" % (SLOT_NAMES[self.active_slot], len(opts)), cx + 14, tray_y + 10, 13, ACCENT, bold=True)

            # 关闭抽屉按钮
            if ui.button(cx + cw - 32, tray_y + 6, 24, 20, "×", size=14):
                self.active_slot = None

            # 配件选项卡片
            opt_x = cx + 12
            opt_y = tray_y + 32
            opt_w = (cw - 30) / 2
            opt_h = 42

            for j, opt in enumerate(opts):
                is_equipped = (cur_atts[self.active_slot] == opt.id)
                col_idx = j % 2
                row_idx = j // 2
                bx = opt_x + col_idx * (opt_w + 6)
                by = opt_y + row_idx * (opt_h + 6)

                if by + opt_h <= tray_y + tray_h:
                    if ui.hover(bx, by, opt_w, opt_h):
                        self.hovered_att = opt.id
                    sub_text = opt.desc[:22]
                    if ui.button(bx, by, opt_w, opt_h, opt.name, selected=is_equipped, size=13, sub=sub_text, align="left"):
                        cur_atts[self.active_slot] = opt.id
                        self.set_atts(cur_id, cur_atts)
        else:
            # 抽屉未展开时展示当前配置概览与操作指南
            ui.panel(cx, tray_y, cw, tray_h, 0.35)
            ui.corner_frame(cx, tray_y, cw, tray_h, color=(0.2, 0.3, 0.4))
            ui.label("战术战备简报", cx + 16, tray_y + 12, 14, ACCENT_DIM, bold=True)
            tip1 = "· 点击上方 [ 瞄具 / 枪口 / 下挂 / 弹匣 ] 可就地快速选装并实时预览 3D 变化"
            tip2 = "· 战局中亦可随时按 [ Z ] 键呼出战场快速改装环"
            tip3 = "· 开镜瞄准自带精确物理倍率缩放与出瞳视场校准"
            tip4 = "· 选好武器后，按 [ 空格 ] 或 [ 回车 ] 即可直接出击"
            ui.label(tip1, cx + 16, tray_y + 38, 12, GREY)
            ui.label(tip2, cx + 16, tray_y + 60, 12, GREY)
            ui.label(tip3, cx + 16, tray_y + 82, 12, GREY)
            ui.label(tip4, cx + 16, tray_y + 104, 12, (0.4, 0.85, 0.6))

        # ════════════════ 右侧: 武器属性雷达数据板 (W: 315) ════════════════
        rx = cx + cw + 20
        rw = W - rx - 32
        ry = 88
        rh = H - ry - 84

        ui.panel(rx, ry, rw, rh, 0.50)
        ui.corner_frame(rx, ry, rw, rh)
        ui.label("武器性能参数", rx + 14, ry + 12, 15, ACCENT, bold=True)

        # 预览对比配置
        prev_atts = dict(cur_atts)
        if self.hovered_att:
            a = ATTACHMENTS[self.hovered_att]
            prev_atts[a.slot] = a.id
        draw_stats(ui, rx + 14, ry + 40, rw - 28, wdef, cur_atts, prev_atts if self.hovered_att else None)

        # ════════════════ 底栏: 部署操作与主菜单 ════════════════
        by = H - 72

        # 返回主菜单
        if ui.button(32, by, 150, 48, "返回主菜单", size=14, sub="ESC"):
            result = "menu"

        # 中间配置简述
        prim_optic = ATTACHMENTS[self.atts_for(prim_id)["optic"]].name
        sec_optic = ATTACHMENTS[self.atts_for(sec_id)["optic"]].name
        summary = "已选战备:  %s (%s)  +  %s (%s)" % (prim_def.name, prim_optic, sec_def.name, sec_optic)
        ui.label(summary, cx, by + 16, 14, WHITE, bold=True)

        # 醒目的巨型部署按钮
        ready = respawn_t <= 0
        deploy_w = 280
        deploy_x = W - deploy_w - 32
        deploy_label = "确认部署" if ready else "部署冷却"
        deploy_sub = "ENTER / 空格 立即出发" if ready else "等待重生 %.1fs" % respawn_t
        if ui.button(deploy_x, by, deploy_w, 52, deploy_label, selected=ready, enabled=ready,
                     size=20, sub=deploy_sub, accent=ACCENT if ready else (0.4, 0.4, 0.4)):
            result = "deploy"

        return result

    def open_plus(self, plus_menu):
        d = self.prefs.data
        tabs = []
        for label, key in (("主武器", "primary"), ("副武器", "secondary")):
            wid = d.get(key)
            tabs.append((label, wid, self.atts_for(wid), (lambda w: (lambda a: self.set_atts(w, a)))(wid)))
        plus_menu.open(tabs, 0 if self.focus == "primary" else 1)


# ════════════════ 主菜单 ════════════════
class MainMenu:
    def __init__(self, ui, prefs):
        self.ui = ui
        self.prefs = prefs
        self.t = 0.0
        self.page = "main"
        self.focus_field = None

    def text_input(self, ch):
        if self.focus_field:
            v = self.prefs.data.get(self.focus_field, "")
            if len(v) < 32:
                self.prefs.data[self.focus_field] = v + ch

    def backspace(self):
        if self.focus_field:
            self.prefs.data[self.focus_field] = self.prefs.data.get(self.focus_field, "")[:-1]

    def draw(self, dt, info=""):
        """返回 ('single',) / ('connect', host, port) / ('quit',) / None"""
        self.t += dt
        ui = self.ui
        W, H = ui.w, ui.h
        d = self.prefs.data
        rect_grad(0, 0, W * 0.6, H, (0.01, 0.02, 0.03), (0.01, 0.02, 0.03), 0.92, 0.0, horizontal=True)
        ui.label("PORTAL STRIKE", 70, 70, 54, WHITE, bold=True)
        ui.label("2042", 70 + ui.text.size("PORTAL STRIKE", 54, True)[0] + 16, 70, 54, ACCENT, bold=True)
        ui.label("Python 第一人称射击  ·  战地风格原型  ·  v" + S.GAME_VERSION, 72, 138, 15, GREY)
        rect(72, 166, 90, 3, ACCENT, 1)
        res = None
        x, y = 70, 210
        if self.page == "main":
            if ui.button(x, y, 320, 56, "单人对战", size=22, sub="团队死斗 · 对抗 AI 机器人", align="left"):
                self.page = "single"
            y += 66
            if ui.button(x, y, 320, 56, "多人游戏", size=22, sub="连接专用服务器", align="left"):
                self.page = "multi"
            y += 66
            if ui.button(x, y, 320, 56, "操作说明", size=22, sub="动作系统 / 按键", align="left"):
                self.page = "help"
            y += 66
            if ui.button(x, y, 320, 56, "退出游戏", size=22, align="left"):
                res = ("quit",)
        elif self.page == "single":
            ui.label("单人对战设置", x, y, 20, WHITE, bold=True)
            y += 44
            y = self._stepper(x, y, "友军机器人", "friendly_bots", 0, 10)
            y = self._stepper(x, y, "敌军机器人", "enemy_bots", 1, 12)
            ui.label("难度", x, y + 10, 16, GREY)
            for i, (name, _) in enumerate(DIFFICULTY):
                if ui.button(x + 150 + i * 86, y, 80, 36, name, d.get("difficulty", 1) == i, size=14):
                    d["difficulty"] = i
                    self.prefs.save()
            y += 50
            y = self._stepper(x, y, "鼠标灵敏度", "sens", 0.2, 3.0, step=0.1, fmt="%.1f")
            y += 16
            if ui.button(x, y, 320, 56, "开始游戏", selected=True, size=22):
                res = ("single",)
            if ui.button(x + 330, y, 140, 56, "返回", size=18):
                self.page = "main"
        elif self.page == "multi":
            ui.label("连接到专用服务器", x, y, 20, WHITE, bold=True)
            y += 44
            y = self._field(x, y, "玩家名", "name")
            y = self._field(x, y, "服务器地址", "server")
            ui.label("启动服务器:  cd fps_game  &&  python -m net.server --port %d --bots 3" % S.DEFAULT_PORT,
                     x, y + 4, 13, GREY)
            y += 36
            if ui.button(x, y, 320, 56, "连接", selected=True, size=22):
                addr = d.get("server", "127.0.0.1:%d" % S.DEFAULT_PORT)
                host, _, port = addr.partition(":")
                try:
                    res = ("connect", host.strip() or "127.0.0.1", int(port or S.DEFAULT_PORT))
                except ValueError:
                    res = None
            if ui.button(x + 330, y, 140, 56, "返回", size=18):
                self.page = "main"
                self.focus_field = None
        elif self.page == "help":
            self._help(x, y)
            if ui.button(x, H - 90, 140, 48, "返回", size=18):
                self.page = "main"
        if info:
            ui.label(info, x, H - 36, 14, GOLD)
        return res

    def _stepper(self, x, y, label, key, lo, hi, step=1, fmt="%d"):
        ui = self.ui
        d = self.prefs.data
        v = d.get(key, lo)
        ui.label(label, x, y + 10, 16, GREY)
        if ui.button(x + 150, y, 40, 36, "−", size=18):
            d[key] = max(lo, round(v - step, 2))
            self.prefs.save()
        ui.label(fmt % d.get(key, v), x + 240, y + 18, 18, WHITE, align="center", valign="middle", bold=True)
        if ui.button(x + 290, y, 40, 36, "+", size=18):
            d[key] = min(hi, round(v + step, 2))
            self.prefs.save()
        return y + 48

    def _field(self, x, y, label, key):
        ui = self.ui
        ui.label(label, x, y + 10, 16, GREY)
        fx, fw = x + 150, 300
        focused = self.focus_field == key
        rect(fx, y, fw, 36, (0.05, 0.07, 0.1), 0.9)
        rect_outline(fx, y, fw, 36, ACCENT if focused else (1, 1, 1), 0.8 if focused else 0.15)
        txt = self.prefs.data.get(key, "")
        caret = "|" if focused and int(self.t * 2) % 2 == 0 else ""
        ui.label(txt + caret, fx + 10, y + 18, 16, WHITE, valign="middle")
        if ui.clicked:
            if ui.hover(fx, y, fw, 36):
                self.focus_field = key
            elif self.focus_field == key:
                self.focus_field = None
                self.prefs.save()
        return y + 48

    def _help(self, x, y):
        ui = self.ui
        rows = [
            ("移动", "W A S D"), ("冲刺", "按住 Shift (冲刺时 FOV 增大, 枪械下压为战术冲刺姿态)"),
            ("跳跃 / 翻越", "空格 — 面对 0.45~1.65m 的障碍自动翻越 (空中贴墙亦可)"),
            ("半蹲", "C 或 左Ctrl (切换)"), ("滑铲", "冲刺中按 C — 保持动量, 可接跳跃 (滑铲跳)"),
            ("趴下", "X 或 长按 C — 趴下/起身有过渡动作, 匍匐时不能射击"),
            ("侧身", "Q / E (探头射击)"), ("瞄准 / 射击", "右键 / 左键"),
            ("换弹", "R — 战术换弹与空仓换弹不同动作; 霰弹逐发装填可被射击打断"),
            ("切换武器", "1 / 2 / 鼠标滚轮"), ("射击模式", "B"), ("检视武器", "T"),
            ("配件菜单", "Z — 游戏中实时改装 (BF2042 Plus 系统)"),
            ("计分板 / 暂停", "Tab / Esc"),
        ]
        for k, v in rows:
            ui.label(k, x, y, 16, ACCENT, bold=True)
            ui.label(v, x + 150, y, 15, WHITE)
            y += 30


# ════════════════ 暂停 ════════════════
class PauseMenu:
    def __init__(self, ui, prefs):
        self.ui = ui
        self.prefs = prefs

    def draw(self):
        ui = self.ui
        W, H = ui.w, ui.h
        rect(0, 0, W, H, (0, 0, 0), 0.6)
        x, y = W / 2 - 160, H / 2 - 170
        ui.label("暂停", W / 2, y - 50, 32, WHITE, align="center", bold=True)
        res = None
        if ui.button(x, y, 320, 50, "继续游戏", selected=True, size=20):
            res = "resume"
        y += 60
        if ui.button(x, y, 320, 50, "重新部署 (更换武器)", size=18):
            res = "redeploy"
        y += 60
        d = self.prefs.data
        ui.label("灵敏度  %.1f" % d.get("sens", 1.0), W / 2, y + 25, 17, WHITE, align="center", valign="middle")
        if ui.button(x, y, 50, 50, "−", size=20):
            d["sens"] = max(0.2, round(d.get("sens", 1.0) - 0.1, 2))
        if ui.button(x + 270, y, 50, 50, "+", size=20):
            d["sens"] = min(3.0, round(d.get("sens", 1.0) + 0.1, 2))
        y += 60
        fov = d.get("fov", S.FOV_BASE)
        ui.label("视野 FOV  %d" % fov, W / 2, y + 25, 17, WHITE, align="center", valign="middle")
        if ui.button(x, y, 50, 50, "−", size=20):
            d["fov"] = max(60, fov - 2)
        if ui.button(x + 270, y, 50, 50, "+", size=20):
            d["fov"] = min(100, fov + 2)
        y += 60
        if ui.button(x, y, 320, 50, "返回主菜单", size=18):
            res = "menu"
        return res
