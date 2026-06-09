"""
Discovery debug tool.
Usage:
    python test_discovery.py host    <- run on the hosting machine
    python test_discovery.py client  <- run on the joining machine
"""

import socket
import json
import sys
import time
import threading

DISCOVERY_PORT = 54321
DISCOVERY_REQUEST = 'OVERLOADED_SERVER_DISCOVERY'

def get_local_ip():
    """Get this machine's local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def run_host():
    print("=== RUNNING AS HOST ===")
    print(f"My IP address: {get_local_ip()}")
    print(f"Listening for discovery on UDP port {DISCOVERY_PORT}...")
    print("Keep this running and start client on the other machine.\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind(('0.0.0.0', DISCOVERY_PORT))
        print(f"[OK] Successfully bound to port {DISCOVERY_PORT}")
    except Exception as e:
        print(f"[FAIL] Could not bind to port {DISCOVERY_PORT}: {e}")
        print("This means something else is already using this port,")
        print("or you don't have permission.")
        return

    sock.settimeout(1.0)
    print("Waiting for discovery requests...\n")

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            msg = data.decode('utf-8').strip()
            print(f"[RECEIVED] From {addr[0]}:{addr[1]} -> '{msg}'")

            if msg == DISCOVERY_REQUEST:
                response = {
                    'type': 'discovery_response',
                    'hostname': socket.gethostname(),
                    'host_username': 'TestHost',
                    'port': 12345,
                    'players': 1,
                    'max_players': 4,
                    'game_started': False
                }
                sock.sendto(json.dumps(response).encode('utf-8'), addr)
                print(f"[SENT] Discovery response to {addr[0]}:{addr[1]}")
            else:
                print(f"[UNKNOWN] Unrecognized message: {msg}")

        except socket.timeout:
            print(".", end='', flush=True)  # heartbeat so you know it's alive
        except KeyboardInterrupt:
            print("\nStopping host.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")

    sock.close()


def run_client():
    print("=== RUNNING AS CLIENT ===")
    print(f"My IP address: {get_local_ip()}")
    print(f"Broadcasting discovery request on UDP port {DISCOVERY_PORT}...\n")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.5)

    broadcast_addr = ('255.255.255.255', DISCOVERY_PORT)

    print(f"[SENDING] '{DISCOVERY_REQUEST}' to {broadcast_addr}")
    try:
        sock.sendto(DISCOVERY_REQUEST.encode('utf-8'), broadcast_addr)
        print("[OK] Broadcast sent successfully")
    except Exception as e:
        print(f"[FAIL] Could not send broadcast: {e}")
        return

    print(f"\nWaiting for responses for 3 seconds...\n")
    start = time.time()
    found = []

    while time.time() - start < 3.0:
        try:
            data, addr = sock.recvfrom(1024)
            print(f"[RECEIVED] Response from {addr[0]}:{addr[1]}")
            try:
                response = json.loads(data.decode('utf-8'))
                print(f"[PARSED]   {json.dumps(response, indent=2)}")
                found.append(response)
            except Exception as e:
                print(f"[PARSE ERROR] {e} - raw data: {data}")
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[ERROR] {e}")

    sock.close()

    print("\n=== RESULT ===")
    if found:
        print(f"[SUCCESS] Found {len(found)} server(s)!")
        for s in found:
            print(f"  - {s.get('host_username')} at port {s.get('port')}")
    else:
        print("[FAIL] No servers found.")
        print("\nPossible reasons:")
        print("  1. Firewall blocking UDP port 54321 on the HOST machine")
        print("  2. Firewall blocking UDP broadcast on the CLIENT machine")  
        print("  3. Host script is not running")
        print("  4. Machines are on different network segments")
        print(f"\nTry pinging the host from this machine:")
        print(f"  ping <host IP address>")


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('host', 'client'):
        print("Usage:")
        print("  python test_discovery.py host    <- on hosting machine")
        print("  python test_discovery.py client  <- on joining machine")
        sys.exit(1)

    if sys.argv[1] == 'host':
        run_host()
    else:
        run_client()
