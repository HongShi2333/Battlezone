"""基岩版枪械几何烘焙 — 不依赖 OpenGL / 网络。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from render.bedrock_geo import bake_gun, parse_geometry
from render.gun_packs import WEAPON_MODELS
from weapons.definitions import WEAPONS


def _cube_model(origin, size, pivot=(0, 0, 0), rotation=None, parent=None, name="body",
                cube_rot=None, cube_pivot=None, extra_bones=None):
    cube = {"origin": list(origin), "size": list(size), "uv": {
        face: {"uv": [0, 0], "uv_size": [4, 4]}
        for face in ("north", "south", "east", "west", "up", "down")
    }}
    if cube_rot:
        cube["rotation"] = list(cube_rot)
        cube["pivot"] = list(cube_pivot or origin)
    bone = {"name": name, "pivot": list(pivot)}
    if parent:
        bone["parent"] = parent
    if rotation:
        bone["rotation"] = list(rotation)
    bone["cubes"] = [cube]
    bones = list(extra_bones or [])
    bones.append(bone)
    return {
        "format_version": "1.12.0",
        "minecraft:geometry": [{
            "description": {"identifier": "geometry.test", "texture_width": 16, "texture_height": 16},
            "bones": bones,
        }],
    }


def test_parse_and_scale_to_meters():
    data = _cube_model([0, 0, 0], [16, 16, 16])
    bones, tw, th = parse_geometry(data)
    assert len(bones) == 1 and tw == 16 and th == 16
    baked = bake_gun(data)
    assert baked.quad_count == 6
    # 16 像素 = 1 米, 盒子占据 [0,1]^3
    assert abs(baked.bounds_min[0]) < 1e-6
    assert abs(baked.bounds_max[0] - 1.0) < 1e-6
    assert abs(baked.bounds_max[1] - 1.0) < 1e-6
    assert abs(baked.bounds_max[2] - 1.0) < 1e-6


def test_parent_rotation_moves_child_around_pivot():
    # 父骨骼绕 Z 转 90°, 子立方体在父 pivot 正上方 16 像素
    parent = {"name": "root", "pivot": [0, 0, 0], "rotation": [0, 0, 90], "cubes": []}
    data = _cube_model([0, 16, 0], [0, 0, 0], pivot=(0, 16, 0), parent="root", name="child",
                       extra_bones=[parent])
    # 零尺寸会被丢掉, 改成一个点状小盒
    data["minecraft:geometry"][0]["bones"][1]["cubes"][0]["size"] = [0.01, 0.01, 0.01]
    baked = bake_gun(data)
    # 与 TACZ / SuperbWarfare 的 Java 加载器一致: 先把 Y 翻到朝下再转,
    # 所以朝上的点绕 Z +90° 后落在 +X, 而不是右手系的 -X。
    c = baked.center
    assert c[0] > 0.9
    assert abs(c[1]) < 0.15


def test_x_rotation_is_right_handed():
    parent = {"name": "root", "pivot": [0, 0, 0], "rotation": [90, 0, 0], "cubes": []}
    data = _cube_model([0, 16, 0], [0.01, 0.01, 0.01], pivot=(0, 16, 0), parent="root",
                       name="child", extra_bones=[parent])
    baked = bake_gun(data)
    c = baked.center
    # 同样因为 Y 先翻转, +Y 绕 +X 转 90° 后落在 -Z
    assert c[2] < -0.9
    assert abs(c[1]) < 0.15


def test_cube_rotation_stays_on_its_pivot():
    """立方体自带旋转必须绕自己的 pivot, 不能被甩离骨骼 (Glock 握把曾因此散开)。"""
    data = _cube_model([0, 0, 0], [4, 2, 2], pivot=(0, 0, 0))
    cube = data["minecraft:geometry"][0]["bones"][0]["cubes"][0]
    cube["rotation"] = [0, 0, 45]
    cube["pivot"] = [2, 1, 1]
    baked = bake_gun(data)
    # pivot (2, 1, 1) 像素 = (0.125, 0.0625, 0.0625) 米, 盒子中心就在这
    assert abs(baked.center[0] - 0.125) < 0.02
    assert abs(baked.center[1] - 0.0625) < 0.02
    assert abs(baked.center[2] - 0.0625) < 0.02


def test_mag_variants_and_hands_hidden():
    def bone(name, parent, cubes=1):
        return {
            "name": name, "parent": parent, "pivot": [0, 0, 0],
            "cubes": [{"origin": [0, 0, 0], "size": [1, 1, 1],
                       "uv": {"north": {"uv": [0, 0], "uv_size": [1, 1]}}}] if cubes else [],
        }
    bones = [
        bone("root", None, 0),
        bone("magazine", "root", 0),
        bone("mag_standard", "magazine"),
        bone("mag_extended_1", "magazine"),
        bone("mag_extended_3", "magazine"),
        bone("righthand_pos", "root"),
        bone("attachment_adapter", "root", 0),
        bone("oem_stock_tactical", "attachment_adapter", 0),
        bone("oem_stock_child", "oem_stock_tactical"),
        bone("slide", "root"),
        bone("sight_illuminated", "slide"),
        bone("muzzle_flash", "root", 0),
        bone("iron_view", "root", 0),
        bone("idle_view", "root", 0),
    ]
    # muzzle / views need pivots
    for b in bones:
        if b["name"] == "muzzle_flash":
            b["pivot"] = [0, 8, -32]
        if b["name"] == "iron_view":
            b["pivot"] = [0, 16, 8]
        if b["name"] == "idle_view":
            b["pivot"] = [4, 20, 10]
        if b["name"] == "righthand_pos":
            b["pivot"] = [2, 6, 1]
    data = {"format_version": "1.12.0", "minecraft:geometry": [{
        "description": {"texture_width": 16, "texture_height": 16},
        "bones": bones,
    }]}
    std = bake_gun(data, {"magazine": "mag_std", "optic": "iron", "muzzle": "muzzle_std", "underbarrel": "ub_none"}, kind="pistol")
    assert len(std.groups["mag"]) == 1          # 只有 mag_standard
    assert len(std.groups["slide"]) == 2        # slide + illuminated child
    assert any(q.emissive for q in std.groups["slide"])
    assert any(not q.emissive for q in std.groups["slide"])
    # 手部占位、转接件及其孙骨骼都不进任何组
    total = sum(len(v) for v in std.groups.values())
    assert total == 1 + 2  # mag_standard + slide + sight_illuminated
    assert abs(std.anchors["muzzle"][2] - (-32 / 16)) < 1e-6
    assert abs(std.anchors["iron"][1] - 1.0) < 1e-6
    assert "grip_r" in std.anchors

    ext = bake_gun(data, {"magazine": "mag_ext", "optic": "iron"})
    assert len(ext.groups["mag"]) == 1
    drum = bake_gun(data, {"magazine": "mag_drum", "optic": "iron"})
    assert len(drum.groups["mag"]) == 1


def test_every_weapon_maps_to_a_pack():
    packs = {spec[0] for spec in WEAPON_MODELS.values()}
    assert packs == {"tacz", "superbwarfare"}
    missing = [wid for wid in WEAPONS if wid not in WEAPON_MODELS]
    assert missing == []
    # 两个仓库都实际被用到, 而不是只挂了一个名字
    assert sum(1 for p, _, _ in WEAPON_MODELS.values() if p == "tacz") >= 4
    assert sum(1 for p, _, _ in WEAPON_MODELS.values() if p == "superbwarfare") >= 4


def test_negative_uv_size_does_not_drop_face():
    cube = {"origin": [0, 0, 0], "size": [4, 4, 4], "uv": {
        "down": {"uv": [4, 8], "uv_size": [4, -4]},
        "up": {"uv": [0, 0], "uv_size": [4, 4]},
    }}
    data = {"format_version": "1.12.0", "minecraft:geometry": [{
        "description": {"texture_width": 16, "texture_height": 16},
        "bones": [{"name": "root", "pivot": [0, 0, 0], "cubes": [cube]}],
    }]}
    baked = bake_gun(data)
    assert baked.quad_count == 2


def test_cached_packs_assemble():
    """缓存里的真实模型必须是一把枪, 而不是散开的零件。没有缓存时跳过。"""
    import os
    from render.gun_packs import CACHE_DIR, load_baked
    atts = {"optic": "iron", "muzzle": "muzzle_std", "underbarrel": "ub_none", "magazine": "mag_std"}
    seen = 0
    for wid, (pack, geo, _tex) in WEAPON_MODELS.items():
        path = os.path.join(CACHE_DIR, pack, geo + ".geo.json")
        if not os.path.isfile(path):
            continue
        kind = WEAPONS[wid].model.get("kind", "rifle")
        baked = load_baked(wid, atts, kind=kind)
        assert baked is not None and baked.quad_count > 200, wid
        assert baked.span[1] < 1.8, (wid, baked.span)  # 旋转错误时零件会在 Y 上炸开
        assert baked.span[2] < 6.0, (wid, baked.span)
        assert "iron" in baked.anchors and "muzzle" in baked.anchors, wid
        seen += 1
    if seen:
        assert seen == len(WEAPON_MODELS)


if __name__ == "__main__":
    test_parse_and_scale_to_meters()
    test_parent_rotation_moves_child_around_pivot()
    test_x_rotation_is_right_handed()
    test_cube_rotation_stays_on_its_pivot()
    test_mag_variants_and_hands_hidden()
    test_every_weapon_maps_to_a_pack()
    test_negative_uv_size_does_not_drop_face()
    test_cached_packs_assemble()
    print("ok")
