"""客户端本地偏好 (武器配置 / 配件 / 灵敏度等) — 保存为 JSON"""
import json
import os
from core import settings as S

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prefs.json")

DEFAULTS = {
    "primary": "m4a1", "secondary": "p320", "atts": {},
    "sens": 1.0, "fov": S.FOV_BASE, "friendly_bots": 4, "enemy_bots": 5, "difficulty": 1,
    "name": "Player", "server": "127.0.0.1:%d" % S.DEFAULT_PORT,
}


class Prefs:
    def __init__(self):
        self.data = dict(DEFAULTS)
        try:
            with open(PATH, "r", encoding="utf-8") as f:
                self.data.update(json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            with open(PATH, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
        except OSError:
            pass
