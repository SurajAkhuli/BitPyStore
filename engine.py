import os
import time
import json
import zlib
from lru_cache import LRUCache


class KVStore:
    def __init__(self, filename="data.log"):
        self.filename = filename
        
        # Open file in append mode → all writes go to end of file (append-only log)
        # buffering=1 → line-buffered writes → flushes on every newline, safer for durability
        self.write_file = open(self.filename, "a+", buffering=1)
        self.read_file = open(self.filename, "r", buffering=1)

        # In-memory index: key -> (header_offset, json_offset, expiry)
        # This is the same idea as Bitcask: index stays in RAM, values stay on disk.
        self.index = {}
        self._load_index()  # Build index from existing log at startup (crash recovery)

        self.cache = LRUCache(capacity=1000)  # LRU cache for faster GETs
        self.put_count = 0
        self.delete_count = 0
        self.last_compaction_time = None


    # ----------------------------------------------------------------
    # INDEX LOADING — Replay the log file at startup to rebuild index
    # ----------------------------------------------------------------
    def _load_index(self):
        """Scan the entire log file and rebuild the in-memory index.
           This acts as crash recovery because we replay the log."""
        self.index = {}
        self.read_file.seek(0)

        while True:
            header_offset = self.read_file.tell()  # Start position of header
            
            header = self.read_file.readline()
            if not header:
                break  # End of file reached

            # Header format: "<length> <checksum>"
            parts = header.strip().split()
            if len(parts) != 2:
                break  # Corrupted or unexpected entry

            try:
                length = int(parts[0])
                checksum = int(parts[1])
            except:
                break  # Corrupted header → stop loading further

            json_offset = self.read_file.tell()  # JSON begins right after header
            json_data = self.read_file.read(length)

            if len(json_data) != length:
                break  # Truncated JSON (unexpected EOF)

            # Verify checksum for corruption detection
            if zlib.crc32(json_data.encode()) != checksum:
                break

            # Skip newline after JSON
            self.read_file.readline()

            try:
                record = json.loads(json_data)
            except:
                break  # Corrupted JSON

            op = record["op"]
            key = record["key"]

            if op == "put":
                expiry = record.get("expiry", 0)
                # Index keeps offsets to header & json lines
                self.index[key] = (header_offset, json_offset, expiry)

            elif op == "delete":
                # Delete markers remove keys from index (Bitcask tombstones)
                self.index.pop(key, None)



    # ----------------------------------------------------------------
    # COMPACTION — rewrite only the latest versions of keys
    # ----------------------------------------------------------------
    def compact(self):
        """Rewrite the log file keeping only live (latest) records.
           Avoids log file growing forever. Works on Windows CRLF safely."""
        
        temp_filename = self.filename + ".compact"
        temp_file = open(temp_filename, "w", buffering=1)

        for key, (header_offset, json_offset, expiry) in self.index.items():
            
            # Skip expired keys
            if expiry != 0 and time.time() > expiry:
                continue

            # Seek to the original header
            self.read_file.seek(header_offset)
            header = self.read_file.readline()  # Not used except to skip

            # Read the JSON line fully (CRLF safe); do NOT use read(length)!
            json_line = self.read_file.readline().rstrip("\r\n")

            # Recompute fresh length & checksum for compacted file
            length = len(json_line)
            checksum = zlib.crc32(json_line.encode())

            # Write clean, compacted entry
            temp_file.write(f"{length} {checksum}\n")
            temp_file.write(json_line + "\n")

        temp_file.close()
        self.read_file.close()
        self.write_file.close()

        # Atomically replace old file (safe even if crash happens)
        os.replace(temp_filename, self.filename)

        # Reopen fresh log and reload index from the compacted file
        self.write_file = open(self.filename, "a+", buffering=1)
        self.read_file = open(self.filename, "r", buffering=1)
        self._load_index()

        self.last_compaction_time = time.time()



    # ----------------------------------------------------------------
    # PUT — append new value to log
    # ----------------------------------------------------------------
    def put(self, key, value, ttl=None):
        # TTL stored as absolute expiry timestamp
        expiry = int(time.time()) + ttl if ttl else 0
        value = str(value)

        # Record is stored as JSON in the log
        record = {"op": "put", "key": key, "value": value, "expiry": expiry}

        json_data = json.dumps(record)
        length = len(json_data)
        checksum = zlib.crc32(json_data.encode())

        # Current write pointer = header position
        header_offset = self.write_file.tell()

        # HEADER WRITE
        self.write_file.write(f"{length} {checksum}\n")

        # JSON WRITE
        self.write_file.write(json_data + "\n")
        self.write_file.flush()  # Ensure durability

        # JSON offset = header_offset + header length
        json_offset = header_offset + len(f"{length} {checksum}\n")

        # Update in-memory index
        self.index[key] = (header_offset, json_offset, expiry)

        self.cache.put(key, value)
        self.put_count += 1



    # ----------------------------------------------------------------
    # DELETE — append a tombstone entry
    # ----------------------------------------------------------------
    def delete(self, key):
        # Tombstone record (Bitcask-style delete)
        record = {"op": "delete", "key": key}

        json_data = json.dumps(record)
        length = len(json_data)
        checksum = zlib.crc32(json_data.encode())

        header_offset = self.write_file.tell()

        self.write_file.write(f"{length} {checksum}\n")
        self.write_file.write(json_data + "\n")
        self.write_file.flush()

        # Remove from index & cache
        self.index.pop(key, None)
        self.cache.delete(key)

        self.delete_count += 1



    # ----------------------------------------------------------------
    # GET — read latest value from disk (or cache)
    # ----------------------------------------------------------------
    def get(self, key):
        if key not in self.index:
            return None

        header_offset, json_offset, expiry = self.index[key]

        # TTL check
        if expiry != 0 and time.time() > expiry:
            self.index.pop(key, None)
            self.cache.delete(key)
            return None

        # Cache hit → fastest path
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        # Seek directly to the JSON offset (Bitcask principle)
        self.read_file.seek(json_offset)

        # Read JSON body using stored length from header
        json_data = self.read_file.read(self._read_json_length(header_offset))

        record = json.loads(json_data)
        value = record["value"]

        # Store in cache
        self.cache.put(key, value)
        return value


    def _read_json_length(self, header_offset):
        """Helper: read header to get JSON length."""
        self.read_file.seek(header_offset)
        header = self.read_file.readline().strip()
        length, _ = map(int, header.split())
        return length



    # ----------------------------------------------------------------
    # CLEANUP
    # ----------------------------------------------------------------
    def close(self):
        """Safely close file handles."""
        if not self.write_file.closed:
            self.write_file.close()
        if not self.read_file.closed:
            self.read_file.close()

    def __del__(self):
        self.close()
