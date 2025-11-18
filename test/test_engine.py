from engine import KVStore
db = KVStore("data/bitpystore.db")

# # Test Step 1

# db.put("name", "suraj")
# db.put("age", "21")
# db.delete("age")

# # Test Step 2

# db.put("name", "suraj")
# db.put("age", "21")
# db.put("name", "suraj2")
# db.delete("age")
# print(db.index)

# # Test Step 3

# db.put("name", "suraj")
# db.put("age", "21")
# db.put("name", "suraj2")
# print(db.get("name"))   # should print suraj2
# print(db.get("age"))    # 21
# db.delete("age")
# print(db.get("age"))    # None

#  # Test Step 4.1              # (run only ONCE)

# db.put("name", "suraj")
# db.put("age", "21")
# db.put("city", "ahmedabad")

# # Test Step 4.2              # (run many times)

# print("name:", db.get("name"))
# print("age:", db.get("age"))
# print("city:", db.get("city"))
# print(db.index)



# # Test Step 5-> Testing Compaction
# db.put("name", "suraj")
# db.put("name", "suraj2")
# db.put("name", "suraj3")

# db.delete("age")
# db.put("city", "mumbai")

# print("Index before compaction:", db.index)

# db.compact()

# print("Index after compaction:", db.index)
# print("GET name:", db.get("name"))
# print("GET city:", db.get("city"))



# # Test 1: Close Manually
# db.put("name", "suraj")
# db.close()

# # Test 2: Automatic Close Via del  -> No errors.
# db.put("x", "123")

# del db




# # Test 3: Context Manager   -> DB should auto-close.
# with KVStore("data.log") as dba:
#     dba.put("city", "ahmedabad")
#     print(dba.get("city"))


# after level 2 till stats completed

# db.put("a", "1")
# db.put("b", "2")
# db.delete("b")

# print(db.stats())
# db.compact()
# print(db.stats())
print(db.stats())
print(db.print_cache)