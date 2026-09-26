"""键鼠 → InputCommand (按键在帧之间"锁存", 保证快速点按不会在两个 tick 之间丢失)"""
import math
import pygame
from core import settings as S
from core.commands import InputCommand, Btn
from core.mathutil import clamp

KEY_BUTTONS = {
    "sprint": Btn.SPRINT, "jump": Btn.JUMP, "crouch": Btn.CROUCH, "crouch_alt": Btn.CROUCH,
    "prone": Btn.PRONE, "reload": Btn.RELOAD, "primary": Btn.PRIMARY, "secondary": Btn.SECONDARY,
    "firemode": Btn.FIREMODE, "inspect": Btn.INSPECT, "lean_left": Btn.LEAN_L, "lean_right": Btn.LEAN_R,
}


class InputSampler:
    def __init__(self):
        self.keys = {}
        for action, name in S.KEYBINDS.items():
            try:
                self.keys[action] = pygame.key.key_code(name)
            except (ValueError, AttributeError):
                self.keys[action] = None
        self.yaw = 0.0
        self.pitch = 0.0
        self.seq = 0
        self.latched = 0
        self.last_dx = 0.0
        self.last_dy = 0.0
        self.sprint_active = False
        self.override = None        # 自动测试: 脚本化输入

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            if self.keys.get("sprint") == e.key:
                self.sprint_active = True
            for action, b in KEY_BUTTONS.items():
                if self.keys.get(action) == e.key:
                    self.latched |= b
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 1:
                self.latched |= Btn.FIRE
            elif e.button == 3:
                self.latched |= Btn.ADS
        elif e.type == pygame.MOUSEWHEEL:
            if e.y != 0:
                self.latched |= Btn.SWAP

    def look(self, dx, dy, sens):
        self.last_dx, self.last_dy = dx, dy
        k = S.MOUSE_SENSITIVITY * sens
        self.yaw += dx * k
        self.pitch = clamp(self.pitch - dy * k, -math.radians(88), math.radians(88))
        self.yaw = (self.yaw + math.pi) % (2 * math.pi) - math.pi

    def build(self, dt, allow_move=True, allow_combat=True):
        self.seq += 1
        cmd = InputCommand(seq=self.seq, dt=dt, yaw=self.yaw, pitch=self.pitch)
        if self.override is not None:
            mf, mr, btn = self.override
            cmd.move_f, cmd.move_r, cmd.buttons = mf, mr, btn
            return cmd
        k = pygame.key.get_pressed()
        mb = pygame.mouse.get_pressed()
        btn = self.latched
        self.latched = 0

        def held(action):
            code = self.keys.get(action)
            return code is not None and k[code]

        if allow_move:
            cmd.move_f = (1.0 if held("forward") else 0.0) - (1.0 if held("back") else 0.0)
            cmd.move_r = (1.0 if held("right") else 0.0) - (1.0 if held("left") else 0.0)
            if held("sprint"):
                self.sprint_active = True
            if cmd.move_f <= 0.1 or mb[0] or mb[2] or held("prone"):
                self.sprint_active = False
            for action, b in KEY_BUTTONS.items():
                if held(action):
                    btn |= b
            if self.sprint_active and cmd.move_f > 0.1:
                btn |= Btn.SPRINT
        else:
            self.sprint_active = False
            btn &= ~(Btn.JUMP | Btn.CROUCH | Btn.PRONE | Btn.SPRINT)
        if allow_combat:
            if mb[0]:
                btn |= Btn.FIRE
            if mb[2]:
                btn |= Btn.ADS
        else:
            btn &= ~(Btn.FIRE | Btn.ADS | Btn.RELOAD | Btn.SWAP | Btn.PRIMARY | Btn.SECONDARY)
        cmd.buttons = btn
        return cmd
