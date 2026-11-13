import hashlib
import bisect

class ConsistentHash:
    def __init__(self, nodes=None, replicas=100):
        self.replicas = replicas
        self.ring = {}
        self.sorted_keys = []

        if nodes:
            for node in nodes:
                self.add_node(node)

    def hash_value(self, value):
        result = hashlib.sha256(
            str(value).encode("utf-8")
        ).hexdigest()

        return int(result, 16)

    def add_node(self, node):
        if node in self.get_nodes():
            return

        for i in range(self.replicas):
            position = self.hash_value(f"{node}:{i}")
            self.ring[position] = node

        self.sorted_keys = sorted(self.ring.keys())

    def remove_node(self, node):
        for i in range(self.replicas):
            position = self.hash_value(f"{node}:{i}")
            self.ring.pop(position, None)

        self.sorted_keys = sorted(self.ring.keys())

    def get_node(self, key):
        if not self.sorted_keys:
            return None

        position = self.hash_value(key)

        index = bisect.bisect(
            self.sorted_keys,
            position
        )

        if index == len(self.sorted_keys):
            index = 0

        return self.ring[self.sorted_keys[index]]

    def get_nodes(self):
        return sorted(set(self.ring.values()))
