from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity=1000):
        self.capacity = capacity
        self.cache = OrderedDict()

    def get(self, key):
        if key not in self.cache:
            return None
        # Move to end: most recently used
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        # If exists, update & move to end
        if key in self.cache:
            self.cache.move_to_end(key)
            self.cache[key] = value
            return
        
        # Add new key
        self.cache[key] = value
        
        # If over capacity, remove least-recently-used
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def delete(self, key):
        if key in self.cache:
            del self.cache[key]
