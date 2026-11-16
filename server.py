import socket
import struct
import threading
import os

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 3074))

class BitBuffer:
    """Packs DemonWare bdBitBuffer data (with 5-bit type tags)"""
    def __init__(self):
        self.bits = []

    def write_bits(self, value, num_bits):
        for i in range(num_bits):
            self.bits.append((value >> i) & 1)

    def write_data_type(self, data_type):
        # DemonWare bdBitBuffer uses 5-bit type tags when type-checked
        self.write_bits(data_type, 5)

    def write_uint32(self, val):
        self.write_data_type(8)  # Type 8 = uint32
         b = struct.pack(">I", val)
        for byte in b:
            self.write_bits(byte, 8)

    def write_uint64(self, val):
        self.write_data_type(10) # Type 10 = uint64
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
    # 0x00: Magic 0xDEADBEEF (Little-Endian -> ef be ad de)
    struct.pack_into("<I", ticket, 0x00, 0xDEADBEEF)
    # 0x04: Type/Version (1 byte)
    ticket[0x04] = 0
    # 0x05: Game ID (5153 = 0x1421) & timestamps
    struct.pack_into("<I", ticket, 0x05, 5153)
    struct.pack_into("<I", ticket, 0x09, 1)
    struct.pack_into("<I", ticket, 0x0D, 1)
    # 0x11: Account ID (8 bytes)
    struct.pack_into("<Q", ticket, 0x11, 1)
    # 0x19: 12-Digit Player Online ID (8 bytes, read into +0x20/+0x24)
    struct.pack_into("<Q", ticket, 0x19, online_id)
    # 0x21: Username (64 bytes, read into +0x28)
    name_bytes = username.encode("ascii")[:63]
    ticket[0x21:0x21 + len(name_bytes)] = name_bytes
    # 0x61: 24-byte Session Key
    ticket[0x61:0x61 + 24] = b"A" * 24
    return bytes(ticket)

def frame_unencrypted_packet(msg_type: int, payload: bytes) -> bytes:
    """
    Wraps payload in DemonWare TCP frame (FUN_8094d430):
    [4-byte length (LE)] [1-byte enc_flag = 0x00] [1-byte msg_type] [payload]
    """
    length = 2 + len(payload)
    return struct.pack("<IBB", length, 0x00, msg_type) + payload

def build_auth_reply() -> bytes:
    """Builds Message Type 0x17 (Auth Reply) for FUN_8094bd04"""
    bb = BitBuffer()
    bb.write_uint32(700)        # 700 = BD_NO_ERROR (Login Success!)
    bb.write_uint32(0x12345678) # IV Seed (local_71c)
    bb.write_raw_bytes(b"\x00" * 128)         # 128-byte RSA Sig (bypassed via Gecko)
    bb.write_raw_bytes(build_user_ticket())   # 128-byte User Ticket (0xDEADBEEF)
    bb.write_raw_bytes(b"\x00" * 128)         # 128-byte Lobby Server Ticket
    return frame_unencrypted_packet(0x17, bb.to_bytes())

def build_lobby_conn_id() -> bytes:
    """Builds Message Type 0x04 (LSG Connection ID) for FUN_8094ebc8"""
    bb = BitBuffer()
    bb.write_uint64(0x0000000000001337)
    return frame_unencrypted_packet(0x04, bb.to_bytes())

def handle_client(conn: socket.socket, addr):
    print(f"[+] New connection from {addr}")
    try:
        conn.settimeout(15.0)
        data = conn.recv(4096)
        if not data:
            # Lobby server connection doesn't send an initial packet right away;
            # send LSG Connection ID!
            print(f"[*] Sending Lobby Connection ID to {addr}")
            conn.sendall(build_lobby_conn_id())
            return

        print(f"[<] Received {len(data)} bytes from {addr}: {data.hex()}")

        # Check if it's an Auth Request (Message Type 0x16 at byte 5)
        if len(data) >= 6 and data[5] == 0x16:
            print(f"[*] Auth Request (0x16) detected! Sending 700 Login Reply...")
            reply = build_auth_reply()
            conn.sendall(reply)
            print(f"[>] Sent Auth Reply ({len(reply)} bytes)")
        else:
            # Lobby traffic
            print(f"[*] Lobby packet detected! Sending Lobby Connection ID...")
            conn.sendall(build_lobby_conn_id())

        # Keep connection open for subsequent lobby tasks
        while True:
            more = conn.recv(4096)
            if not more:
                break
            print(f"[<] Follow-up packet ({len(more)} bytes): {more.hex()}")

    except socket.timeout:
        # If client connected and waited (Lobby connection), send Lobby ID
        try:
            print(f"[*] Timeout waiting for first packet from {addr}; sending Lobby ID...")
            conn.sendall(build_lobby_conn_id())
        except Exception:
            pass
    except Exception as e:
        print(f"[!] Connection error with {addr}: {e}")
    finally:
        conn.close()
        print(f"[-] Closed connection from {addr}")

def main():
    print(f"=== CoD4: Reflex Edition (Wii) Server Revival ===")
    print(f"Listening on {HOST}:{PORT} (TCP)...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(5)
        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()

if __name__ == "__main__":
    main()
