import socket
import struct
import threading
import http.server
import subprocess
import os

HOST = "0.0.0.0"
GAME_PORT = 3074
WEB_PORT = int(os.environ.get("PORT", 8000))

class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"CoD4 Reflex Wii Server is Running!")
    def log_message(self, format, *args):
        pass  # Keep logs clean

def start_health_server():
    server = http.server.HTTPServer((HOST, WEB_PORT), HealthCheckHandler)
    print(f"[*] Koyeb HTTP Health Check listening on port {WEB_PORT}")
    server.serve_forever()

def start_tcp_tunnel():
    print(f"[*] Starting public TCP tunnel for Wii on port {GAME_PORT}...")
    try:
        proc = subprocess.Popen(
            ["bore", "local", str(GAME_PORT), "--to", "bore.pub"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in proc.stdout:
            print(f"[TUNNEL] {line.strip()}")
    except Exception as e:
        print(f"[!] Tunnel note: {e}")

class BitBuffer:
    """Packs DemonWare bdBitBuffer data (with 5-bit type tags)"""
    def __init__(self):
        self.bits = []

    def write_bits(self, value, num_bits):
        for i in range(num_bits):
            self.bits.append((value >> i) & 1)

    def write_data_type(self, data_type):
        self.write_bits(data_type, 5)

    def write_uint32(self, val):
        self.write_data_type(8)  # Type 8 = uint32
        b = struct.pack(">I", val)
        for byte in b:
            self.write_bits(byte, 8)

    def write_uint64(self, val):
        self.write_data_type(10)  # Type 10 = uint64
        b = struct.pack(">Q", val)
        for byte in b:
            self.write_bits(byte, 8)

    def write_raw_bytes(self, data: bytes):
        for byte in data:
            self.write_bits(byte, 8)

    def to_bytes(self) -> bytes:
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            chunk = self.bits[i:i+8]
            byte = 0
            for bit_idx, bit in enumerate(chunk):
                byte |= (bit << bit_idx)
            out.append(byte)
        return bytes(out)

def build_user_ticket(online_id=12345678, username="ReflexPlayer") -> bytes:
    """Builds the 128-byte (0x80) User Ticket expected by FUN_8094c808"""
    ticket = bytearray(128)
    struct.pack_into("<I", ticket, 0x00, 0xDEADBEEF)
    ticket[0x04] = 0
    struct.pack_into("<I", ticket, 0x05, 5153)
    struct.pack_into("<I", ticket, 0x09, 1)
    struct.pack_into("<I", ticket, 0x0D, 1)
    struct.pack_into("<Q", ticket, 0x11, 1)
    struct.pack_into("<Q", ticket, 0x19, online_id)
    name_bytes = username.encode("ascii")[:63]
    ticket[0x21:0x21 + len(name_bytes)] = name_bytes
    ticket[0x61:0x61 + 24] = b"A" * 24
    return bytes(ticket)

def frame_unencrypted_packet(msg_type: int, payload: bytes) -> bytes:
    length = 2 + len(payload)
    return struct.pack("<IBB", length, 0x00, msg_type) + payload

def build_auth_reply() -> bytes:
    bb = BitBuffer()
    bb.write_uint32(700)        # 700 = BD_NO_ERROR (Login Success!)
    bb.write_uint32(0x12345678) # IV Seed
    bb.write_raw_bytes(b"\x00" * 128)         # 128-byte RSA Sig (bypassed via Gecko)
    bb.write_raw_bytes(build_user_ticket())   # 128-byte User Ticket (0xDEADBEEF)
    bb.write_raw_bytes(b"\x00" * 128)         # 128-byte Lobby Server Ticket
    return frame_unencrypted_packet(0x17, bb.to_bytes())

def build_lobby_conn_id() -> bytes:
    bb = BitBuffer()
    bb.write_uint64(0x0000000000001337)
    return frame_unencrypted_packet(0x04, bb.to_bytes())

def handle_client(conn: socket.socket, addr):
    print(f"[+] New Wii connection from {addr}")
    try:
        conn.settimeout(10.0)
        data = conn.recv(4096)
        if not data:
            print(f"[*] Sending Lobby Connection ID to {addr}")
            conn.sendall(build_lobby_conn_id())
            return

        print(f"[<] Received {len(data)} bytes from {addr}: {data.hex()}")

        if len(data) >= 6 and data[5] == 0x16:
            print(f"[*] Auth Request (0x16) detected! Sending 700 Login Reply...")
            reply = build_auth_reply()
            conn.sendall(reply)
            print(f"[>] Sent Auth Reply ({len(reply)} bytes)")
        else:
            print(f"[*] Lobby packet detected! Sending Lobby Connection ID...")
            conn.sendall(build_lobby_conn_id())

        while True:
            more = conn.recv(4096)
            if not more:
                break
            print(f"[<] Follow-up packet ({len(more)} bytes): {more.hex()}")

    except socket.timeout:
        try:
            print(f"[*] Lobby socket ready for {addr}; sending Lobby Connection ID...")
            conn.sendall(build_lobby_conn_id())
            while True:
                more = conn.recv(4096)
                if not more:
                    break
                print(f"[<] Lobby Task Packet ({len(more)} bytes): {more.hex()}")
        except Exception:
            pass
    except Exception as e:
        print(f"[!] Connection error with {addr}: {e}")
    finally:
        conn.close()
        print(f"[-] Closed connection from {addr}")

def main():
    print("=== CoD4: Reflex Edition (Wii) Server Revival ===")
    threading.Thread(target=start_health_server, daemon=True).start()
    threading.Thread(target=start_tcp_tunnel, daemon=True).start()

    print(f"[*] Game Server listening on {HOST}:{GAME_PORT} (TCP)...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, GAME_PORT))
        s.listen(5)
        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()

if __name__ == "__main__":
    main()
