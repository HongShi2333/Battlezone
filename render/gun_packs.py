"""
从 TACZ 与 SuperbWarfare 加载枪械几何。

两个仓库的美术资源都不能再分发进本仓库:

* TACZ 模型 / 贴图: CC BY-NC-ND 4.0 (署名-非商业-禁止演绎)
* SuperbWarfare 模型 / 贴图: 制作组保留所有权利

因此这里只保存「哪把游戏武器对应哪个上游文件」的索引, 并在本地缓存中按需下载
(或读取玩家已经克隆的仓库)。缓存目录 ``assets/gunpacks/cache`` 被 gitignore。
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request
from typing import Dict, Optional, Tuple

from .bedrock_geo import bake_gun, BakedGun

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "assets", "gunpacks", "cache")

PACKS = {
    "tacz": {
        "label": "TACZ",
        "repo": "MCModderAnchor/TACZ",
        "ref": "1.20.1",
        "geo": "src/main/resources/assets/tacz/custom/tacz_default_gun/assets/tacz/geo_models/gun/{name}_geo.json",
        "tex": "src/main/resources/assets/tacz/custom/tacz_default_gun/assets/tacz/textures/gun/uv/{name}.png",
        "env": "BATTLEZONE_TACZ",
        "credit": "MCModderAnchor/TACZ",
        "license": "Assets CC BY-NC-ND 4.0",
    },
    "superbwarfare": {
        "label": "SuperbWarfare",
        "repo": "Mercurows/SuperbWarfare",
        "ref": "superbwarfare",
        "geo": "src/main/resources/assets/superbwarfare/models/bedrock/gun/{name}.geo.json",
        "tex": "src/main/resources/assets/superbwarfare/textures/bedrock/gun/{name}.png",
        "env": "BATTLEZONE_SW",
        "credit": "Mercurows/SuperbWarfare",
        "license": "Assets all rights reserved",
    },
}

# 游戏武器 id → (包, 几何名, 贴图名)。两边仓库都用到, 尽量对上现实原型。
WEAPON_MODELS: Dict[str, Tuple[str, str, str]] = {
    # ── TACZ ──
    "p320": ("tacz", "p320", "p320"),
    "deagle": ("tacz", "deagle", "deagle"),
    "m4a1": ("tacz", "m4a1", "m4a1"),
    "qbz951": ("tacz", "qbz_95", "qbz_95"),
    "scarh": ("tacz", "scar_h", "scar_h"),
    "m82": ("tacz", "m107", "m107"),          # 巴雷特 .50, TACZ 对应 M107
    "spas12": ("tacz", "spas_12", "spas_12"),
    "saiga12": ("tacz", "aa12", "aa12"),      # 弹匣供弹霰弹, 包内最接近的是 AA-12
    # ── SuperbWarfare ──
    "g17": ("superbwarfare", "glock_17", "glock_17"),
    "g18c": ("superbwarfare", "glock_18", "glock_17"),  # 官方枪数据共用 glock_17 贴图
    "qbz191": ("superbwarfare", "qbz_191", "qbz_191"),
    "ak12": ("superbwarfare", "ak_12", "ak_12"),
    "awm": ("superbwarfare", "awm", "awm"),
    "qbu88": ("superbwarfare", "mk_14", "mk_14"),  # 包内没有 QBU-88, 用 Mk14 精确射手步枪
    "svd": ("superbwarfare", "svd", "svd"),
    "m870": ("superbwarfare", "m_870", "m_870"),
    "qbs09": ("superbwarfare", "m_1897", "m_1897"),  # 泵动霰弹, 包内对应温彻斯特 M1897
}

_lock = threading.Lock()
_file_locks: Dict[str, threading.Lock] = {}
_prefetch_started = False
_warned = set()


def _file_lock(path):
    with _lock:
        lk = _file_locks.get(path)
        if lk is None:
            lk = threading.Lock()
            _file_locks[path] = lk
        return lk


def _warn(key, msg):
    if key in _warned:
        return
    _warned.add(key)
    print(msg)


def mapping_for(wid) -> Optional[Tuple[str, str, str]]:
    return WEAPON_MODELS.get(wid)


def pack_label(wid) -> Optional[str]:
    m = WEAPON_MODELS.get(wid)
    if not m:
        return None
    pack, geo, _tex = m
    return "%s · %s" % (PACKS[pack]["label"], geo)


def _local_candidates(pack, kind, name):
    """kind: geo | tex。返回可能已经存在于磁盘上的路径。"""
    info = PACKS[pack]
    ext = ".geo.json" if kind == "geo" else ".png"
    names = []
    # 1) 显式枪包目录
    override = os.environ.get("BATTLEZONE_GUNPACKS")
    if override:
        names.append(os.path.join(override, pack, name + ext))
    # 2) 已克隆的上游仓库
    root = os.environ.get(info["env"])
    if root:
        rel = info[kind].format(name=name)
        names.append(os.path.join(root, *rel.split("/")))
    # 3) 运行时缓存
    names.append(os.path.join(CACHE_DIR, pack, name + ext))
    return names


def _download(pack, kind, name, dest):
    info = PACKS[pack]
    rel = info[kind].format(name=name)
    url = "https://api.github.com/repos/%s/contents/%s?ref=%s" % (info["repo"], rel, info["ref"])
    headers = {
        "User-Agent": "Battlezone-gunpack",
        "Accept": "application/vnd.github.raw",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    if data[:1] == b"{" and b"message" in data[:200]:
        raise RuntimeError(data[:200].decode("utf-8", "replace"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return dest


def ensure_file(pack, kind, name) -> Optional[str]:
    """返回本地文件路径。找不到且下载失败时返回 None。"""
    existing = [p for p in _local_candidates(pack, kind, name) if os.path.isfile(p) and os.path.getsize(p) > 32]
    if existing:
        return existing[0]
    dest = os.path.join(CACHE_DIR, pack, name + (".geo.json" if kind == "geo" else ".png"))
    lk = _file_lock(dest)
    with lk:
        if os.path.isfile(dest) and os.path.getsize(dest) > 32:
            return dest
        try:
            _download(pack, kind, name, dest)
            return dest
        except Exception as e:
            _warn("dl:%s:%s" % (pack, name),
                  "[gunpacks] 无法获取 %s %s (%s): %s" % (PACKS[pack]["label"], name, kind, e))
            return None


def load_baked(wid, atts, kind="rifle") -> Optional[BakedGun]:
    mapped = WEAPON_MODELS.get(wid)
    if not mapped:
        return None
    pack, geo, tex = mapped
    geo_path = ensure_file(pack, "geo", geo)
    if not geo_path:
        return None
    tex_path = ensure_file(pack, "tex", tex)
    rgba = _load_rgba(tex_path) if tex_path else None
    try:
        with open(geo_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _warn("json:%s" % geo_path, "[gunpacks] 几何解析失败 %s: %s" % (geo_path, e))
        try:
            os.remove(geo_path)
        except OSError:
            pass
        return None
    baked = bake_gun(data, atts, rgba, pack=pack, model_name=geo, kind=kind)
    baked.tex_path = tex_path  # type: ignore[attr-defined]
    if baked.quad_count < 8:
        _warn("empty:%s" % wid, "[gunpacks] %s 烘焙后没有可用面, 回退程序化模型" % wid)
        return None
    return baked


def _load_rgba(path):
    """返回 HxWx4, 行 0 为图像顶部 (与基岩版 UV 一致)。不依赖 OpenGL。"""
    try:
        import pygame
        if not pygame.get_init():
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            pygame.init()
        if pygame.display.get_surface() is None:
            try:
                pygame.display.set_mode((1, 1))
            except pygame.error:
                pass
        surf = pygame.image.load(path).convert_alpha()
    except Exception as e:
        _warn("tex:%s" % path, "[gunpacks] 贴图读取失败 %s: %s" % (path, e))
        return None
    w, h = surf.get_size()
    try:
        import numpy as np
        raw = pygame.image.tostring(surf, "RGBA", False)
        return np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 4).copy()
    except Exception:
        return None


def prefetch_all():
    """下载全部已映射的几何与贴图。失败的武器会在对局中回退到程序化模型。"""
    for wid, (pack, geo, tex) in WEAPON_MODELS.items():
        ensure_file(pack, "geo", geo)
        ensure_file(pack, "tex", tex)


def prefetch_async():
    global _prefetch_started
    with _lock:
        if _prefetch_started:
            return
        _prefetch_started = True
    threading.Thread(target=prefetch_all, name="gunpack-prefetch", daemon=True).start()
