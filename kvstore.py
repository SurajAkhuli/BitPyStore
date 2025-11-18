import os
import time 
import json
import zlib
from cache import LRUCache

class KVStore:
    def __init__(self, filename="data.log"):
        self.filename = filename
        # open file in append mode so new writes go to end
        self.write_file = open(self.filename, "a+", buffering=1)
        self.read_file = open(self.filename, "r", buffering=1)
        # Computer stores writes in memory first, then writes to file later. Writes go to file immediately when \n is written (Every line is flushed)
        # buffering=1 = write each line to file immediately.No buffering=1 = write later (not instant).
        
        self.put_count = 0
        self.delete_count = 0
        self.last_compaction_time = None
                
        self.index = {}   # in-memory index: key -> offset
        self._load_index()    # load index from existing log
        
        self.cache = LRUCache(capacity=1000)  # cache with capacity of 1000 items
        

    def _load_index(self):
        """Rebuild index by scanning the log file."""
        self.read_file.seek(0)  # move to beginning

        while True:
            header = self.read_file.readline()
            if not header:
                break  # end of file

            try:
                length, checksum = map(int, header.strip().split(" "))
            except:
                break  # corrupted header → stop
            
            offset = self.read_file.tell()    # start of JSON record
            
            json_data = self.read_file.read(length)
            if not json_data:
                break  # corrupted end

            # verify checksum
            if zlib.crc32(json_data.encode()) != checksum:
                break  # corrupted record

            record = json.loads(json_data)
            op = record["op"]
            if op == "put":
                key = record["key"]
                expiry = record["expiry"]
                self.index[key] = (offset, expiry)
    
            elif op == "delete":
                key = record["key"]
                self.index.pop(key, None)
                
            # skip newline after JSON
            self.read_file.readline()
                    
    def compact(self):
        """Compact the log file to remove old and deleted records."""

        # 1. Create temp file
        temp_filename = self.filename + ".compact"
        temp_file = open(temp_filename, "w", buffering=1)

        # 2. Write only the latest valid PUT records
        for key, (offset, expiry) in self.index.items():
            # skip expired keys
            if expiry != 0 and time.time() > expiry:
                continue
            # Read current value from original file
            self.read_file.seek(offset)
            json_data = self.read_file.readline().strip()

            length = len(json_data)
            checksum = zlib.crc32(json_data.encode())
    
            temp_file.write(f"{length} {checksum}\n")
            temp_file.write(json_data + "\n")
            

        temp_file.close()
        self.read_file.close()
        self.write_file.close()

        # 3. Replace old file with compacted file
        os.replace(temp_filename, self.filename) 
        # os.replace(src, dst) does: Delete dst (old file), Rename src to dst, Do it in ONE ATOMIC OPERATION, Guaranteed not to leave broken files

        # 4. Reopen file and rebuild index
        self.write_file = open(self.filename, "a+", buffering=1)
        self.read_file = open(self.filename, "r", buffering=1)
        self.index = {}
        # Why do we empty index? -> Before compaction: index contains offsets from OLD FILE. If we don’t clear index → DB will point to WRONG places → corrupted reads. So we MUST: 1)Clear index 2)Rebuild index from compacted file
        self._load_index()
        
        self.last_compaction_time = time.time()



    def close(self):
        """Safely close the database file."""
        if not self.write_file.closed:
            self.write_file.close()
        if not self.read_file.closed:
            self.read_file.close()

    def __del__(self):
        self.close()
        
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()



    def put(self, key, value, ttl=None):
        # calculate absolute expiry timestamp
        expiry = 0
        if ttl is not None:
            expiry = int(time.time()) + ttl
            
        record = {
            "op": "put",
            "key": key,
            "value": value,
            "expiry": expiry
        }
            
        json_data = json.dumps(record)
        length = len(json_data)
        checksum = zlib.crc32(json_data.encode())
        # get offset before writing
        offset = self.write_file.tell()

        # write record to file
        # header
        self.write_file.write(f"{length} {checksum}\n")
        # body
        self.write_file.write(json_data + "\n")
        self.write_file.flush()
        # Add Optional: flush after every write (durability). Databases normally call fsync or flush file buffer.
        
        # store offset of JSON (not header)
        header_len = len(f"{length} {checksum}\n")
        self.index[key] = (offset + header_len, expiry)
        
        self.put_count += 1
        self.cache.put(key, value)
        


    def delete(self, key):
        # write delete record
        record = {
            "op": "delete",
            "key": key
        }
        json_data = json.dumps(record)
        length = len(json_data)
        checksum = zlib.crc32(json_data.encode())
        offset = self.write_file.tell()
        
        self.write_file.write(f"{length} {checksum}\n")
        self.write_file.write(json_data + "\n")
        self.write_file.flush()

        self.delete_count += 1
        self.cache.delete(key)
        # remove from index
        self.index.pop(key, None)  
        # If key exists → deletes. If key doesn't exist → silently returns None

    def get(self, key):
        # if key not in index → no value
        if key not in self.index:
            return None

        # jump to record offset
        offset, expiry = self.index[key]
        
        # check expiry
        # 1. TTL Check
        if expiry != 0 and time.time() > expiry:
            # key expired
            del self.index[key]
            self.cache.delete(key)
            return None
        
        # 2. Cache Check first
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        
        self.read_file.seek(offset)
    
        # Actually, length is not needed here because we access JSON directly.
        # simpler:
        json_line = self.read_file.readline().strip()  # if strip is used to remove \n then why we dont put strip also in load_index also may be bcz there we use length find concept if yes then why we dont use that also here may be bcz we are coming here directly through offset value and not going back to get length
        
        # _load_index() → uses length-based reading, so NO strip.
        # get() → reads whole line, so strip is OK.
        # And YES — in get() we do NOT go back to read length, we rely on offset.
        
        record = json.loads(json_line)
    
        value = record["value"]
        self.cache.put(key, value)
    
        return value

    def stats(self):
        return {
            "file_size_bytes": os.path.getsize(self.filename),
            "keys_in_index": len(self.index),
            "keys_in_cache": len(self.cache.cache),
            "put_count": self.put_count,
            "delete_count": self.delete_count,
            "last_compaction_time": self.last_compaction_time,
        }

    def print_cache(self):
        print("LRU Cache contents:")
        for key, value in self.cache.cache.items():
            print(f"{key} -> {value}")
