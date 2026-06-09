import socket
import json
import threading
import time


class ServerDiscovery:
    """Handles server discovery via UDP broadcast on the local network."""
    
    DISCOVERY_PORT = 54321
    DISCOVERY_REQUEST = 'OVERLOADED_SERVER_DISCOVERY'

    @staticmethod
    def _get_real_local_ip():
        """Find the IP of the real network adapter by routing toward external address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '0.0.0.0'

    @staticmethod
    def start_discovery_listener(server, port=12345, discovery_port=DISCOVERY_PORT):
        """Start UDP listeners on ALL local IPs so we never miss a request."""
        def listen(bind_ip):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((bind_ip, discovery_port))
                sock.settimeout(1.0)
                print(f"Discovery listener bound to {bind_ip}:{discovery_port}")
                
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
                        print(f"Discovery listener error on {bind_ip}: {e}")
            except Exception as e:
                print(f"Discovery listener could not bind to {bind_ip}: {e}")
            finally:
                try:
                    sock.close()
                except:
                    pass

        # Get all local IPs this machine has
        local_ips = ServerDiscovery._get_all_local_ips()
        print(f"Discovery: starting listeners on {local_ips}")
        
        threads = []
        for ip in local_ips:
            t = threading.Thread(target=listen, args=(ip,), daemon=True)
            t.start()
            threads.append(t)
        
        return threads

    @staticmethod
    def _get_all_local_ips():
        """Get all IPv4 addresses this machine has across all adapters."""
        ips = set()
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None):
                ip = info[4][0]
                # Only IPv4, skip loopback
                if '.' in ip and not ip.startswith('127.'):
                    ips.add(ip)
        except Exception:
            pass
        
        # Also add the real IP from routing trick
        real = ServerDiscovery._get_real_local_ip()
        if real != '0.0.0.0':
            ips.add(real)
        
        # Always include 0.0.0.0 as fallback
        if not ips:
            ips.add('0.0.0.0')
        
        return list(ips)

    @staticmethod
    def discover_servers(timeout=2.0, discovery_port=DISCOVERY_PORT):
        """Broadcast discovery request and collect available servers."""
        servers = []
        seen_servers = set()

        real_ip = ServerDiscovery._get_real_local_ip()
        print(f"Discovery: real IP is {real_ip}")

        def try_discover(bind_ip, broadcast_ip):
            """Try one discovery strategy, append results to servers list."""
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(0.5)
                
                if bind_ip != '0.0.0.0':
                    sock.bind((bind_ip, 0))
                
                sock.sendto(
                    ServerDiscovery.DISCOVERY_REQUEST.encode('utf-8'),
                    (broadcast_ip, discovery_port)
                )
                print(f"Discovery: sent from {bind_ip} to {broadcast_ip}:{discovery_port}")
                
                deadline = time.time() + timeout
                while time.time() < deadline:
                    try:
                        data, addr = sock.recvfrom(1024)
                        response = json.loads(data.decode('utf-8'))
                        if response.get('type') == 'discovery_response':
                            key = (response.get('hostname'), response.get('port'))
                            if key not in seen_servers:
                                seen_servers.add(key)
                                response['ip'] = addr[0]
                                servers.append(response)
                                print(f"Discovery: found server at {addr[0]}")
                    except socket.timeout:
                        break
                    except Exception:
                        break
                
                sock.close()
            except Exception as e:
                print(f"Discovery strategy {bind_ip}->{broadcast_ip} failed: {e}")

        # Strategy 1: bind to real IP, broadcast globally
        try_discover(real_ip, '255.255.255.255')
        
        # Strategy 2: unbound, broadcast globally  
        if not servers:
            try_discover('0.0.0.0', '255.255.255.255')

        # Strategy 3: scan subnet directly (send to each .x on same /21)
        # This works even when broadcast is blocked
        if not servers and real_ip != '0.0.0.0':
            print("Broadcast failed, trying subnet scan...")
            parts = real_ip.split('.')
            base = f"{parts[0]}.{parts[1]}.{parts[2]}."
            
            def scan_ip(target_ip):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.settimeout(0.3)
                    s.bind((real_ip, 0))
                    s.sendto(
                        ServerDiscovery.DISCOVERY_REQUEST.encode('utf-8'),
                        (target_ip, discovery_port)
                    )
                    try:
                        data, addr = s.recvfrom(1024)
                        response = json.loads(data.decode('utf-8'))
                        if response.get('type') == 'discovery_response':
                            key = (response.get('hostname'), response.get('port'))
                            if key not in seen_servers:
                                seen_servers.add(key)
                                response['ip'] = addr[0]
                                servers.append(response)
                                print(f"Discovery: found server at {addr[0]} via direct scan")
                    except socket.timeout:
                        pass
                    s.close()
                except Exception:
                    pass

            # Scan all IPs in the same /24
            scan_threads = []
            for i in range(1, 255):
                target = base + str(i)
                if target == real_ip:
                    continue
                t = threading.Thread(target=scan_ip, args=(target,), daemon=True)
                t.start()
                scan_threads.append(t)
            
            # Wait for all scans to complete
            for t in scan_threads:
                t.join(timeout=1.0)

        servers.sort(key=lambda s: (s.get('game_started', False), s.get('players', 0)))
        print(f"Discovery: found {len(servers)} server(s) total")
        return servers
