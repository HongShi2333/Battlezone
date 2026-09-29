"""预下载 TACZ / SuperbWarfare 枪械几何与贴图到本地缓存 (不写入 git)。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from render.gun_packs import WEAPON_MODELS, prefetch_all, CACHE_DIR, pack_label


def main():
    print("缓存目录:", CACHE_DIR)
    prefetch_all()
    missing = []
    from render.gun_packs import ensure_file
    for wid, (pack, geo, tex) in WEAPON_MODELS.items():
        g = ensure_file(pack, "geo", geo)
        t = ensure_file(pack, "tex", tex)
        flag = "ok" if g and t else "MISSING"
        if not (g and t):
            missing.append(wid)
        print("  %-8s %-18s %s" % (flag, wid, pack_label(wid)))
    if missing:
        print("未能获取:", ", ".join(missing))
        return 1
    print("全部 %d 把武器的模型已缓存。" % len(WEAPON_MODELS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
