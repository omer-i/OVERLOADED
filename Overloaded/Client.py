import socket
import threading
import json
import time


class Client:
    def __init__(self, host='localhost', port=12345):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.file = None
        self._recv_thread = None
        self._running = False
        self.client_id = None
        self._lock = threading.Lock()
        self.latest_state = None
        self._auth_event = threading.Event()
        self._auth_result = None
        self._register_event = threading.Event()
        self._register_result = None

    def connect(self, timeout=5.0):
        try:
            self.sock.settimeout(timeout)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None)
            self.file = self.sock.makefile('rwb')
            self._running = True
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()
            print(f"Connected to server at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def _recv_loop(self):
        f = self.file
        while self._running:
            try:
                line = f.readline()
                if not line:
                    break
                decoded = line.decode('utf-8').strip()
                try:
                    data = json.loads(decoded)
                except Exception:
                    continue

                print(f"Client recv: {data}")
                if data.get('type') == 'welcome':
                    self.client_id = data.get('id')
                    print(f"Assigned client_id: {self.client_id}")
                elif data.get('type') == 'auth':
                    self._auth_result = data
                    self._auth_event.set()
                elif data.get('type') == 'register':
                    self._register_result = data
                    self._register_event.set()
                else:
                    with self._lock:
                        self.latest_state = data
            except Exception:
                break
        self._running = False

    def send_input(self, x, y, health=None):
        obj = {'type': 'input', 'x': float(x), 'y': float(y)}
        if health is not None:
            obj['health'] = int(health)
        try:
            self.sock.sendall((json.dumps(obj) + '\n').encode('utf-8'))
        except Exception:
            pass

    def send_shoot(self, ox, oy, ex, ey):
        obj = {'type': 'shoot', 'ox': float(ox), 'oy': float(oy), 'tx': float(ex), 'ty': float(ey)}
        try:
            self.sock.sendall((json.dumps(obj) + '\n').encode('utf-8'))
        except Exception:
            pass

    def send_auth(self, username, password, timeout=5.0):
        """Send credentials to the server and block until a response arrives.
        Returns True if the server accepted the credentials."""
        self._auth_event.clear()
        self._auth_result = None
        obj = {'type': 'auth', 'username': username, 'password': password}
        try:
            self.sock.sendall((json.dumps(obj) + '\n').encode('utf-8'))
        except Exception:
            return False
        if not self._auth_event.wait(timeout=timeout):
            return False
        return bool(self._auth_result and self._auth_result.get('ok'))

    def announce_username(self, username):
        """Tell the server our username without waiting for a response.
        Used after already being authenticated to register presence on a server."""
        obj = {'type': 'auth', 'username': username, 'password': ''}
        try:
            self.sock.sendall((json.dumps(obj) + '\n').encode('utf-8'))
        except Exception:
            pass

    def send_register(self, username, password, timeout=5.0):
        """Register a new account on the server.
        Returns (ok: bool, msg: str)."""
        self._register_event.clear()
        self._register_result = None
        obj = {'type': 'register', 'username': username, 'password': password}
        try:
            self.sock.sendall((json.dumps(obj) + '\n').encode('utf-8'))
        except Exception:
            return False, 'Connection error'
        if not self._register_event.wait(timeout=timeout):
            return False, 'Server timed out'
        result = self._register_result
        if not result:
            return False, 'No response'
        return bool(result.get('ok')), result.get('msg', 'Unknown error')

    def send_ready(self, ready=True):
        obj = {'type': 'ready', 'ready': bool(ready)}
        try:
            self.sock.sendall((json.dumps(obj) + '\n').encode('utf-8'))
        except Exception:
            pass

    def get_latest_state(self):
        with self._lock:
            return self.latest_state.copy() if isinstance(self.latest_state, dict) else self.latest_state

    def close(self):
        self._running = False
        try:
            if self.file:
                self.file.close()
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass
        print('Client closed')
