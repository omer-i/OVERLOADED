import socket
import json
import threading
import time


class ServerDiscovery:
    """Handles server discovery via UDP broadcast on the local network."""
    
    DISCOVERY_PORT = 54321
    BROADCAST_ADDRESS = '<broadcast>'
    DISCOVERY_REQUEST = 'OVERLOADED_SERVER_DISCOVERY'
    
    @staticmethod
    def start_discovery_listener(server, port=12345, discovery_port=DISCOVERY_PORT):
        """Start a UDP listener for discovery requests on the server.
        
        Args:
            server: The Server instance to get player count from
            port: The TCP port the server is listening on
            discovery_port: The UDP port to listen on for discovery requests
        """
        def listen():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('0.0.0.0', discovery_port))
                sock.settimeout(1.0)
                
                while server._running:
                    try:
                        data, addr = sock.recvfrom(1024)
                        if data.decode('utf-8').strip() == ServerDiscovery.DISCOVERY_REQUEST:
                            # Respond with server info
                            with server._lock:
                                player_count = len(server.players)
                                response = {
                                    'type': 'discovery_response',
                                    'hostname': socket.gethostname(),
                                    'host_username': server.host_username or 'Host',
                                    'port': port,
                                    'players': player_count,
                                    'max_players': 4,  # Can be configured
                                    'game_started': server.game_started
                                }
                            sock.sendto(json.dumps(response).encode('utf-8'), addr)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"Discovery listener error: {e}")
                        
            except Exception as e:
                print(f"Discovery listener init error: {e}")
            finally:
                try:
                    sock.close()
                except:
                    pass
        
        thread = threading.Thread(target=listen, daemon=True)
        thread.start()
        return thread
    
    @staticmethod
    def discover_servers(timeout=2.0, discovery_port=DISCOVERY_PORT):
        """Broadcast discovery request and collect available servers.
        
        Args:
            timeout: How long to wait for responses (in seconds)
            discovery_port: The UDP port to broadcast on
            
        Returns:
            List of discovered servers: [{'hostname': str, 'port': int, 'players': int, ...}, ...]
        """
        servers = []
        
        try:
            # Create UDP socket for broadcasting
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.5)
            
            # Send discovery broadcast
            broadcast_addr = ('255.255.255.255', discovery_port)
            sock.sendto(ServerDiscovery.DISCOVERY_REQUEST.encode('utf-8'), broadcast_addr)
            
            # Collect responses
            start_time = time.time()
            seen_servers = set()  # Track unique servers by (hostname, port)
            
            while time.time() - start_time < timeout:
                try:
                    data, addr = sock.recvfrom(1024)
                    response = json.loads(data.decode('utf-8'))
                    
                    if response.get('type') == 'discovery_response':
                        # Create unique key to avoid duplicates
                        key = (response.get('hostname'), response.get('port'))
                        if key not in seen_servers:
                            seen_servers.add(key)
                            response['ip'] = addr[0]  # Add actual IP for connection
                            servers.append(response)
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error parsing discovery response: {e}")
                    continue
            
            sock.close()
            
        except Exception as e:
            print(f"Server discovery error: {e}")
        
        # Sort by number of players (full servers at end)
        servers.sort(key=lambda s: (s.get('game_started', False), s.get('players', 0)))
        
        return servers
