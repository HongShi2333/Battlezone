"""
武器定义 (纯数据)。
基于现实枪械进行游戏化改造，数值为平衡后的游戏数值。
新增武器：往 WEAPONS 里加一个 WeaponDef 即可，渲染层会根据 model 参数程序化建模。
"""
from dataclasses import dataclass, field
from typing import List, Dict

PISTOL, RIFLE, SNIPER, SHOTGUN = "pistol", "rifle", "sniper", "shotgun"
CATEGORY_NAMES = {PISTOL: "手枪", RIFLE: "步枪", SNIPER: "狙击枪", SHOTGUN: "霰弹枪"}
PRIMARY_CATEGORIES = [RIFLE, SNIPER, SHOTGUN]
SECONDARY_CATEGORIES = [PISTOL]


@dataclass
class WeaponDef:
    id: str
    name: str                     # 显示名
    real: str                     # 原型 / 改造说明
    category: str
    caliber: str
    # 伤害
    damage_near: float
    damage_far: float
    range_near: float             # 该距离内满伤
    range_far: float              # 该距离外最低伤害
    headshot_mult: float = 1.8
    limb_mult: float = 0.9
    pellets: int = 1
    # 射击
    rpm: float = 600
    fire_modes: List[str] = field(default_factory=lambda: ["auto"])   # auto/semi/burst/bolt/pump
    burst_count: int = 3
    mag_size: int = 30
    reserve_mags: int = 4
    reload_time: float = 2.1      # 战术换弹
    reload_empty_time: float = 2.7  # 空仓换弹
    shell_reload: bool = False    # 逐发装填 (霰弹)
    shell_time: float = 0.5
    cycle_time: float = 0.0       # 拉栓/泵动时间
    # 精度 (度)
    spread_hip: float = 3.0
    spread_ads: float = 0.15
    spread_move: float = 1.5
    spread_per_shot: float = 0.25
    spread_max_bloom: float = 2.0
    # 后坐力 (度/发)
    recoil_v: float = 0.45
    recoil_h: float = 0.20
    recoil_bias: float = 0.1      # 水平偏向 (+右)
    recoil_first: float = 1.3     # 第一发倍率
    recoil_recovery: float = 9.0
    visual_kick: float = 1.0
    # 操控
    ads_time: float = 0.25
    draw_time: float = 0.55
    move_mult: float = 1.0
    sprint_to_fire: float = 0.16
    tracer_color: tuple = (1.0, 0.85, 0.45)
    sound: str = "rifle"
    model: Dict = field(default_factory=dict)
    default_atts: Dict = field(default_factory=dict)

    @property
    def slot(self):
        return "secondary" if self.category == PISTOL else "primary"


WEAPONS: Dict[str, WeaponDef] = {}


def _reg(w: WeaponDef):
    WEAPONS[w.id] = w
    return w


# ═══════════════════════ 手枪 ═══════════════════════
_reg(WeaponDef(
    id="p320", name="P320-M17", real="SIG Sauer P320 / 美军 M17 — 模块化框架, 缩短套筒改造",
    category=PISTOL, caliber="9x19mm",
    damage_near=32, damage_far=21, range_near=12, range_far=40,
    rpm=420, fire_modes=["semi"], mag_size=17, reserve_mags=5,
    reload_time=1.45, reload_empty_time=1.8,
    spread_hip=1.6, spread_ads=0.25, spread_move=0.8, spread_per_shot=0.35,
    recoil_v=1.4, recoil_h=0.35, recoil_first=1.0, ads_time=0.16, draw_time=0.35,
    move_mult=1.05, sprint_to_fire=0.1, sound="pistol",
    model=dict(kind="pistol", color=(0.62, 0.52, 0.36), slide=(0.12, 0.12, 0.12), length=0.20),
    default_atts={"optic": "iron"},
))
_reg(WeaponDef(
    id="g17", name="G17 Gen5", real="Glock 17 第五代 — 加装扩容握把套, 竞技扳机",
    category=PISTOL, caliber="9x19mm",
    damage_near=30, damage_far=20, range_near=12, range_far=40,
    rpm=460, fire_modes=["semi"], mag_size=17, reserve_mags=5,
    reload_time=1.35, reload_empty_time=1.7,
    spread_hip=1.5, spread_ads=0.22, spread_move=0.8, spread_per_shot=0.3,
    recoil_v=1.25, recoil_h=0.3, recoil_first=1.0, ads_time=0.15, draw_time=0.32,
    move_mult=1.05, sprint_to_fire=0.1, sound="pistol",
    model=dict(kind="pistol", color=(0.10, 0.10, 0.10), slide=(0.16, 0.16, 0.17), length=0.19),
    default_atts={"optic": "iron"},
))
_reg(WeaponDef(
    id="g18c", name="G18C Auto", real="Glock 18C — 全自动冲锋手枪, 枪管泄气孔改造, 33发长弹匣",
    category=PISTOL, caliber="9x19mm",
    damage_near=22, damage_far=14, range_near=9, range_far=30,
    rpm=1100, fire_modes=["auto", "semi"], mag_size=33, reserve_mags=4,
    reload_time=1.6, reload_empty_time=2.0,
    spread_hip=2.2, spread_ads=0.6, spread_move=1.0, spread_per_shot=0.18, spread_max_bloom=2.6,
    recoil_v=0.75, recoil_h=0.45, recoil_bias=0.15, recoil_first=1.0, ads_time=0.17, draw_time=0.35,
    move_mult=1.05, sprint_to_fire=0.1, sound="pistol",
    model=dict(kind="pistol", color=(0.12, 0.12, 0.12), slide=(0.20, 0.20, 0.21), length=0.19,
               long_mag=True, comp=True),
    default_atts={"optic": "iron"},
))
_reg(WeaponDef(
    id="deagle", name="Desert Eagle", real="IMI 沙漠之鹰 Mk XIX .50AE — 加重枪口配重块",
    category=PISTOL, caliber=".50 AE",
    damage_near=62, damage_far=40, range_near=15, range_far=50, headshot_mult=2.0,
    rpm=240, fire_modes=["semi"], mag_size=7, reserve_mags=5,
    reload_time=1.9, reload_empty_time=2.3,
    spread_hip=2.4, spread_ads=0.2, spread_move=1.2, spread_per_shot=0.9,
    recoil_v=3.8, recoil_h=0.8, recoil_first=1.0, recoil_recovery=6.0, visual_kick=1.8,
    ads_time=0.2, draw_time=0.45, move_mult=1.0, sprint_to_fire=0.12, sound="magnum",
    model=dict(kind="pistol", color=(0.55, 0.56, 0.58), slide=(0.60, 0.61, 0.63), length=0.26, big=True),
    default_atts={"optic": "iron"},
))

# ═══════════════════════ 步枪 ═══════════════════════
_reg(WeaponDef(
    id="m4a1", name="M4A1 Block II", real="Colt M4A1 SOPMOD Block II — 14.5\" 枪管, RIS II 护木",
    category=RIFLE, caliber="5.56x45mm NATO",
    damage_near=25, damage_far=18, range_near=25, range_far=70,
    rpm=800, fire_modes=["auto", "semi"], mag_size=30, reserve_mags=4,
    reload_time=2.0, reload_empty_time=2.55,
    spread_hip=2.6, spread_ads=0.12, spread_move=1.4, spread_per_shot=0.08,
    recoil_v=0.42, recoil_h=0.22, recoil_bias=0.08, ads_time=0.24,
    model=dict(kind="rifle", color=(0.13, 0.13, 0.12), furniture=(0.15, 0.14, 0.13),
               barrel=0.36, receiver=0.42, stock="m4", mag="stanag", handguard="ris"),
    default_atts={"optic": "reddot"},
))
_reg(WeaponDef(
    id="qbz191", name="QBZ-191", real="191式自动步枪 — 常规布局, 伸缩枪托, 5.8mm 新弹",
    category=RIFLE, caliber="5.8x42mm DBP191",
    damage_near=27, damage_far=20, range_near=28, range_far=75,
    rpm=750, fire_modes=["auto", "semi"], mag_size=30, reserve_mags=4,
    reload_time=2.1, reload_empty_time=2.6,
    spread_hip=2.5, spread_ads=0.10, spread_move=1.4, spread_per_shot=0.07,
    recoil_v=0.38, recoil_h=0.18, recoil_bias=-0.05, ads_time=0.25,
    model=dict(kind="rifle", color=(0.22, 0.23, 0.18), furniture=(0.28, 0.29, 0.22),
               barrel=0.38, receiver=0.44, stock="191", mag="curved", handguard="smooth"),
    default_atts={"optic": "holo"},
))
_reg(WeaponDef(
    id="qbz951", name="QBZ-95-1", real="95-1式自动步枪 — 无托结构, 加长提把导轨改造",
    category=RIFLE, caliber="5.8x42mm DBP10",
    damage_near=28, damage_far=20, range_near=26, range_far=70,
    rpm=650, fire_modes=["auto", "semi"], mag_size=30, reserve_mags=4,
    reload_time=2.35, reload_empty_time=2.95,
    spread_hip=2.3, spread_ads=0.12, spread_move=1.3, spread_per_shot=0.08,
    recoil_v=0.40, recoil_h=0.16, recoil_bias=0.04, ads_time=0.22, move_mult=1.03,
    model=dict(kind="bullpup", color=(0.20, 0.21, 0.17), furniture=(0.24, 0.25, 0.20),
               barrel=0.30, receiver=0.52, mag="curved"),
    default_atts={"optic": "reddot"},
))
_reg(WeaponDef(
    id="ak12", name="AK-12 (2023)", real="卡拉什尼科夫 AK-12 2023 版 — 改进折叠托, 2 连发模式",
    category=RIFLE, caliber="5.45x39mm",
    damage_near=27, damage_far=19, range_near=24, range_far=65,
    rpm=700, fire_modes=["auto", "burst", "semi"], burst_count=2, mag_size=30, reserve_mags=4,
    reload_time=2.2, reload_empty_time=2.8,
    spread_hip=2.7, spread_ads=0.14, spread_move=1.5, spread_per_shot=0.09,
    recoil_v=0.46, recoil_h=0.26, recoil_bias=0.12, ads_time=0.26,
    model=dict(kind="rifle", color=(0.12, 0.12, 0.11), furniture=(0.14, 0.13, 0.12),
               barrel=0.38, receiver=0.44, stock="folding", mag="ak", handguard="ak"),
    default_atts={"optic": "iron"},
))
_reg(WeaponDef(
    id="scarh", name="SCAR-H", real="FN SCAR-H Mk17 — 7.62 战斗步枪, 缩短 13\" 枪管",
    category=RIFLE, caliber="7.62x51mm NATO",
    damage_near=35, damage_far=27, range_near=30, range_far=85,
    rpm=580, fire_modes=["auto", "semi"], mag_size=20, reserve_mags=5,
    reload_time=2.25, reload_empty_time=2.8,
    spread_hip=2.9, spread_ads=0.12, spread_move=1.6, spread_per_shot=0.14,
    recoil_v=0.72, recoil_h=0.32, recoil_bias=0.1, visual_kick=1.3, ads_time=0.29, move_mult=0.96,
    sound="battle",
    model=dict(kind="rifle", color=(0.55, 0.47, 0.34), furniture=(0.15, 0.14, 0.13),
               barrel=0.34, receiver=0.46, stock="scar", mag="box20", handguard="scar"),
    default_atts={"optic": "reddot"},
))

# ═══════════════════════ 狙击枪 ═══════════════════════
_reg(WeaponDef(
    id="awm", name="AWM .338", real="Accuracy International AWM — .338 Lapua 马格南, 折叠枪托",
    category=SNIPER, caliber=".338 Lapua Magnum",
    damage_near=105, damage_far=85, range_near=60, range_far=200, headshot_mult=2.5, limb_mult=0.85,
    rpm=45, fire_modes=["bolt"], cycle_time=1.05, mag_size=5, reserve_mags=5,
    reload_time=3.0, reload_empty_time=3.6,
    spread_hip=6.0, spread_ads=0.0, spread_move=4.0, spread_per_shot=0.0,
    recoil_v=5.0, recoil_h=0.8, recoil_first=1.0, recoil_recovery=5.0, visual_kick=2.2,
    ads_time=0.38, draw_time=0.8, move_mult=0.9, sprint_to_fire=0.25,
    tracer_color=(1.0, 0.9, 0.7), sound="sniper",
    model=dict(kind="sniper", color=(0.30, 0.34, 0.24), furniture=(0.30, 0.34, 0.24),
               barrel=0.62, receiver=0.40, stock="aw", mag="box5", bolt=True),
    default_atts={"optic": "x8"},
))
_reg(WeaponDef(
    id="m82", name="M82A1 Barrett", real="巴雷特 M82A1 — .50 BMG 半自动反器材步枪, 双室制退器",
    category=SNIPER, caliber=".50 BMG",
    damage_near=100, damage_far=90, range_near=80, range_far=250, headshot_mult=2.3, limb_mult=0.9,
    rpm=140, fire_modes=["semi"], mag_size=10, reserve_mags=3,
    reload_time=3.3, reload_empty_time=4.0,
    spread_hip=7.0, spread_ads=0.05, spread_move=5.0, spread_per_shot=0.6,
    recoil_v=6.5, recoil_h=1.2, recoil_first=1.0, recoil_recovery=4.5, visual_kick=2.6,
    ads_time=0.48, draw_time=1.0, move_mult=0.82, sprint_to_fire=0.3,
    tracer_color=(1.0, 0.8, 0.5), sound="fifty",
    model=dict(kind="sniper", color=(0.16, 0.16, 0.15), furniture=(0.18, 0.18, 0.17),
               barrel=0.70, receiver=0.55, stock="barrett", mag="box10", brake=True),
    default_atts={"optic": "x8", "underbarrel": "bipod"},
))
_reg(WeaponDef(
    id="qbu88", name="QBU-88", real="88式狙击步枪 — 无托精确射手步枪, 加装全尺寸导轨",
    category=SNIPER, caliber="5.8x42mm DVP88",
    damage_near=52, damage_far=44, range_near=50, range_far=150, headshot_mult=2.2,
    rpm=320, fire_modes=["semi"], mag_size=10, reserve_mags=5,
    reload_time=2.4, reload_empty_time=2.9,
    spread_hip=4.0, spread_ads=0.05, spread_move=2.5, spread_per_shot=0.3,
    recoil_v=1.6, recoil_h=0.4, recoil_first=1.0, recoil_recovery=7.0, visual_kick=1.4,
    ads_time=0.3, draw_time=0.6, move_mult=0.96, sprint_to_fire=0.2, sound="dmr",
    model=dict(kind="bullpup", color=(0.18, 0.19, 0.15), furniture=(0.22, 0.23, 0.18),
               barrel=0.48, receiver=0.55, mag="box10"),
    default_atts={"optic": "x4"},
))
_reg(WeaponDef(
    id="svd", name="SVD Dragunov", real="德拉贡诺夫 SVD — 7.62x54R, 合成材料枪托现代化改造",
    category=SNIPER, caliber="7.62x54mmR",
    damage_near=62, damage_far=52, range_near=55, range_far=170, headshot_mult=2.2,
    rpm=260, fire_modes=["semi"], mag_size=10, reserve_mags=4,
    reload_time=2.6, reload_empty_time=3.1,
    spread_hip=4.5, spread_ads=0.05, spread_move=2.8, spread_per_shot=0.4,
    recoil_v=2.3, recoil_h=0.5, recoil_first=1.0, recoil_recovery=6.5, visual_kick=1.6,
    ads_time=0.33, draw_time=0.65, move_mult=0.94, sprint_to_fire=0.22, sound="dmr",
    model=dict(kind="sniper", color=(0.12, 0.12, 0.11), furniture=(0.40, 0.25, 0.14),
               barrel=0.60, receiver=0.42, stock="svd", mag="box10"),
    default_atts={"optic": "x4"},
))

# ═══════════════════════ 霰弹枪 ═══════════════════════
_reg(WeaponDef(
    id="m870", name="M870 MCS", real="雷明顿 870 MCS — 泵动式, 模块化战斗霰弹枪",
    category=SHOTGUN, caliber="12 Gauge 00 Buck",
    damage_near=20, damage_far=6, range_near=8, range_far=28, headshot_mult=1.4, pellets=8,
    rpm=70, fire_modes=["pump"], cycle_time=0.62, mag_size=7, reserve_mags=4,
    shell_reload=True, shell_time=0.48, reload_time=0.45, reload_empty_time=0.9,
    spread_hip=4.2, spread_ads=3.2, spread_move=0.8, spread_per_shot=0.0,
    recoil_v=4.0, recoil_h=0.9, recoil_first=1.0, recoil_recovery=6.0, visual_kick=2.0,
    ads_time=0.26, draw_time=0.55, move_mult=0.98, tracer_color=(1.0, 0.75, 0.4), sound="shotgun",
    model=dict(kind="shotgun", color=(0.10, 0.10, 0.10), furniture=(0.13, 0.12, 0.11),
               barrel=0.46, receiver=0.24, stock="m4", pump=True),
    default_atts={"optic": "iron"},
))
_reg(WeaponDef(
    id="spas12", name="SPAS-12", real="弗兰基 SPAS-12 — 泵动/半自动双模式, 折叠顶托",
    category=SHOTGUN, caliber="12 Gauge",
    damage_near=18, damage_far=5, range_near=8, range_far=26, headshot_mult=1.4, pellets=8,
    rpm=160, fire_modes=["semi", "pump"], cycle_time=0.55, mag_size=8, reserve_mags=4,
    shell_reload=True, shell_time=0.45, reload_time=0.45, reload_empty_time=0.85,
    spread_hip=4.6, spread_ads=3.6, spread_move=0.9, spread_per_shot=0.2,
    recoil_v=3.4, recoil_h=0.9, recoil_first=1.0, recoil_recovery=6.5, visual_kick=1.8,
    ads_time=0.28, draw_time=0.6, move_mult=0.96, tracer_color=(1.0, 0.75, 0.4), sound="shotgun",
    model=dict(kind="shotgun", color=(0.16, 0.16, 0.16), furniture=(0.14, 0.14, 0.14),
               barrel=0.48, receiver=0.26, stock="folding", pump=True, heatshield=True),
    default_atts={"optic": "iron"},
))
_reg(WeaponDef(
    id="saiga12", name="Saiga-12K", real="赛加-12K — 半自动弹匣供弹霰弹枪, AK 平台改造",
    category=SHOTGUN, caliber="12 Gauge",
    damage_near=15, damage_far=4, range_near=7, range_far=22, headshot_mult=1.4, pellets=8,
    rpm=280, fire_modes=["semi"], mag_size=8, reserve_mags=4,
    reload_time=2.4, reload_empty_time=2.9,
    spread_hip=4.8, spread_ads=3.8, spread_move=1.0, spread_per_shot=0.3,
    recoil_v=2.7, recoil_h=1.0, recoil_first=1.0, recoil_recovery=7.0, visual_kick=1.5,
    ads_time=0.27, draw_time=0.6, move_mult=0.97, tracer_color=(1.0, 0.75, 0.4), sound="shotgun",
    model=dict(kind="rifle", color=(0.11, 0.11, 0.10), furniture=(0.13, 0.12, 0.11),
               barrel=0.34, receiver=0.42, stock="folding", mag="saiga", handguard="ak", thick_barrel=True),
    default_atts={"optic": "iron"},
))
_reg(WeaponDef(
    id="qbs09", name="QBS-09", real="09式霰弹枪 — 泵动/半自动, 加长弹仓改造",
    category=SHOTGUN, caliber="18.4mm (12 Gauge)",
    damage_near=21, damage_far=6, range_near=9, range_far=30, headshot_mult=1.4, pellets=8,
    rpm=75, fire_modes=["pump"], cycle_time=0.58, mag_size=6, reserve_mags=5,
    shell_reload=True, shell_time=0.46, reload_time=0.45, reload_empty_time=0.85,
    spread_hip=4.0, spread_ads=3.0, spread_move=0.8, spread_per_shot=0.0,
    recoil_v=4.2, recoil_h=0.8, recoil_first=1.0, recoil_recovery=6.0, visual_kick=2.0,
    ads_time=0.26, draw_time=0.55, move_mult=0.98, tracer_color=(1.0, 0.75, 0.4), sound="shotgun",
    model=dict(kind="shotgun", color=(0.19, 0.20, 0.16), furniture=(0.22, 0.23, 0.18),
               barrel=0.44, receiver=0.25, stock="fixed", pump=True),
    default_atts={"optic": "iron"},
))


def weapons_in(category):
    return [w for w in WEAPONS.values() if w.category == category]


def primary_weapons():
    return [w for w in WEAPONS.values() if w.category in PRIMARY_CATEGORIES]


def secondary_weapons():
    return [w for w in WEAPONS.values() if w.category in SECONDARY_CATEGORIES]
