"""
NetworkSession —— 连接专用服务器的客户端会话。

  * 客户端预测: 本地玩家用 simulate_player 立即响应输入 (无延迟手感)
  * 服务器校正: 收到快照后, 采用服务器状态, 并重放尚未被确认的命令
  * 本地开火特效即时生成 (预测), 服务器发来的自己的 shot 事件被忽略
  * 远程玩家直接采用快照 (渲染层对其做平滑插值)
"""
import time
from core import settings as S
from core.commands import InputCommand
from world.world import World
from player.controller import simulate_player
from net import protocol as P
from net.transport import UdpTransport
from net.session import GameSession

INPUT_REDUNDANCY = 3


class NetworkSession(GameSession):
    is_network = True

    def __init__(self, host, port=S.DEFAULT_PORT, name="Player", transport=None, server_addr=None):
        self.transport = transport or UdpTransport("0.0.0.0", 0)
        self.addr = server_addr or (host, port)
        self.world = World()
        self.world.players.clear()
        self.local_pid = -1
        self.name = name
        self.pending = []           # 未被服务器确认的命令
        self.sent_recent = []
        self._events = []
        self._seen_event_ids = set()
        self.connected = False
        self.rtt = 0.0
        self._last_hello = 0.0
        self._last_ping = 0.0
        self.last_snapshot_time = 0.0
        self._send(P.hello(name, S.GAME_VERSION))

    def _send(self, msg):
        self.transport.send(P.encode(msg), self.addr)

    def _receive(self):
        for data, _addr in self.transport.poll():
            try:
                msg = P.decode(data)
            except Exception:
                continue
            t = msg.get("t")
            if t == "welcome":
                self.local_pid = msg["pid"]
                self.connected = True
            elif t == "snap":
                self._on_snapshot(msg)
            elif t == "pong":
                self.rtt = time.time() - msg.get("t0", time.time())

    def _on_snapshot(self, msg):
        self.last_snapshot_time = time.time()
        self.world.apply_snapshot(msg["s"])
        ack = msg.get("ack", -1)
        # ── 服务器校正 + 重放 ──
        self.pending = [c for c in self.pending if c.seq > ack]
        me = self.world.players.get(self.local_pid)
        if me is not None:
            for c in self.pending:
                simulate_player(me, c, self.world.col)
        for e in msg.get("ev", []):
            eid = e.get("id")
            if eid in self._seen_event_ids:
                continue
            self._seen_event_ids.add(eid)
            if e["e"] == "shot" and e["pid"] == self.local_pid:
                continue        # 自己的开火已在本地预测
            self._events.append(e)
        if len(self._seen_event_ids) > 4000:
            self._seen_event_ids = set(sorted(self._seen_event_ids)[-1000:])

    def tick(self, cmd: InputCommand):
        self._receive()
        now = time.time()
        if not self.connected:
            if now - self._last_hello > 1.0:
                self._last_hello = now
                self._send(P.hello(self.name, S.GAME_VERSION))
            return
        if now - self._last_ping > 2.0:
            self._last_ping = now
            self._send({"t": "ping", "t0": now})
        self.pending.append(cmd)
        self.sent_recent = (self.sent_recent + [cmd])[-INPUT_REDUNDANCY:]
        self._send(P.input_msg(self.sent_recent))
        # 本地预测
        me = self.world.players.get(self.local_pid)
        if me is not None:
            shots = simulate_player(me, cmd, self.world.col)
            for s in shots:
                # 仅生成视觉事件 (命中由服务器判定)
                ends = []
                for d in s.dirs:
                    hit = self.world.col.raycast(s.origin, d, 300.0)
                    t = hit[0] if hit else 300.0
                    ends.append([s.origin[i] + d[i] * t for i in range(3)])
                w = me.weapon
                self._events.append(dict(e="shot", pid=me.pid, w=s.weapon, o=list(s.origin), ends=ends,
                                         n=[None] * len(ends), h=[-2] * len(ends),
                                         sup=w.stats.suppressed, fh=w.stats.flash_hidden, sc=s.counter))

    def deploy(self, loadout):
        self._send(P.deploy(loadout))
        return True

    def set_attachments(self, slot_index, atts):
        self._send(P.atts(slot_index, atts))
        me = self.world.players.get(self.local_pid)
        if me and slot_index < len(me.weapons):
            me.weapons[slot_index].set_attachments(atts)
        return True

    def poll_events(self):
        ev, self._events = self._events, []
        return ev

    def status_text(self):
        if not self.connected:
            return "正在连接 %s:%d ..." % self.addr
        return "在线 · RTT %d ms · 玩家 %d" % (self.rtt * 1000, len(self.world.players))

    def close(self):
        try:
            self._send({"t": "bye"})
        finally:
            self.transport.close()
