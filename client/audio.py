"""
程序化音效 (numpy 合成, 无需外部音频文件) + 3D 定位 (距离衰减 + 立体声声像)
没有声卡时自动降级为静音。
"""
import math
import random
import numpy as np
import pygame

SR = 44100


def _env(n, attack=0.002, decay=0.15):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / decay)


def _lowpass(x, k):
    """简单一阶低通, k 越小越闷"""
    y = np.empty_like(x)
    acc = 0.0
    # 向量化近似: 用卷积核
    n = max(1, int(1 / max(k, 1e-3)))
    kernel = np.ones(n) / n
    return np.convolve(x, kernel, mode="same")


def _noise(n, seed=None):
    rng = np.random.default_rng(seed)
    return rng.uniform(-1, 1, n)


def _tone(n, f0, f1=None, phase=0.0):
    f1 = f0 if f1 is None else f1
    t = np.arange(n) / SR
    f = np.linspace(f0, f1, n)
    return np.sin(2 * np.pi * np.cumsum(f) / SR + phase)


def _gunshot(dur, crack, body_f, body_decay, tail, lp, seed):
    n = int(SR * dur)
    nz = _noise(n, seed)
    crack_part = nz * _env(n, 0.0005, crack)
    body = _tone(n, body_f * 1.6, body_f * 0.6) * _env(n, 0.001, body_decay)
    tail_part = _lowpass(_noise(n, seed + 1), lp) * _env(n, 0.01, tail) * 2.2
    s = crack_part * 0.9 + body * 0.8 + tail_part * 0.6
    return s


def _to_sound(x, vol=1.0):
    x = x / (np.max(np.abs(x)) + 1e-6) * vol
    a = (x * 32000).astype(np.int16)
    stereo = np.ascontiguousarray(np.stack([a, a], -1))
    return pygame.sndarray.make_sound(stereo)


class Audio:
    def __init__(self):
        self.enabled = False
        self.sounds = {}
        self.master = 0.8
        try:
            pygame.mixer.pre_init(SR, -16, 2, 512)
            pygame.mixer.init(SR, -16, 2, 512)
            pygame.mixer.set_num_channels(48)
            self.enabled = True
        except Exception as e:
            print("[audio] disabled:", e)
            return
        self._build()

    def _build(self):
        S = self.sounds
        profiles = {
            "rifle": (0.45, 0.02, 90, 0.05, 0.18, 0.12),
            "battle": (0.55, 0.025, 70, 0.07, 0.22, 0.1),
            "pistol": (0.35, 0.015, 120, 0.04, 0.12, 0.15),
            "magnum": (0.6, 0.03, 60, 0.08, 0.25, 0.08),
            "dmr": (0.7, 0.03, 65, 0.08, 0.3, 0.08),
            "sniper": (1.1, 0.035, 50, 0.1, 0.45, 0.06),
            "fifty": (1.3, 0.04, 40, 0.14, 0.55, 0.05),
            "shotgun": (0.7, 0.03, 55, 0.1, 0.28, 0.07),
        }
        for name, (dur, crack, bf, bd, tail, lp) in profiles.items():
            x = _gunshot(dur, crack, bf, bd, tail, lp, hash(name) & 0xFFFF)
            S["shot_" + name] = _to_sound(x, 0.95)
            far = _lowpass(x, 0.03) * 0.9
            S["far_" + name] = _to_sound(far, 0.6)
        # 消音
        n = int(SR * 0.22)
        x = _lowpass(_noise(n, 5), 0.2) * _env(n, 0.001, 0.035) + _tone(n, 300, 120) * _env(n, 0.001, 0.02) * 0.3
        S["shot_suppressed"] = _to_sound(x, 0.55)
        # 机械声
        def click(freq, dur=0.04, seed=0, vol=0.5):
            n = int(SR * dur)
            return _to_sound(_noise(n, seed) * _env(n, 0.0005, dur / 5) * 0.6 +
                             _tone(n, freq, freq * 0.8) * _env(n, 0.0005, dur / 4) * 0.5, vol)
        S["mag_out"] = click(900, 0.08, 1, 0.45)
        S["mag_in"] = click(1400, 0.07, 2, 0.55)
        S["bolt"] = click(1800, 0.06, 3, 0.5)
        S["bolt_back"] = click(700, 0.12, 4, 0.5)
        S["pump"] = click(500, 0.14, 5, 0.6)
        S["shell"] = click(1100, 0.06, 6, 0.45)
        S["dry"] = click(2500, 0.03, 7, 0.35)
        S["switch"] = click(600, 0.1, 8, 0.35)
        S["attach"] = click(1600, 0.09, 9, 0.4)
        S["firemode"] = click(2200, 0.04, 10, 0.35)
        # 移动
        for i in range(4):
            n = int(SR * 0.12)
            x = _lowpass(_noise(n, 20 + i), 0.08) * _env(n, 0.003, 0.03)
            S["step%d" % i] = _to_sound(x, 0.25)
        n = int(SR * 0.7)
        x = _lowpass(_noise(n, 30), 0.15) * np.linspace(1, 0, n) ** 1.5
        S["slide"] = _to_sound(x, 0.45)
        n = int(SR * 0.2)
        S["land"] = _to_sound(_lowpass(_noise(n, 31), 0.04) * _env(n, 0.002, 0.05) + _tone(n, 80, 40) * _env(n, 0.001, 0.06), 0.5)
        n = int(SR * 0.25)
        S["cloth"] = _to_sound(_lowpass(_noise(n, 32), 0.3) * _env(n, 0.04, 0.08), 0.2)
        # 反馈
        n = int(SR * 0.06)
        S["hit"] = _to_sound(_tone(n, 1900, 1700) * _env(n, 0.0005, 0.015), 0.35)
        n = int(SR * 0.25)
        S["headshot"] = _to_sound((_tone(n, 2600) + _tone(n, 3900) * 0.5) * _env(n, 0.0005, 0.06), 0.4)
        n = int(SR * 0.18)
        x = _tone(n, 1500) * _env(n, 0.0005, 0.03)
        x[int(SR * 0.07):] += _tone(n - int(SR * 0.07), 2100) * _env(n - int(SR * 0.07), 0.0005, 0.04)
        S["kill"] = _to_sound(x, 0.45)
        n = int(SR * 0.25)
        S["hurt"] = _to_sound(_tone(n, 110, 60) * _env(n, 0.002, 0.08) + _lowpass(_noise(n, 40), 0.05) * _env(n, 0.002, 0.05), 0.55)
        n = int(SR * 0.08)
        S["impact"] = _to_sound(_noise(n, 41) * _env(n, 0.0005, 0.012), 0.3)
        n = int(SR * 0.18)
        x = _noise(n, 42) * np.sin(np.linspace(0, np.pi, n)) ** 2
        S["whiz"] = _to_sound(_lowpass(x, 0.5), 0.3)
        n = int(SR * 0.5)
        S["deploy"] = _to_sound((_tone(n, 440, 880) * 0.5 + _tone(n, 660, 1320) * 0.3) * _env(n, 0.02, 0.2), 0.3)
        n = int(SR * 0.08)
        S["ui"] = _to_sound(_tone(n, 1200, 1400) * _env(n, 0.001, 0.02), 0.25)

    def play(self, name, vol=1.0, pan=0.0):
        if not self.enabled:
            return
        s = self.sounds.get(name)
        if s is None:
            return
        ch = pygame.mixer.find_channel(True)
        if ch is None:
            return
        v = max(0.0, min(1.0, vol * self.master))
        l = v * min(1.0, 1 - pan)
        r = v * min(1.0, 1 + pan)
        ch.set_volume(l, r)
        ch.play(s)

    def play_at(self, name, pos, listener, yaw, max_dist=120.0, vol=1.0, far_name=None):
        dx, dy, dz = pos[0] - listener[0], pos[1] - listener[1], pos[2] - listener[2]
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d > max_dist:
            return
        att = 1.0 / (1.0 + d * 0.08)
        rx, rz = math.cos(yaw), math.sin(yaw)
        pan = (dx * rx + dz * rz) / max(d, 1.0)
        pan = max(-0.85, min(0.85, pan))
        if far_name and d > 30:
            self.play(far_name, vol * min(1.0, att * 2.2), pan)
        else:
            self.play(name, vol * att, pan)
