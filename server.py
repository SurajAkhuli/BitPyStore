import socket
import os

from kvstore import KVStore
db = KVStore("data.log")

HOST = "127.0.0.1"
PORT = 5000
shutdown_flag = False

def start_server():
    global shutdown_flag
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(5)
    server.settimeout(1)  # allow checking for ctrl+c
    print(f"Server running on {HOST}:{PORT}")

    while not shutdown_flag:
        try:
            client_socket, addr = server.accept()
        except KeyboardInterrupt:
            print("\nServer stopped manually.")
            break
        except Exception as e:
            # This catches:
            # - TimeoutError
            # - socket.timeout
            # - ANY unexpected exception
            continue  # retry loop, DO NOT stop server

        print(f"Client connected: {addr}")
        handle_client(client_socket)

    # SHUTDOWN triggered
    print("Server shutting down...")
    db.close()           # close your KVStore
    server.close()       # close TCP socket


def handle_client(client_socket):
    try:
        client_socket.sendall(b"Welcome to KVStore Server\n")
    except:
        client_socket.close()
        return

    while True:
        try:
            data = client_socket.recv(1024)
        except ConnectionResetError:
            break

        if not data:
            break

        message = data.decode().strip()
        print("Client:", message)

        cmd, args = parse_command(message)

        # Handle parser errors
        if cmd == "ERROR":
            client_socket.sendall(("ERROR: " + args[0] + "\n").encode())
            continue

        # -----------------------
        #   COMMAND HANDLING
        # -----------------------

        # PUT key value
        if cmd == "PUT":
            key = args[0]
            value = " ".join(args[1:])  # allows spaces in value
            db.put(key, value)          # CALL YOUR KVSTORE
            client_socket.sendall(b"OK\n")
            continue

        # GET key
        if cmd == "GET":
            key = args[0]
            result = db.get(key)
            if result is None:
                client_socket.sendall(b"NOT_FOUND\n")
            else:
                client_socket.sendall(("VALUE " + str(result) + "\n").encode())
            continue

        # DEL key
        if cmd == "DEL":
            key = args[0]
            db.delete(key)
            client_socket.sendall(b"DELETED\n")
            continue
        
        # TTL key seconds
        if cmd == "TTL":
            key = args[0]
            seconds = int(args[1])

            # check if key exists
            val = db.get(key)
            if val is None:
                client_socket.sendall(b"NOT_FOUND\n")
                continue
            
            db.put(key, val, ttl=seconds)   # re-put with new TTL
            client_socket.sendall(b"OK\n")
            continue
        
        # STATS command
        if cmd == "STATS":
            stats = {
                "keys_in_index": len(db.index),
                "keys_in_cache": len(db.cache.cache),  # assuming dict inside LRUCache
                "put_count": db.put_count,
                "delete_count": db.delete_count,
                "file_size_bytes": os.path.getsize(db.filename),
                "last_compaction_time": db.last_compaction_time
            }

            # Convert dict to string
            text = "\n".join([f"{k}: {v}" for k, v in stats.items()])
            client_socket.sendall((text + "\n").encode())
            continue
        
        # COMPACT
        if cmd == "COMPACT":
            try:
                db.compact()
                client_socket.sendall(b"OK\n")
            except Exception as e:
                client_socket.sendall(f"ERROR: {str(e)}\n".encode())
            continue
        
        global shutdown_flag

        if cmd == "SHUTDOWN":
            client_socket.sendall(b"OK\n")
            shutdown_flag = True     # tell server to stop
            break
        

        # EXIT
        if cmd == "EXIT":
            client_socket.sendall(b"OK\n")
            break

        # Unknown (should never reach here)
        client_socket.sendall(b"ERROR: Unknown command\n")

    client_socket.close()
    print("Client disconnected")


def parse_command(text):
    """
    Parse command string and return command + arguments.
    Example:
    'PUT name suraj' -> ('PUT', ['name', 'suraj'])
    """
    text = text.strip()
    if not text:
        return None, []

    parts = text.split()
    cmd = parts[0].upper()
    args = parts[1:]

    # Validate commands
    if cmd == "PUT":
        if len(args) < 2:
            return "ERROR", ["PUT requires: PUT key value"]
        return cmd, args

    if cmd == "GET":
        if len(args) != 1:
            return "ERROR", ["GET requires: GET key"]
        return cmd, args

    if cmd == "DEL":
        if len(args) != 1:
            return "ERROR", ["DEL requires: DEL key"]
        return cmd, args

    if cmd == "TTL":
        if len(args) != 2:
            return "ERROR", ["TTL requires: TTL key seconds"]
        return cmd, args

    if cmd == "STATS":
        return "STATS", []

    if cmd == "COMPACT":
        return "COMPACT", []

    if cmd == "SHUTDOWN":
        return "SHUTDOWN", []

    # If unknown
    return "ERROR", [f"Unknown command: {cmd}"]


if __name__ == "__main__":
    try:
        start_server()
    except KeyboardInterrupt:
        print("\nServer stopped manually.")
