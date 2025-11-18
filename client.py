import socket

s = socket.socket()
s.connect(("127.0.0.1", 5000))

# print welcome
welcome = s.recv(1024).decode()
print("Server:", welcome)

while True:
    msg = input("> ")
    s.sendall((msg + "\n").encode())

    response = s.recv(1024)

    # if server closed connection
    if not response:
        print("Server closed connection.")
        break

    text = response.decode()
    print("Server:", text)

    if msg.strip().upper() == "SHUTDOWN":
        break

s.close()
print("Client closed.")
