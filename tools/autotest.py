"""
自动化测试: 脚本化输入 + 截图 (开发调试用)
    python main.py --autotest screens
"""
import os
from core.commands import Btn


class AutoTest:
    def __init__(self, outdir):
        self.out = outdir
        os.makedirs(outdir, exist_ok=True)
        self.frame = 0
        self.mouse = (0, 0)
        self.script = []
        self._build()

    def at(self, f, fn):
        self.script.append((f, fn))

    def _build(self):
        B = Btn
        if self.out.rstrip("/").endswith("net"):
            self.at(90, lambda app: app._deploy())
            self.at(92, lambda app: setattr(app.input, "override", (1.0, 0.0, 0)))
            self.at(200, lambda app: app.screenshot(os.path.join(self.out, "net_play.png")))
            self.at(205, lambda app: setattr(app, "running", False))
            self.script.sort(key=lambda x: x[0])
            return

        def ov(mf=0.0, mr=0.0, b=0):
            return lambda app: setattr(app.input, "override", (mf, mr, b))

        def shot(name):
            return lambda app: app.screenshot(os.path.join(self.out, name + ".png"))

        def prefs(**kw):
            def f(app):
                app.prefs.data.update(kw)
            return f

        def redeploy(app):
            p = app.me
            app.session.world._kill(p, None, None, False)
            p.respawn_t = 0
            app.death_info = None
            app.mode = "loadout"

        f = 0
        self.at(40, shot("01_menu"))
        self.at(45, prefs(primary="m4a1", secondary="p320", enemy_bots=5, friendly_bots=4,
                          atts={"m4a1": {"optic": "holo", "muzzle": "compensator", "underbarrel": "vgrip", "magazine": "mag_std"}}))
        self.at(50, lambda app: app.start_single())
        self.at(90, shot("02_loadout"))
        self.at(95, lambda app: app._deploy())
        self.at(96, ov())
        self.at(150, shot("03_hip"))
        self.at(155, ov(0, 0, B.ADS))
        self.at(190, shot("04_ads"))
        self.at(192, ov(0, 0, B.ADS | B.FIRE))
        self.at(197, shot("05_fire"))
        self.at(200, ov(1.0, 0, B.SPRINT))
        self.at(250, shot("06_sprint"))
        self.at(252, ov(1.0, 0, B.SPRINT | B.CROUCH))
        self.at(262, shot("07_slide"))
        self.at(275, ov(0, 0, 0))
        self.at(300, shot("08_crouch"))
        self.at(305, ov(0, 0, B.PRONE))
        self.at(307, ov(0, 0, 0))
        self.at(360, shot("09_prone"))
        self.at(362, ov(0, 0, B.JUMP))
        self.at(364, ov(0, 0, 0))
        self.at(400, ov(0, 0, B.FIRE))
        self.at(430, ov(0, 0, 0))
        self.at(432, ov(0, 0, B.RELOAD))
        self.at(434, ov(0, 0, 0))
        self.at(470, shot("10_reload_out"))
        self.at(500, shot("11_reload_in"))
        self.at(600, ov(0, 0, B.LEAN_R))
        self.at(630, shot("12_lean"))
        self.at(632, ov(0, 0, B.SECONDARY))
        self.at(634, ov(0, 0, 0))
        self.at(680, shot("13_pistol"))
        self.at(682, ov(0, 0, B.ADS))
        self.at(710, shot("14_pistol_ads"))
        self.at(712, ov(0, 0, 0))
        self.at(715, lambda app: app._open_plus_ingame())
        self.at(740, shot("15_plus_menu"))
        self.at(742, lambda app: app.plus.close())
        # 狙击枪
        self.at(745, prefs(primary="awm", atts={"awm": {"optic": "x8", "muzzle": "suppressor", "underbarrel": "bipod", "magazine": "mag_std"}}))
        self.at(746, redeploy)
        self.at(750, lambda app: app._deploy())
        self.at(800, shot("16_sniper_hip"))
        self.at(802, ov(0, 0, B.ADS))
        self.at(850, shot("17_sniper_scope"))
        self.at(852, ov(0, 0, B.ADS | B.FIRE))
        self.at(854, ov(0, 0, B.ADS))
        self.at(880, shot("18_bolt_cycle"))
        self.at(900, ov(0, 0, 0))
        # 霰弹枪
        self.at(905, prefs(primary="m870"))
        self.at(906, redeploy)
        self.at(910, lambda app: app._deploy())
        self.at(960, ov(0, 0, B.FIRE))
        self.at(962, ov(0, 0, 0))
        self.at(975, shot("19_pump"))
        self.at(1010, ov(0, 0, B.RELOAD))
        self.at(1012, ov(0, 0, 0))
        self.at(1050, shot("20_shell_reload"))
        # 其它武器外观
        self.at(1100, prefs(primary="qbz951", atts={"qbz951": {"optic": "x4", "muzzle": "suppressor", "underbarrel": "agrip", "magazine": "mag_ext"}}))
        self.at(1101, redeploy)
        self.at(1105, lambda app: app._deploy())
        self.at(1160, shot("21_qbz951"))
        self.at(1165, prefs(primary="qbz191", atts={"qbz191": {"optic": "reddot", "muzzle": "flashhider", "underbarrel": "laser", "magazine": "mag_drum"}}))
        self.at(1166, redeploy)
        self.at(1170, lambda app: app._deploy())
        self.at(1225, shot("22_qbz191"))
        self.at(1226, ov(0, 0, B.ADS))
        self.at(1260, shot("23_qbz191_ads"))
        self.at(1262, ov(0, 0, B.INSPECT))
        self.at(1264, ov(0, 0, 0))
        self.at(1300, shot("24_inspect"))
        self.at(1302, lambda app: setattr(app, "show_scores", True))
        self.at(1305, shot("25_scoreboard"))
        self.at(1306, lambda app: setattr(app, "show_scores", False))
        self.at(1310, lambda app: setattr(app, "running", False))
        self.script.sort(key=lambda x: x[0])

    def step(self, app):
        self.frame += 1
        while self.script and self.script[0][0] <= self.frame:
            _, fn = self.script.pop(0)
            fn(app)
