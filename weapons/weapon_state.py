"""
WeaponInstance —— 单把武器的运行时状态机 (纯逻辑, 确定性)。

状态:
  draw     拔枪
  idle     待机 (可射击)
  reload   弹匣换弹 (tactical / empty)
  shell    逐发装填 (霰弹): phase = start / loop / end
  cycle    拉栓 / 泵动
  attach   更换配件
  inspect  检视

所有字段可序列化 → 可直接放进网络快照。渲染层只"读取"这些状态来驱动动画。
"""
from .definitions import WEAPONS
from .attachments import compute_stats, sanitize, default_attachments

ATTACH_TIME = 0.55
INSPECT_TIME = 2.6
SHELL_END_TIME = 0.35


class WeaponInstance:
    def __init__(self, wid: str, atts=None):
        self.id = wid
        self.defn = WEAPONS[wid]
        self.atts = sanitize(self.defn, atts) if atts else default_attachments(self.defn)
        self.stats = compute_stats(self.defn, self.atts)
        self.ammo = self.stats.mag_size
        self.reserve = self.stats.mag_size * self.defn.reserve_mags
        self.mode_idx = 0
        self.state = "draw"
        self.phase = ""
        self.timer = self.defn.draw_time
        self.total = self.defn.draw_time
        self.cooldown = 0.0
        self.burst_left = 0
        self.shots_in_row = 0
        self.since_shot = 9.0
        self.bloom = 0.0
        self.empty_reload = False
        self.reload_applied = False
        self.shot_counter = 0
        self.reload_counter = 0
        self.needs_pump_after_reload = False
        self.trigger_buffer = 0.0

    # ── 属性 ──
    @property
    def fire_mode(self):
        return self.defn.fire_modes[self.mode_idx % len(self.defn.fire_modes)]

    @property
    def progress(self):
        return 1.0 - (self.timer / self.total) if self.total > 0 else 1.0

    # ── 外部动作 ──
    def draw(self):
        self.state = "draw"
        self.timer = self.total = self.defn.draw_time
        self.burst_left = 0

    def set_attachments(self, atts):
        new_atts = sanitize(self.defn, atts)
        if new_atts == self.atts:
            return False
        old_mag = self.stats.mag_size
        self.atts = new_atts
        self.stats = compute_stats(self.defn, self.atts)
        if self.stats.mag_size != old_mag:
            # 弹匣容量变化: 多余子弹放回备弹
            total = self.ammo + self.reserve
            self.ammo = min(self.ammo, self.stats.mag_size)
            self.reserve = total - self.ammo
        self.state = "attach"
        self.timer = self.total = ATTACH_TIME
        return True

    def cycle_fire_mode(self):
        if len(self.defn.fire_modes) > 1 and self.state in ("idle", "inspect"):
            self.mode_idx = (self.mode_idx + 1) % len(self.defn.fire_modes)
            return True
        return False

    def start_inspect(self):
        if self.state == "idle":
            self.state = "inspect"
            self.timer = self.total = INSPECT_TIME

    def start_reload(self):
        if self.state not in ("idle", "inspect") or self.ammo >= self.stats.mag_size or self.reserve <= 0:
            return False
        self.reload_counter += 1
        self.empty_reload = self.ammo == 0
        self.reload_applied = False
        if self.defn.shell_reload:
            self.state = "shell"
            self.phase = "start"
            self.needs_pump_after_reload = self.empty_reload
            self.timer = self.total = self.stats.reload_time
        else:
            self.state = "reload"
            t = self.stats.reload_empty_time if self.empty_reload else self.stats.reload_time
            self.timer = self.total = t
        return True

    def cancel(self):
        """被切枪 / 死亡打断"""
        if self.state in ("reload", "shell", "inspect", "attach", "cycle"):
            self.state = "idle"
            self.timer = 0.0

    # ── 每 tick 更新 ──
    def update(self, dt, trigger, trigger_pressed, reload_pressed, can_fire):
        """返回本 tick 的射击次数 (0 或 1, 高射速下可能 2)"""
        self.cooldown = max(-0.05, self.cooldown - dt)
        self.trigger_buffer = max(0.0, self.trigger_buffer - dt)
        self.since_shot += dt
        self.bloom = max(0.0, self.bloom - dt * (self.defn.spread_max_bloom * 2.2 + 1.0))
        if self.since_shot > 0.28 and not trigger:
            self.shots_in_row = 0

        # 检视可被任何动作打断
        if self.state == "inspect" and (trigger_pressed or reload_pressed):
            self.state = "idle"

        # 霰弹逐发装填时扣扳机 → 打断
        if self.state == "shell" and trigger_pressed and self.ammo > 0 and self.phase == "loop":
            self.phase = "end"
            self.timer = self.total = SHELL_END_TIME * 0.5

        self._tick_state(dt)

        if reload_pressed:
            self.start_reload()

        shots = 0
        if self.state != "idle" or not can_fire:
            if self.state != "idle":
                self.burst_left = 0
            return 0

        if self.ammo <= 0:
            if trigger_pressed or (trigger and self.fire_mode == "auto"):
                self.start_reload()
            return 0

        mode = self.fire_mode
        want = False
        if mode == "auto":
            want = trigger
        elif mode == "burst":
            if trigger_pressed and self.burst_left <= 0:
                self.burst_left = self.defn.burst_count
            want = self.burst_left > 0
        else:  # semi / bolt / pump — 带扳机缓冲, 冷却中按下也不会丢失
            if trigger_pressed:
                self.trigger_buffer = 0.14
            want = self.trigger_buffer > 0

        interval = 60.0 / self.defn.rpm
        if mode == "burst":
            interval *= 0.75
        while want and self.cooldown <= 0 and self.ammo > 0 and shots < 2:
            self._fire_one(interval)
            shots += 1
            if mode == "burst":
                self.burst_left -= 1
                want = self.burst_left > 0
            elif mode != "auto":
                want = False
                self.trigger_buffer = 0.0
            if self.state != "idle":
                break
        return shots

    def _fire_one(self, interval):
        self.ammo -= 1
        self.cooldown = max(self.cooldown, 0.0) + interval
        self.shot_counter += 1
        self.shots_in_row += 1
        self.since_shot = 0.0
        self.bloom = min(self.defn.spread_max_bloom, self.bloom + self.defn.spread_per_shot)
        if self.fire_mode in ("bolt", "pump") and self.ammo > 0:
            self.state = "cycle"
            self.timer = self.total = self.defn.cycle_time

    def _tick_state(self, dt):
        if self.state == "idle":
            return
        self.timer -= dt
        if self.state == "reload":
            if not self.reload_applied and self.progress >= 0.82:
                need = self.stats.mag_size - self.ammo
                take = min(need, self.reserve)
                self.ammo += take
                self.reserve -= take
                self.reload_applied = True
            if self.timer <= 0:
                self.state = "idle"
        elif self.state == "shell":
            if self.timer > 0:
                return
            if self.phase == "start":
                self.phase = "loop"
                self.timer = self.total = self.stats.shell_time
            elif self.phase == "loop":
                if self.reserve > 0 and self.ammo < self.stats.mag_size:
                    self.ammo += 1
                    self.reserve -= 1
                if self.ammo >= self.stats.mag_size or self.reserve <= 0:
                    self.phase = "end"
                    t = SHELL_END_TIME + (self.defn.cycle_time if self.needs_pump_after_reload else 0)
                    self.timer = self.total = t
                else:
                    self.timer = self.total = self.stats.shell_time
            else:
                self.state = "idle"
                self.phase = ""
        else:  # draw / cycle / attach / inspect
            if self.timer <= 0:
                self.state = "idle"
                self.timer = 0.0

    # ── 序列化 ──
    def to_dict(self):
        return dict(id=self.id, atts=self.atts, ammo=self.ammo, reserve=self.reserve,
                    mode=self.mode_idx, st=self.state, ph=self.phase,
                    tm=round(self.timer, 4), tt=round(self.total, 4), cd=round(self.cooldown, 4),
                    sc=self.shot_counter, rc=self.reload_counter, er=self.empty_reload,
                    bl=round(self.bloom, 3), sr=self.shots_in_row)

    @staticmethod
    def from_dict(d, existing=None):
        w = existing if (existing and existing.id == d["id"]) else WeaponInstance(d["id"], d["atts"])
        if w.atts != d["atts"]:
            w.atts = sanitize(w.defn, d["atts"])
            w.stats = compute_stats(w.defn, w.atts)
        w.ammo, w.reserve, w.mode_idx = d["ammo"], d["reserve"], d["mode"]
        w.state, w.phase, w.timer, w.total = d["st"], d["ph"], d["tm"], d["tt"]
        w.cooldown, w.shot_counter, w.reload_counter = d["cd"], d["sc"], d["rc"]
        w.empty_reload, w.bloom, w.shots_in_row = d["er"], d["bl"], d["sr"]
        return w
