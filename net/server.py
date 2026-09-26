"""
专用服务器 (Dedicated Server) —— 无渲染, 可在 Linux 云主机上运行。

    python -m net.server --port 27960 --bots 4          (在 fps_game 目录下)

流程 (每 tick):
  1. 收包: hello / input / deploy / atts / ping / bye
  2. 对每个客户端应用排队的 InputCommand (权威模拟, 与客户端预测同一份代码)
  3. 机器人生成命令并应用
  4. world.step()
  5. 以 SNAPSHOT_RATE 广播快照 + 最近事件 (事件带 id, 重复发送以抗丢包)

TODO (后续多人开发):
  * 延迟补偿 (lag compensation): 保存历史命中盒, 按客户端 RTT 回溯判定
  * 可靠消息通道 (ack/resend) 与加密握手
  * 快照增量压缩 (delta against acked baseline)
  * 大厅 / 匹配 / 多房间
"""
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import settings as S
from core.commands import InputCommand
from world.world import World
from world.bots import BotManager
from net import protocol as P
from net.transport import UdpTransport

CLIENT_TIMEOUT = 10.0
EVENT_REDUNDANCY = 0.6      # 事件在后续快照中重复发送的时长 (秒)
MAX_QUEUE = 8


class ClientConn:
    def __init__(self, addr, pid, name):
        self.addr = addr
        self.pid = pid
        self.name = name
        self.queue = []
        self.last_seq = -1
        self.last_cmd = None
        self.last_heard = time.time()


class GameServer:
    def __init__(self, port=S.DEFAULT_PORT, bots_per_team=3, transport=None, skill=0.5):
        self.transport = transport or UdpTransport("0.0.0.0", port)
        self.world = World()
        self.bots = BotManager(self.world, skill=skill)
        self.clients = {}           # addr -> ClientConn
        self.next_pid = 1
        self.event_log = []         # [(id, time, event)]
        self.event_id = 0
        pid = 1000
        for team in (S.TEAM_BLUE, S.TEAM_RED):
            for _ in range(bots_per_team):
                self.bots.add_bot(pid, team)
                pid += 1
        self._snap_accum = 0.0
        self.running = True

    # ── 收包 ──
    def _handle(self, data, addr):
        try:
            msg = P.decode(data)
        except Exception:
            return
        t = msg.get("t")
        c = self.clients.get(addr)
        if t == "hello":
            if c is None:
                pid = self.next_pid
                self.next_pid += 1
                counts = [0, 0]
                for q in self.world.players.values():
                    if not q.is_bot:
                        counts[q.team] += 1
                team = 0 if counts[0] <= counts[1] else 1
                c = ClientConn(addr, pid, str(msg.get("name", "Player"))[:16])
                self.clients[addr] = c
                self.world.add_player(pid, c.name, team)
                print(f"[server] {c.name} joined as pid={pid} team={team} from {addr}", flush=True)
            p = self.world.players[c.pid]
            self.transport.send(P.encode(P.welcome(c.pid, p.team, self.world.map.name, S.TICK_RATE)), addr)
            return
        if c is None:
            return
        c.last_heard = time.time()
        if t == "input":
            for packed in msg.get("cmds", []):
                cmd = InputCommand.unpack(packed)
                if cmd.seq > c.last_seq and all(q.seq != cmd.seq for q in c.queue):
                    c.queue.append(cmd)
            c.queue.sort(key=lambda q: q.seq)
            if len(c.queue) > MAX_QUEUE:
                c.queue = c.queue[-MAX_QUEUE:]
        elif t == "deploy":
            self.world.request_deploy(c.pid, msg.get("loadout"))
        elif t == "atts":
            self.world.set_attachments(c.pid, int(msg.get("slot", 0)), msg.get("atts", {}))
        elif t == "ping":
            self.transport.send(P.encode({"t": "pong", "t0": msg.get("t0")}), addr)
        elif t == "bye":
            self._drop(addr)

    def _drop(self, addr):
        c = self.clients.pop(addr, None)
        if c:
            self.world.remove_player(c.pid)
            print(f"[server] {c.name} left", flush=True)

    # ── 主循环 ──
    def tick(self, dt):
        for data, addr in self.transport.poll():
            self._handle(data, addr)
        now = time.time()
        for addr, c in list(self.clients.items()):
            if now - c.last_heard > CLIENT_TIMEOUT:
                self._drop(addr)
                continue
            # 每 tick 处理 1 条命令, 队列积压时追赶 (最多 3 条)
            n = 1 if len(c.queue) <= 2 else 3
            for _ in range(n):
                if c.queue:
                    cmd = c.queue.pop(0)
                    c.last_seq = cmd.seq
                    c.last_cmd = cmd
                    self.world.apply_command(c.pid, cmd)
        for pid, cmd in self.bots.update(dt).items():
            self.world.apply_command(pid, cmd)
        self.world.step(dt)
        ev = self.world.drain_events()
        self.bots.on_events(ev)
        for e in ev:
            self.event_id += 1
            e["id"] = self.event_id
            self.event_log.append((self.event_id, self.world.time, e))
        cutoff = self.world.time - EVENT_REDUNDANCY
        while self.event_log and self.event_log[0][1] < cutoff:
            self.event_log.pop(0)
        self._snap_accum += dt
        if self._snap_accum >= 1.0 / S.SNAPSHOT_RATE:
            self._snap_accum = 0.0
            events = [e for _, _, e in self.event_log]
            for addr, c in self.clients.items():
                snap = self.world.snapshot(full_for=c.pid)
                self.transport.send(P.encode(P.snap(snap, c.last_seq, events)), addr)

    def run(self):
        print(f"[server] {self.world.map.name} running @ {S.TICK_RATE}Hz, bots={len(self.bots.brains)}", flush=True)
        dt = S.TICK_DT
        nxt = time.perf_counter()
        while self.running:
            self.tick(dt)
            nxt += dt
            sleep = nxt - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
            else:
                nxt = time.perf_counter()


def main():
    ap = argparse.ArgumentParser(description="Dedicated server")
    ap.add_argument("--port", type=int, default=S.DEFAULT_PORT)
    ap.add_argument("--bots", type=int, default=3, help="每队机器人数量")
    ap.add_argument("--skill", type=float, default=0.5)
    a = ap.parse_args()
    srv = GameServer(a.port, a.bots, skill=a.skill)
    try:
        srv.run()
    except KeyboardInterrupt:
        print("\n[server] shutdown")


if __name__ == "__main__":
    main()
