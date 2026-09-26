"""
配件系统 (纯数据 + 属性计算)。
按 Z 打开的 "Plus 配件菜单" 四个方向对应四个槽位:
    上 = 瞄具(optic)   左 = 枪口(muzzle)   右 = 下挂(underbarrel)   下 = 弹匣(magazine)
"""
from dataclasses import dataclass, field, replace
from typing import Dict, Set
from .definitions import WeaponDef, PISTOL, RIFLE, SNIPER, SHOTGUN, WEAPONS

SLOTS = ["optic", "muzzle", "underbarrel", "magazine"]
SLOT_NAMES = {"optic": "瞄具", "muzzle": "枪口", "underbarrel": "下挂", "magazine": "弹匣"}
SLOT_DIRECTION = {"optic": "up", "muzzle": "left", "underbarrel": "right", "magazine": "down"}

ALL = {PISTOL, RIFLE, SNIPER, SHOTGUN}
LONG = {RIFLE, SNIPER, SHOTGUN}


@dataclass
class AttachmentDef:
    id: str
    slot: str
    name: str
    desc: str
    categories: Set[str]
    mods: Dict[str, float] = field(default_factory=dict)   # 乘法修正
    adds: Dict[str, float] = field(default_factory=dict)   # 加法修正
    zoom: float = 0.0              # 仅瞄具: 放大倍率
    scope_overlay: bool = False    # 高倍镜使用全屏镜片覆盖
    reticle: str = ""              # dot / holo / chevron / mildot
    suppressed: bool = False
    flash_hidden: bool = False
    only: Set[str] = field(default_factory=set)   # 只允许特定武器 id
    exclude: Set[str] = field(default_factory=set)


ATTACHMENTS: Dict[str, AttachmentDef] = {}


def _a(a: AttachmentDef):
    ATTACHMENTS[a.id] = a


# ─── 瞄具 ───
_a(AttachmentDef("iron", "optic", "机械瞄具", "原厂机瞄, 视野最清晰", ALL, zoom=1.15))
_a(AttachmentDef("rmr", "optic", "RMR 微型红点", "Trijicon RMR, 手枪专用", {PISTOL}, zoom=1.25, reticle="dot",
                 mods={"ads_time": 1.05}))
_a(AttachmentDef("reddot", "optic", "T2 红点", "Aimpoint T2 1x 红点", {RIFLE, SHOTGUN}, zoom=1.3, reticle="dot",
                 mods={"ads_time": 1.03}))
_a(AttachmentDef("holo", "optic", "EXPS3 全息", "EOTech 全息, 圆环+中心点", {RIFLE, SHOTGUN}, zoom=1.35, reticle="holo",
                 mods={"ads_time": 1.05}))
_a(AttachmentDef("x3", "optic", "3x 棱镜", "紧凑 3 倍棱镜", {RIFLE, SNIPER}, zoom=3.0, reticle="chevron",
                 scope_overlay=True, mods={"ads_time": 1.15}))
_a(AttachmentDef("x4", "optic", "ACOG 4x", "Trijicon ACOG 4x32", {RIFLE, SNIPER}, zoom=4.0, reticle="chevron",
                 scope_overlay=True, mods={"ads_time": 1.2}))
_a(AttachmentDef("x8", "optic", "8x 狙击镜", "8 倍可变狙击镜", {SNIPER}, zoom=8.0, reticle="mildot",
                 scope_overlay=True, mods={"ads_time": 1.25}))
_a(AttachmentDef("x12", "optic", "12x 高倍镜", "远距离 12 倍镜, 开镜慢", {SNIPER}, zoom=12.0, reticle="mildot",
                 scope_overlay=True, mods={"ads_time": 1.4}))

# ─── 枪口 ───
_a(AttachmentDef("muzzle_std", "muzzle", "标准枪口", "无改装", ALL))
_a(AttachmentDef("suppressor", "muzzle", "消音器", "隐藏枪声与小地图红点, 有效射程降低", ALL - {SHOTGUN},
                 suppressed=True, flash_hidden=True, mods={"range_near": 0.85, "range_far": 0.9, "ads_time": 1.05}))
_a(AttachmentDef("compensator", "muzzle", "补偿器", "大幅降低水平后坐", ALL - {SHOTGUN},
                 mods={"recoil_h": 0.65, "recoil_v": 1.05}))
_a(AttachmentDef("flashhider", "muzzle", "消焰器", "隐藏枪口火光, 轻微降低垂直后坐", ALL - {SHOTGUN},
                 flash_hidden=True, mods={"recoil_v": 0.92}))
_a(AttachmentDef("brake", "muzzle", "制退器", "显著降低垂直后坐, 腰射精度降低", {RIFLE, SNIPER},
                 mods={"recoil_v": 0.75, "spread_hip": 1.12}))
_a(AttachmentDef("choke", "muzzle", "收束器", "弹丸散布 -35%", {SHOTGUN},
                 mods={"spread_hip": 0.65, "spread_ads": 0.65}))
_a(AttachmentDef("slug", "muzzle", "独头弹改装", "发射独头弹, 单发高伤远射程", {SHOTGUN},
                 mods={"spread_hip": 0.3, "spread_ads": 0.05, "range_near": 3.0, "range_far": 2.5},
                 adds={"pellets_set": 1, "damage_mult_slug": 4.6}))

# ─── 下挂 ───
_a(AttachmentDef("ub_none", "underbarrel", "无", "无下挂", ALL))
_a(AttachmentDef("vgrip", "underbarrel", "垂直握把", "垂直后坐 -15%", LONG,
                 mods={"recoil_v": 0.85}))
_a(AttachmentDef("agrip", "underbarrel", "斜握把", "开镜速度 +15%", LONG,
                 mods={"ads_time": 0.85}))
_a(AttachmentDef("laser", "underbarrel", "激光指示器", "腰射散布 -30%", ALL,
                 mods={"spread_hip": 0.7}))
_a(AttachmentDef("bipod", "underbarrel", "两脚架", "趴下/蹲下时后坐 -55%", {RIFLE, SNIPER},
                 adds={"bipod": 1}, mods={"ads_time": 1.05}))

# ─── 弹匣 ───
_a(AttachmentDef("mag_std", "magazine", "标准弹匣", "标准容量", ALL))
_a(AttachmentDef("mag_ext", "magazine", "扩容弹匣", "容量 +50%, 换弹更慢", ALL - {SHOTGUN} | {SHOTGUN},
                 mods={"mag_size": 1.5, "reload_time": 1.15, "reload_empty_time": 1.15, "ads_time": 1.06}))
_a(AttachmentDef("mag_fast", "magazine", "快拔弹匣", "换弹速度 +25%", ALL,
                 mods={"reload_time": 0.75, "reload_empty_time": 0.75, "shell_time": 0.8}))
_a(AttachmentDef("mag_drum", "magazine", "弹鼓", "容量 x2, 移动速度降低", {RIFLE},
                 mods={"mag_size": 2.0, "reload_time": 1.35, "reload_empty_time": 1.35,
                       "move_mult": 0.94, "ads_time": 1.12}))
_a(AttachmentDef("mag_ap", "magazine", "穿甲弹", "远距离伤害 +20%, 容量 -20%", {RIFLE, SNIPER, PISTOL},
                 mods={"damage_far": 1.2, "mag_size": 0.8}))


def compatible(weapon: WeaponDef, att: AttachmentDef) -> bool:
    if weapon.category not in att.categories:
        return False
    if att.only and weapon.id not in att.only:
        return False
    if weapon.id in att.exclude:
        return False
    return True


def options_for(weapon: WeaponDef, slot: str):
    return [a for a in ATTACHMENTS.values() if a.slot == slot and compatible(weapon, a)]


DEFAULT_BY_SLOT = {"optic": "iron", "muzzle": "muzzle_std", "underbarrel": "ub_none", "magazine": "mag_std"}


def default_attachments(weapon: WeaponDef) -> Dict[str, str]:
    atts = dict(DEFAULT_BY_SLOT)
    atts.update(weapon.default_atts)
    return sanitize(weapon, atts)


def sanitize(weapon: WeaponDef, atts: Dict[str, str]) -> Dict[str, str]:
    """保证配件合法 (服务器端用来校验客户端请求)"""
    out = {}
    for slot in SLOTS:
        aid = atts.get(slot, DEFAULT_BY_SLOT[slot])
        a = ATTACHMENTS.get(aid)
        if a is None or a.slot != slot or not compatible(weapon, a):
            aid = DEFAULT_BY_SLOT[slot]
        out[slot] = aid
    return out


@dataclass
class FinalStats:
    """最终属性 = 武器基础属性 × 配件修正"""
    base: WeaponDef
    damage_near: float
    damage_far: float
    range_near: float
    range_far: float
    pellets: int
    mag_size: int
    reload_time: float
    reload_empty_time: float
    shell_time: float
    spread_hip: float
    spread_ads: float
    recoil_v: float
    recoil_h: float
    ads_time: float
    move_mult: float
    zoom: float
    scope_overlay: bool
    reticle: str
    suppressed: bool
    flash_hidden: bool
    bipod: bool


def compute_stats(weapon: WeaponDef, atts: Dict[str, str]) -> FinalStats:
    m = {}
    adds = {}
    optic = ATTACHMENTS[atts.get("optic", "iron")]
    suppressed = flash_hidden = False
    for slot in SLOTS:
        a = ATTACHMENTS.get(atts.get(slot, DEFAULT_BY_SLOT[slot]))
        if not a:
            continue
        for k, v in a.mods.items():
            m[k] = m.get(k, 1.0) * v
        for k, v in a.adds.items():
            adds[k] = adds.get(k, 0) + v
        suppressed |= a.suppressed
        flash_hidden |= a.flash_hidden

    def g(k):
        return getattr(weapon, k) * m.get(k, 1.0)

    pellets = weapon.pellets
    dn, df = g("damage_near"), g("damage_far")
    if adds.get("pellets_set"):
        pellets = 1
        dn *= adds.get("damage_mult_slug", 1.0)
        df *= adds.get("damage_mult_slug", 1.0)
    mag = max(1, int(round(weapon.mag_size * m.get("mag_size", 1.0))))
    return FinalStats(
        base=weapon, damage_near=dn, damage_far=df,
        range_near=g("range_near"), range_far=g("range_far"), pellets=pellets,
        mag_size=mag, reload_time=g("reload_time"), reload_empty_time=g("reload_empty_time"),
        shell_time=g("shell_time"), spread_hip=g("spread_hip"), spread_ads=g("spread_ads"),
        recoil_v=g("recoil_v"), recoil_h=g("recoil_h"), ads_time=g("ads_time"),
        move_mult=g("move_mult"), zoom=optic.zoom, scope_overlay=optic.scope_overlay,
        reticle=optic.reticle, suppressed=suppressed, flash_hidden=flash_hidden,
        bipod=bool(adds.get("bipod")),
    )
