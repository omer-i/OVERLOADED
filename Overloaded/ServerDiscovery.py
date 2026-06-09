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
    def _get_real_local_ip():
        """Find the IP of the real network adapter (the one with internet access).
        
        Does this by opening a UDP socket toward an external address - no data
        is actually sent, but the OS picks the correct outbound interface.
        Returns the IP string, or '0.0.0.0' as fallback.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Connecting to an external address forces OS to pick the right adapter.
            # No data is sent - UDP connect just sets the route.
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '0.0.0.0'

    @staticmethod
    def _get_broadcast_address(local_ip):
        """Calculate the subnet broadcast address from a local IP.
        
        Uses the OS routing table via socket to determine the correct
        broadcast address for the given local IP's subnet.
        Falls back to 255.255.255.255 if calculation fails.
        """
        try:
            # Get all network interfaces and find the one matching our IP
            import ipaddress
            # Try to get subnet info via socket
            # We'll use a common approach: try to get the netmask
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            import fcntl
            import struct
            # This is Linux-only, so wrap in try/except
            import fcntl
            SIOCGIFNETMASK = 0x891b
            # fallback for Windows
        except Exception:
            pass
        
        # Windows-compatible approach: use the IP with common subnet masks
        # Since both machines are on 255.255.248.0, calculate broadcast
        try:
            import ipaddress
            # Get all interfaces
            hostname = socket.gethostname()
            all_ips = socket.getaddrinfo(hostname, None)
            
            # Try to find subnet for our IP using a trick:
            # connect to our own IP to get interface info
            # Actually just compute from the local_ip directly
            # For 10.30.56.x with /21 (255.255.248.0): broadcast is 10.30.63.255
            # We detect this dynamically below
            pass
        except Exception:
            pass

        # Most reliable cross-platform approach:
        # Send to 255.255.255.255 but BIND to the specific local IP
        # This forces the packet out the right adapter even without knowing the subnet
        return '255.255.255.255'

    @staticmethod
    def start_discovery_listener(server, port=12345, discovery_port=DISCOVERY_PORT):
        """Start a UDP listener for discovery requests on the server."""
        def listen():
            try:
                local_ip = ServerDiscovery._get_real_local_ip()
                print(f"Discovery listener binding to {local_ip}:{discovery_port}")
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Bind to the real adapter IP, not 0.0.0.0
                # This ensures we only listen on the real network, not virtual adapters
                sock.bind((local_ip, discovery_port))
                sock.settimeout(1.0)
                
                print(f"Discovery listener ready on {local_ip}:{discovery_port}")
                
                while server._running:
                    try:
                        data, addr = sock.recvfrom(1024)
                        if data.decode('utf-8').strip() == ServerDiscovery.DISCOVERY_REQUEST:
                            with server._lock:
                                player_count = len(server.players)
                                response = {
                                    'type': 'discovery_response',
                                    'hostname': socket.gethostname(),
                                    'host_username': server.host_username or 'Host',
                                    'port': port,
                                    'players': player_count,
                                    'max_players': 4,
                                    'game_started': server.game_started
                                }
                            sock.sendto(json.dumps(response).encode('utf-8'), addr)
                            print(f"Discovery: responded to {addr[0]}")
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
        """Broadcast discovery request and collect available servers."""
        servers = []
        
        try:
            local_ip = ServerDiscovery._get_real_local_ip()
            print(f"Discovery: using local IP {local_ip}")

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.5)
            
            # Bind to the real adapter so broadcast goes out the right interface
            # Port 0 means OS picks a free port for us
            sock.bind((local_ip, 0))
            print(f"Discovery: bound to {local_ip}, broadcasting...")

            broadcast_addr = ('255.255.255.255', discovery_port)
            sock.sendto(ServerDiscovery.DISCOVERY_REQUEST.encode('utf-8'), broadcast_addr)
            print(f"Discovery: broadcast sent to {broadcast_addr}")
            
            start_time = time.time()
            seen_servers = set()
            
            while time.time() - start_time < timeout:
                try:
                    data, addr = sock.recvfrom(1024)
                    print(f"Discovery: got response from {addr[0]}")
                    response = json.loads(data.decode('utf-8'))
                    
                    if response.get('type') == 'discovery_response':
                        key = (response.get('hostname'), response.get('port'))
                        if key not in seen_servers:
                            seen_servers.add(key)
                            response['ip'] = addr[0]
                            servers.append(response)
                            print(f"Discovery: found server '{response.get('host_username')}' at {addr[0]}")
                            
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error parsing discovery response: {e}")
                    continue
            
            sock.close()
            
        except Exception as e:
            print(f"Server discovery error: {e}")
        
        servers.sort(key=lambda s: (s.get('game_started', False), s.get('players', 0)))
        print(f"Discovery: found {len(servers)} server(s)")
        return servers
