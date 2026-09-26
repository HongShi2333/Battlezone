"""
InputCommand —— 客户端 → 模拟层 的唯一输入通道。

整个架构的核心：玩家(本地/远程/机器人)都只通过 InputCommand 驱动。
  * 单机：LocalSession 直接把命令交给 World
  * 多人：客户端把命令发送给服务器，同时本地用相同代码做预测(prediction)，
          收到服务器快照后回滚+重放(reconciliation)
  * 机器人：BotBrain 生成 InputCommand，与真人共用同一套移动/武器代码
"""
from dataclasses import dataclass


class Btn:
    FIRE        = 1 << 0
    ADS         = 1 << 1
    SPRINT      = 1 << 2
    JUMP        = 1 << 3
    CROUCH      = 1 << 4
    PRONE       = 1 << 5
    RELOAD      = 1 << 6
    PRIMARY     = 1 << 7
    SECONDARY   = 1 << 8
    SWAP        = 1 << 9     # 滚轮切换
    FIREMODE    = 1 << 10
    LEAN_L      = 1 << 11
    LEAN_R      = 1 << 12
    INSPECT     = 1 << 13


@dataclass
class InputCommand:
    seq: int = 0              # 递增序号 (用于服务器确认 / 客户端重放)
    dt: float = 1 / 60
    move_f: float = 0.0       # 前后 -1..1
    move_r: float = 0.0       # 左右 -1..1
    yaw: float = 0.0          # 绝对视角 (弧度)
    pitch: float = 0.0
    buttons: int = 0

    def held(self, b: int) -> bool:
        return (self.buttons & b) != 0

    # ── 序列化 (紧凑元组, 便于 JSON/msgpack) ──
    def pack(self):
        return [self.seq, round(self.dt, 5), round(self.move_f, 3), round(self.move_r, 3),
                round(self.yaw, 5), round(self.pitch, 5), self.buttons]

    @staticmethod
    def unpack(t):
        return InputCommand(int(t[0]), float(t[1]), float(t[2]), float(t[3]),
                            float(t[4]), float(t[5]), int(t[6]))
