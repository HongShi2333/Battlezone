"""
传输层抽象。上层只依赖 Transport 接口:
    send(data: bytes, addr)      poll() -> [(data, addr), ...]

  * LoopbackTransport —— 进程内 (测试 / 单机走完整网络路径)
  * UdpTransport      —— 非阻塞 UDP
后续可扩展: ENet / WebSocket / Steam Networking 等, 只需实现相同接口。
"""
import socket
from collections import deque


class Transport:
    def send(self, data: bytes, addr):
        raise NotImplementedError

    def poll(self):
        raise NotImplementedError

    def close(self):
        pass


class LoopbackTransport(Transport):
    """成对使用: a, b = LoopbackTransport.pair()"""

    def __init__(self, name):
        self.name = name
        self.inbox = deque()
        self.peer = None

    @staticmethod
    def pair():
        a, b = LoopbackTransport("A"), LoopbackTransport("B")
        a.peer, b.peer = b, a
        return a, b

    def send(self, data, addr=None):
        self.peer.inbox.append((data, self.name))

    def poll(self):
        out = list(self.inbox)
        self.inbox.clear()
        return out


class UdpTransport(Transport):
    MAX_PACKET = 65507

    def __init__(self, bind_host="0.0.0.0", bind_port=0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((bind_host, bind_port))
        self.sock.setblocking(False)

    @property
    def port(self):
        return self.sock.getsockname()[1]

    def send(self, data, addr):
        try:
            self.sock.sendto(data, addr)
        except (BlockingIOError, OSError):
            pass

    def poll(self):
        out = []
        while True:
            try:
                data, addr = self.sock.recvfrom(self.MAX_PACKET)
                out.append((data, addr))
            except (BlockingIOError, ConnectionResetError):
                break
            except OSError:
                break
        return out

    def close(self):
        self.sock.close()
