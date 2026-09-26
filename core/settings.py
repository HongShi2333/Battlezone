"""
全局配置 — 所有可调参数集中管理。
注意：本文件为 *纯数据*，不得 import pygame / OpenGL，
因为它同时被客户端和无头服务器 (dedicated server) 使用。
"""
import math

# ── 版本 / 网络 ────────────────────────────────────────
GAME_VERSION = "0.3.0"
TICK_RATE = 60                      # 模拟频率 (Hz) — 客户端与服务器一致
TICK_DT = 1.0 / TICK_RATE
SNAPSHOT_RATE = 30                  # 服务器快照广播频率
DEFAULT_PORT = 27960

# ── 窗口 ─────────────────────────────────────────────
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS_CAP = 144
WINDOW_TITLE = "PORTAL STRIKE 2042 — Python FPS"

# ── 鼠标 ─────────────────────────────────────────────
MOUSE_SENSITIVITY = 0.0022         # rad/pixel
ADS_SENSITIVITY_MULTIPLIER = 0.65  # 开镜灵敏度系数 (再乘以 1/倍率)

# ── 玩家尺寸 (米) ────────────────────────────────────
PLAYER_RADIUS = 0.32
EYE_STAND  = 1.65
EYE_CROUCH = 1.12
EYE_PRONE  = 0.38
EYE_SLIDE  = 0.95
BODY_STAND  = 1.85                 # 碰撞盒高度
BODY_CROUCH = 1.30
BODY_PRONE  = 0.60
BODY_SLIDE  = 1.10
EYE_LERP_SPEED = 9.0               # 姿态切换时眼高插值速度

# ── 移动速度 (m/s) ───────────────────────────────────
WALK_SPEED   = 4.6
SPRINT_SPEED = 7.4
CROUCH_SPEED = 2.6
PRONE_SPEED  = 1.0
ADS_MOVE_MULT = 0.62
GROUND_ACCEL = 60.0
AIR_ACCEL    = 6.0
GROUND_FRICTION = 12.0

SLIDE_BOOST     = 9.8              # 滑铲起始速度
SLIDE_DURATION  = 0.80
SLIDE_FRICTION  = 3.2
SLIDE_COOLDOWN  = 0.9
SLIDE_MIN_SPEED = 5.5              # 需要达到的冲刺速度才能滑铲

GRAVITY = -19.6
JUMP_VELOCITY = 6.4
STEP_HEIGHT = 0.42                 # 可自动跨上的台阶高度
MANTLE_MIN = 0.45                  # 翻越高度范围
MANTLE_MAX = 1.65
MANTLE_TIME = 0.42

PRONE_HOLD_TIME = 0.38             # 长按 C 进入趴下
PRONE_TRANSITION = 0.55            # 进入/离开趴下的动作时间 (期间不能开火)
SPRINT_TO_FIRE = 0.16              # 冲刺后可开火的延迟
LEAN_OFFSET = 0.38                 # 侧身偏移距离
LEAN_ANGLE = 13.0                  # 侧身倾角 (度)

MAX_HEALTH = 100
REGEN_DELAY = 6.0
REGEN_RATE = 18.0
RESPAWN_TIME = 4.0

# ── FOV (度) ─────────────────────────────────────────
FOV_BASE   = 78
FOV_SPRINT_ADD = 6
FOV_SLIDE_ADD  = 10
FOV_LERP_SPEED = 10.0
VIEWMODEL_FOV = 58

# ── 世界 ─────────────────────────────────────────────
FOG_START = 35.0
FOG_END = 190.0
FOG_COLOR = (0.62, 0.60, 0.56)
SKY_TOP = (0.36, 0.45, 0.55)
SKY_HORIZON = (0.80, 0.72, 0.60)
SUN_DIR = (0.45, 0.75, 0.35)

# ── 队伍 ─────────────────────────────────────────────
TEAM_BLUE = 0
TEAM_RED = 1
TEAM_NAMES = {TEAM_BLUE: "BLUFOR", TEAM_RED: "OPFOR"}
TEAM_COLORS = {TEAM_BLUE: (0.30, 0.65, 1.0), TEAM_RED: (1.0, 0.32, 0.25)}
SCORE_LIMIT = 50

# ── 按键 (pygame 按键名, 由客户端解析) ────────────────
KEYBINDS = {
    "forward": "w", "back": "s", "left": "a", "right": "d",
    "sprint": "left shift", "jump": "space",
    "crouch": "c", "crouch_alt": "left ctrl", "prone": "x",
    "reload": "r", "primary": "1", "secondary": "2",
    "firemode": "b", "attachments": "z", "inspect": "t",
    "lean_left": "q", "lean_right": "e",
    "scoreboard": "tab", "pause": "escape",
}

def deg(r):
    return r * 180.0 / math.pi
