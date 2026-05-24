import socket
import threading
import json
import time
import random
import pygame
from auth import AuthManager
from Enemy import Enemy
from ServerDiscovery import ServerDiscovery

class Server:
    def __init__(self, host='0.0.0.0', port=12345, tick_rate=20, host_username=None):
        # Initialize pygame for Enemy sprite handling
        if not pygame.display.get_surface():
            pygame.init()
            pygame.display.set_mode((1, 1))  # Minimal hidden display for server
        
        self.host = host
        self.port = port
        self.tick_rate = tick_rate
        self.host_username = host_username
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.clients = {}  # cid -> {sock, file}
        self.players = {}  # cid -> {x, y, health, username, ready}
        self.enemies = {}  # eid -> Enemy instance
        self.player_kills = {}  # cid -> kill count this session
        self._lock = threading.Lock()
        self._next_client_id = 1
        self._next_enemy_id = 1
        self.auth = AuthManager()
        self._running = False
        self.game_started = False
        
        # WORLD SETUP - same as game.py
        self.world_dimensions = (3120, 2340)  # 1.3x and 1.5x of typical screen
        self.world_bounds = pygame.Rect(0, 0, self.world_dimensions[0], self.world_dimensions[1])
        
        # WALLS - same as game.py
        wall_thickness = 20
        world_width, world_height = self.world_dimensions
        self.walls = [
            pygame.Rect(0, 0, world_width, wall_thickness),  # top
            pygame.Rect(0, world_height - wall_thickness, world_width, wall_thickness),  # bottom
            pygame.Rect(0, 0, wall_thickness, world_height),  # left
            pygame.Rect(world_width - wall_thickness, 0, wall_thickness, world_height),  # right
            pygame.Rect(1800, 500, 100, 300),  # central obstacle
        ]
        
        # DIFFICULTY PROGRESSION
        self.elapsed_gameplay_time = 0.0
        self.base_spawn_interval = 2.0
        self.spawn_interval_current = self.base_spawn_interval
        self.spawn_timer = 0.0 

    def start(self):
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen()
            self._running = True
            threading.Thread(target=self._accept_loop, daemon=True).start()
            threading.Thread(target=self._game_loop, daemon=True).start()
            # Start discovery listener for room browsing
            ServerDiscovery.start_discovery_listener(self, port=self.port)
            print(f"Server: Listening on {self.host}:{self.port}")
        except Exception as e:
            print(f"Server Error: {e}")

    def start_game(self):
        with self._lock:
            self.game_started = True
            self.elapsed_gameplay_time = 0.0
            self.spawn_timer = self.spawn_interval_current
            # Reset kill counts for this game session
            self.player_kills = {cid: 0 for cid in self.players.keys()}
            print("Server: Game state changed to STARTED")

    def _accept_loop(self):
        while self._running:
            try:
                conn, addr = self.server_socket.accept()
                with self._lock:
                    cid = self._next_client_id
                    self._next_client_id += 1
                    # track client socket and authentication state
                    self.clients[cid] = {'sock': conn, 'auth': False}
                    # player entry created immediately but username/ready updated on auth
                    self.players[cid] = {'id': cid, 'x': 400, 'y': 300, 'health': 100, 'username': None, 'ready': False}
                
                # Send welcome ID immediately
                conn.sendall((json.dumps({'type': 'welcome', 'id': cid}) + '\n').encode('utf-8'))
                threading.Thread(target=self._handle_client, args=(cid, conn), daemon=True).start()
            except: break

    def _handle_client(self, cid, conn):
        f = conn.makefile('r')
        while self._running:
            try:
                line = f.readline()
                if not line: break
                data = json.loads(line)
                if data.get('type') == 'input':
                    with self._lock:
                        if cid in self.players:
                            self.players[cid].update({'x': data['x'], 'y': data['y'], 'health': data.get('health', 100)})
                elif data.get('type') == 'auth':
                    # client is attempting to authenticate with username/password
                    # if password is empty, trust the username (for in-game sessions where client already authenticated locally)
                    uname = data.get('username')
                    pwd = data.get('password')
                    ok = False
                    try:
                        if pwd == '' and uname:
                            # During game join without password - just trust the username claim
                            ok = True
                        else:
                            # Full password authentication
                            ok = self.auth.authenticate(uname, pwd)
                    except Exception:
                        ok = False
                    try:
                        resp = {'type': 'auth', 'ok': bool(ok)}
                        conn.sendall((json.dumps(resp) + '\n').encode('utf-8'))
                    except Exception:
                        pass
                    if ok:
                        with self._lock:
                            self.clients[cid]['auth'] = True
                            if cid in self.players:
                                self.players[cid]['username'] = uname
                elif data.get('type') == 'register':
                    uname = data.get('username', '').strip()
                    pwd = data.get('password', '')
                    ok, msg = False, 'Error'
                    try:
                        ok, msg = self.auth.register(uname, pwd)
                    except Exception as e:
                        msg = str(e)
                    try:
                        conn.sendall((json.dumps({'type': 'register', 'ok': bool(ok), 'msg': msg}) + '\n').encode('utf-8'))
                    except Exception:
                        pass
                    if ok:
                        with self._lock:
                            self.clients[cid]['auth'] = True
                            if cid in self.players:
                                self.players[cid]['username'] = uname
                elif data.get('type') == 'ready':
                    val = bool(data.get('ready', False))
                    with self._lock:
                        if cid in self.players:
                            self.players[cid]['ready'] = val
                elif data.get('type') == 'shoot':
                    # Expected fields: 'ox','oy' (origin), 'tx','ty' (target/end)
                    ox = float(data.get('ox', 0))
                    oy = float(data.get('oy', 0))
                    tx = float(data.get('tx', ox))
                    ty = float(data.get('ty', oy))
                    damage = float(data.get('damage', 60))
                    # simple distance-to-segment test against each enemy
                    def point_segment_dist2(px, py, x1, y1, x2, y2):
                        vx = x2 - x1
                        vy = y2 - y1
                        wx = px - x1
                        wy = py - y1
                        vv = vx*vx + vy*vy
                        if vv == 0:
                            # degenerate segment
                            dx = px - x1
                            dy = py - y1
                            return dx*dx + dy*dy
                        t = (wx*vx + wy*vy) / vv
                        if t < 0: t = 0
                        elif t > 1: t = 1
                        projx = x1 + t * vx
                        projy = y1 + t * vy
                        dx = px - projx
                        dy = py - projy
                        return dx*dx + dy*dy

                    hit_radius = 28.0
                    hit_r2 = hit_radius * hit_radius
                    with self._lock:
                        to_remove = []
                        for eid, enemy in list(self.enemies.items()):
                            try:
                                # Use Enemy object properties instead of dict
                                d2 = point_segment_dist2(enemy.pos.x, enemy.pos.y, ox, oy, tx, ty)
                                if d2 <= hit_r2:
                                    enemy.health -= damage
                                    if enemy.health <= 0:
                                        to_remove.append(eid)
                            except Exception as e:
                                print(f"Error checking enemy collision: {e}")
                        
                        for eid in to_remove:
                            try:
                                del self.enemies[eid]
                                if cid in self.player_kills:
                                    self.player_kills[cid] += 1
                                    username = self.players.get(cid, {}).get('username')
                                    if username:
                                        try:
                                            self.auth.record_game_kills(username, self.player_kills[cid])
                                        except Exception:
                                            pass
                            except KeyError:
                                pass
            except: break
        self._disconnect(cid)

    def _disconnect(self, cid):
        with self._lock:
            # Submit final kill count before disconnecting
            if self.game_started and cid in self.player_kills and cid in self.players:
                username = self.players[cid].get('username')
                if username:
                    try:
                        self.auth.record_game_kills(username, self.player_kills[cid])
                    except Exception as e:
                        print(f"Error recording final kills for {username}: {e}")
            
            if cid in self.clients:
                try: self.clients[cid]['sock'].close()
                except: pass
                del self.clients[cid]
            if cid in self.players: 
                del self.players[cid]
            if cid in self.player_kills:
                del self.player_kills[cid]
            print(f"Server: Client {cid} disconnected")
    
    # ============================================================================
    # GAME LOGIC METHODS (from game.py)
    # ============================================================================
    
    def update_difficulty(self, dt):
        """Update elapsed time and calculate difficulty multiplier."""
        self.elapsed_gameplay_time += dt
        
        # Speed scales from 1.0x to 3.0x over time
        speed_multiplier = min(3.0, 1.0 + self.elapsed_gameplay_time * 0.005)
        
        # Spawn rate increases from base interval down to 0.3 seconds minimum
        self.spawn_interval_current = max(
            0.3,
            self.base_spawn_interval * max(0.2, 1.0 - self.elapsed_gameplay_time * 0.003)
        )
        
        return speed_multiplier
    
    def get_server_viewport(self):
        """Calculate viewport bounding box around all active players.
        
        Returns pygame.Rect representing the area where enemies should spawn.
        Falls back to center of world if no players.
        """
        if not self.players:
            # Default viewport centered on world
            center_x = self.world_dimensions[0] // 2
            center_y = self.world_dimensions[1] // 2
            return pygame.Rect(center_x - 960, center_y - 540, 1920, 1080)
        
        # Find bounding box of all players
        positions = [p for p in self.players.values() if p]
        if not positions:
            center_x = self.world_dimensions[0] // 2
            center_y = self.world_dimensions[1] // 2
            return pygame.Rect(center_x - 960, center_y - 540, 1920, 1080)
        
        xs = [p['x'] for p in positions]
        ys = [p['y'] for p in positions]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        # Expand viewport to account for all players with margin
        margin = 400
        left = max(self.world_bounds.left, min_x - margin)
        top = max(self.world_bounds.top, min_y - margin)
        right = min(self.world_bounds.right, max_x + margin)
        bottom = min(self.world_bounds.bottom, max_y + margin)
        
        return pygame.Rect(left, top, right - left, bottom - top)
    
    def spawn_enemy_at_edge(self, viewport_rect, difficulty_multiplier=1.0):
        """Spawn enemy at edge of viewport (from game.py)."""
        spawn_margin = 280
        valid_spawn_positions = []
        
        viewport_left = viewport_rect.left
        viewport_top = viewport_rect.top
        viewport_right = viewport_rect.right
        viewport_bottom = viewport_rect.bottom
        
        # TOP EDGE
        spawn_x = random.randint(viewport_left, viewport_right)
        spawn_y = viewport_top - spawn_margin
        if self.world_bounds.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))
        
        # RIGHT EDGE
        spawn_x = viewport_right + spawn_margin
        spawn_y = random.randint(viewport_top, viewport_bottom)
        if self.world_bounds.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))
        
        # BOTTOM EDGE
        spawn_x = random.randint(viewport_left, viewport_right)
        spawn_y = viewport_bottom + spawn_margin
        if self.world_bounds.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))
        
        # LEFT EDGE
        spawn_x = viewport_left - spawn_margin
        spawn_y = random.randint(viewport_top, viewport_bottom)
        if self.world_bounds.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))
        
        if not valid_spawn_positions:
            return None
        
        final_spawn_x, final_spawn_y = random.choice(valid_spawn_positions)
        
        # Create enemy with difficulty-scaled stats
        enemy_base_speed = random.randint(60, 120)
        scaled_speed = int(enemy_base_speed * difficulty_multiplier)
        scaled_health = int(30 * (difficulty_multiplier ** 1.2))
        
        return Enemy(
            pos=(final_spawn_x, final_spawn_y),
            patrol_points=[(final_spawn_x, final_spawn_y)],
            speed=scaled_speed,
            hp=scaled_health
        )
    
    def resolve_entity_wall_collision(self, entity, walls_list):
        """Resolve collision between entity and walls (from game.py)."""
        for wall_rect in walls_list:
            if entity.rect.colliderect(wall_rect):
                x_overlap = min(
                    entity.rect.right - wall_rect.left,
                    wall_rect.right - entity.rect.left
                )
                y_overlap = min(
                    entity.rect.bottom - wall_rect.top,
                    wall_rect.bottom - entity.rect.top
                )
                
                if x_overlap < y_overlap:
                    if entity.rect.centerx < wall_rect.centerx:
                        entity.pos.x -= x_overlap
                    else:
                        entity.pos.x += x_overlap
                else:
                    if entity.rect.centery < wall_rect.centery:
                        entity.pos.y -= y_overlap
                    else:
                        entity.pos.y += y_overlap
                
                if hasattr(entity, 'update_rects'):
                    entity.update_rects()
                else:
                    entity.rect.center = (round(entity.pos.x), round(entity.pos.y))
    
    def resolve_enemy_collisions(self):
        """Prevent enemies from overlapping (from game.py)."""
        enemies_list = list(self.enemies.values())
        for i in range(len(enemies_list)):
            for j in range(i + 1, len(enemies_list)):
                enemy1 = enemies_list[i]
                enemy2 = enemies_list[j]
                if enemy1.rect.colliderect(enemy2.rect):
                    dx = enemy1.pos.x - enemy2.pos.x
                    dy = enemy1.pos.y - enemy2.pos.y
                    distance = (dx ** 2 + dy ** 2) ** 0.5
                    if distance > 0:
                        dx /= distance
                        dy /= distance
                        push_distance = 8
                        enemy1.pos.x += dx * push_distance
                        enemy1.pos.y += dy * push_distance
                        enemy2.pos.x -= dx * push_distance
                        enemy2.pos.y -= dy * push_distance
    
    def handle_enemy_player_damage(self):
        """Check for enemy-player collisions and apply damage."""
        for cid, player in self.players.items():
            player_pos = pygame.Vector2(player['x'], player['y'])
            player_rect = pygame.Rect(player_pos.x - 18, player_pos.y - 18, 36, 36)
            
            for eid, enemy in list(self.enemies.items()):
                if enemy.rect.colliderect(player_rect):
                    # Apply damage
                    damage = getattr(enemy, 'contact_damage', 10)
                    new_health = max(0, player['health'] - damage)
                    self.players[cid]['health'] = new_health
                    
                    if new_health <= 0:
                        print(f"Server: Player {cid} defeated by enemy {eid}")

    def _game_loop(self):
        """Main server game loop with sophisticated game logic (from game.py)."""
        tick_dt = 1.0 / max(1, self.tick_rate)

        while self._running:
            t0 = time.time()
            with self._lock:
                if self.game_started:
                    # UPDATE DIFFICULTY & PROGRESSION
                    difficulty_multiplier = self.update_difficulty(tick_dt)
                    
                    # Get viewport for spawning
                    viewport = self.get_server_viewport()
                    
                    # ENEMY SPAWNING
                    self.spawn_timer -= tick_dt
                    if self.spawn_timer <= 0:
                        new_enemy = self.spawn_enemy_at_edge(viewport, difficulty_multiplier)
                        if new_enemy:
                            eid = self._next_enemy_id
                            self._next_enemy_id += 1
                            self.enemies[eid] = new_enemy
                        self.spawn_timer = self.spawn_interval_current
                    
                    # UPDATE ENEMIES
                    for eid, enemy in list(self.enemies.items()):
                        if not self.players:
                            continue
                        
                        # Find nearest player for chasing
                        player_list = [(pid, p['x'], p['y']) for pid, p in self.players.items()]
                        if player_list:
                            nearest_pid, nearest_x, nearest_y = min(
                                player_list,
                                key=lambda p: (p[1] - enemy.pos.x) ** 2 + (p[2] - enemy.pos.y) ** 2
                            )
                            
                            # Update enemy with difficulty-scaled speed
                            try:
                                enemy.movement_speed = int(enemy.base_speed * difficulty_multiplier)
                                enemy.max_health = int(enemy.base_health * difficulty_multiplier)
                            except Exception:
                                pass
                            
                            # Create temporary player object for enemy chase logic
                            class TempPlayer:
                                def __init__(self, x, y):
                                    self.pos = pygame.Vector2(x, y)
                            
                            temp_player = TempPlayer(nearest_x, nearest_y)
                            enemy.update(tick_dt, target=temp_player)
                        
                        # Wall collision resolution
                        self.resolve_entity_wall_collision(enemy, self.walls)
                        
                        # Clamp to world bounds
                        enemy.pos.x = max(self.world_bounds.left + 20, min(enemy.pos.x, self.world_bounds.right - 20))
                        enemy.pos.y = max(self.world_bounds.top + 20, min(enemy.pos.y, self.world_bounds.bottom - 20))
                        enemy.rect.center = (round(enemy.pos.x), round(enemy.pos.y))
                    
                    # RESOLVE ENEMY COLLISIONS
                    self.resolve_enemy_collisions()
                    
                    # HANDLE ENEMY-PLAYER DAMAGE
                    self.handle_enemy_player_damage()

                # Use 'state' if game started, otherwise 'lobby'
                msg_type = 'state' if self.game_started else 'lobby'
                # Build player list with authoritative kill counts
                players_data = []
                for pcid, player_data in self.players.items():
                    p = dict(player_data)
                    p['kills'] = self.player_kills.get(pcid, 0)
                    players_data.append(p)
                packet = {
                    'type': msg_type,
                    'players': players_data,
                }
                if self.game_started:
                    # Serialize Enemy objects to dictionaries
                    enemies_data = []
                    for eid, enemy in self.enemies.items():
                        try:
                            enemies_data.append({
                                'id': eid,
                                'x': float(enemy.pos.x),
                                'y': float(enemy.pos.y),
                                'hp': enemy.health,
                                'max_hp': enemy.max_health
                            })
                        except Exception:
                            pass
                    packet['enemies'] = enemies_data
                    try:
                        packet['leaderboard'] = self.auth.get_leaderboard(10)
                    except Exception:
                        pass

                payload = (json.dumps(packet) + '\n').encode('utf-8')

                for cid in list(self.clients.keys()):
                    try:
                        self.clients[cid]['sock'].sendall(payload)
                    except:
                        self._disconnect(cid)

            # sleep to maintain tick rate
            elapsed = time.time() - t0
            to_sleep = tick_dt - elapsed
            if to_sleep > 0:
                time.sleep(to_sleep)

    def stop(self):
        self._running = False
        self.server_socket.close()