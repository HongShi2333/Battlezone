"""
网络协议 —— 消息定义与编解码。

当前实现: JSON + zlib (易调试)。可无缝替换为 msgpack / 自定义二进制,
只需修改 encode/decode 两个函数, 上层无需改动。

消息 (t 字段):
  C→S  hello   {name, ver}                     加入请求
  S→C  welcome {pid, team, map, tick}          分配玩家 ID
  C→S  input   {cmds:[InputCommand.pack()...]} 最近 N 条命令 (冗余抗丢包)
  C→S  deploy  {loadout}                        重生部署
  C→S  atts    {slot, atts}                     游戏内修改配件 (Z 菜单)
  S→C  snap    {s: world.snapshot(), ack, ev:[...]}  快照 + 最近事件 (事件带 id 去重)
  C↔S  ping / pong {t0}
  C→S  bye
"""
import json
import zlib

PROTOCOL_VERSION = 1
_COMPRESS_THRESHOLD = 512


def encode(msg: dict) -> bytes:
    raw = json.dumps(msg, separators=(",", ":")).encode("utf-8")
    if len(raw) > _COMPRESS_THRESHOLD:
        return b"Z" + zlib.compress(raw, 3)
    return b"J" + raw


def decode(data: bytes) -> dict:
    if not data:
        return {}
    tag, body = data[:1], data[1:]
    if tag == b"Z":
        body = zlib.decompress(body)
    return json.loads(body.decode("utf-8"))


def hello(name, ver):
    return {"t": "hello", "name": name, "ver": ver, "pv": PROTOCOL_VERSION}


def welcome(pid, team, map_name, tick_rate):
    return {"t": "welcome", "pid": pid, "team": team, "map": map_name, "tick": tick_rate}


def input_msg(cmds):
    return {"t": "input", "cmds": [c.pack() for c in cmds]}


def deploy(loadout):
    return {"t": "deploy", "loadout": loadout}


def atts(slot, attachments):
    return {"t": "atts", "slot": slot, "atts": attachments}


def snap(snapshot, ack, events):
    return {"t": "snap", "s": snapshot, "ack": ack, "ev": events}
