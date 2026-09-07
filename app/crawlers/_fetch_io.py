"""HTTP plaintext framing bounds, in addition to encoded/decoded entity bounds."""
from _fetch_policy import Rejected


class ProtocolBudget:
    def __init__(self, policy):
        self.per_response = policy['max_wire_bytes'] + 65536
        self.total = policy['max_total_wire_bytes'] + policy['max_requests'] * 65536
        self.used = 0


class ResponseSocket:
    """Only the makefile capability needed by http.client.HTTPResponse."""
    def __init__(self, sock, budget):
        self.sock, self.budget = sock, budget

    def makefile(self, *args, **kwargs):
        return LimitedReader(self.sock.makefile(*args, **kwargs), self.budget)


class LimitedReader:
    def __init__(self, stream, budget):
        self.stream, self.budget = stream, budget
        self.used = 0

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def _read(self, method, size):
        room = min(self.budget.per_response - self.used, self.budget.total - self.budget.used)
        amount = max(1, room + 1)
        if size is not None and size >= 0:
            amount = min(size, amount)
        data = method(amount)
        self.used += len(data)
        self.budget.used += len(data)
        if len(data) > room:
            raise Rejected('too_large')
        return data

    def read(self, size=-1):
        return self._read(self.stream.read, size)

    read1 = read

    def readline(self, size=-1):
        return self._read(self.stream.readline, size)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    readinto1 = readinto
