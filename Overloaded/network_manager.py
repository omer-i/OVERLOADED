import threading
import time
from Server import Server
from Client import Client
from ServerDiscovery import ServerDiscovery

class NetworkManager:
    def __init__(self, game):
        self.game = game
        self.server = None
        self.client = None
        self.is_hosting = False
        self.is_connected = False

    def start_host(self, host='0.0.0.0', port=12345, username=None):
        if self.is_hosting: return
        self.server = Server(host=host, port=port, host_username=username)
        self.server.start()
        self.is_hosting = True
        # Do not auto-join here; let the caller decide when/if to join.
        return True

    def join_server(self, host='localhost', port=12345):
        if self.is_connected: return True
        
        try:
            self.client = Client(host=host, port=port)
            if self.client.connect():
                # Critical: Wait for server to acknowledge us
                start_t = time.time()
                while time.time() - start_t < 3.0:
                    if self.client.client_id is not None:
                        self.is_connected = True
                        # Send authentication if user is logged in
                        if self.game.current_user:
                            self.client.announce_username(self.game.current_user)
                        return True
                    time.sleep(0.1)
            
            print("Network: Connection timed out.")
            self.stop_network()
            return False
        except Exception as e:
            print(f"Network: Join error: {e}")
            self.stop_network()
            return False

    def stop_network(self):
        if self.client: 
            self.client.close()
            self.client = None
        if self.server: 
            self.server.stop()
            self.server = None
        self.is_connected = False
        self.is_hosting = False
    
    def discover_available_servers(self, timeout=2.0):
        """Discover available game servers on the local network.
        
        Returns:
            List of server info dicts: [{'hostname': str, 'port': int, 'players': int, 'ip': str, ...}, ...]
        """
        return ServerDiscovery.discover_servers(timeout=timeout)