"""
GameSession —— 客户端与 "游戏世界" 之间的唯一接口。

客户端 (渲染/UI/输入) 只和 Session 打交道, 完全不关心世界在本地还是远端:
  * LocalSession   : 单机, 进程内权威 World + 机器人
  * NetworkSession : 连接专用服务器 (见 net_session.py), 本地预测 + 服务器校正

接口:
    session.local_pid              本地玩家 id
    session.world                  可读的世界状态 (渲染用)
    session.tick(cmd)              每个固定模拟步调用一次, 提交本地输入
    session.deploy(loadout)        重生部署
    session.set_attachments(i, a)  修改配件 (Z 菜单)
    session.poll_events()          取出本帧的游戏事件 (音效/特效/击杀提示)
    session.close()
"""
from core import settings as S
from world.world import World
from world.bots import BotManager


class GameSession:
    local_pid = 0
    world = None
    is_network = False

    def tick(self, cmd):
        raise NotImplementedError

    def deploy(self, loadout):
        raise NotImplementedError

    def set_attachments(self, slot_index, atts):
        raise NotImplementedError

    def poll_events(self):
        raise NotImplementedError

    def status_text(self):
        return ""

    def close(self):
        pass


class LocalSession(GameSession):
    """单机: 世界与机器人都在本进程中运行"""

    def __init__(self, player_name="You", friendly_bots=4, enemy_bots=5, skill=0.5):
        self.world = World()
        self.bots = BotManager(self.world, skill=skill)
        self.local_pid = 1
        self.world.add_player(self.local_pid, player_name, S.TEAM_BLUE)
        pid = 100
        for _ in range(friendly_bots):
            self.bots.add_bot(pid, S.TEAM_BLUE)
            pid += 1
        for _ in range(enemy_bots):
            self.bots.add_bot(pid, S.TEAM_RED)
            pid += 1
        self._events = []

    def tick(self, cmd):
        bot_cmds = self.bots.update(cmd.dt)
        self.world.apply_command(self.local_pid, cmd)
        for pid, c in bot_cmds.items():
            self.world.apply_command(pid, c)
        self.world.step(cmd.dt)
        ev = self.world.drain_events()
        self.bots.on_events(ev)
        self._events.extend(ev)

    def deploy(self, loadout):
        return self.world.request_deploy(self.local_pid, loadout)

    def set_attachments(self, slot_index, atts):
        return self.world.set_attachments(self.local_pid, slot_index, atts)

    def poll_events(self):
        ev, self._events = self._events, []
        return ev

    def status_text(self):
        return "单机模式 · 机器人 %d" % len(self.bots.brains)
