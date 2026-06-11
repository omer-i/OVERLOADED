import pygame
import sys
import os
import random
import time
import winreg
from Player import Player
from Enemy import Enemy
from network_manager import NetworkManager
from lobby import Lobby
from entity_manager import EntityManager
import threading
import ui_theme
from auth import AuthManager
from PIL import Image

class Game:
    def __init__(self):
        pygame.init()

        pygame.display.set_caption("Overloaded")
        _icon_path = os.path.join(os.path.dirname(__file__), "overloaded.ico")
        from PIL import Image
        _pil_img = Image.open(_icon_path).convert("RGBA")
        _icon_surface = pygame.image.fromstring(_pil_img.tobytes(), _pil_img.size, "RGBA")
        pygame.display.set_icon(_icon_surface)

        # DISPLAY SETUP
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.screen_size = self.screen.get_size()
        self.is_fullscreen = True
        self.clock = pygame.time.Clock()
        bg_path = os.path.join(os.path.dirname(__file__), "assets", "Backround", "blue_nebulae_1.png")
        self.space_surface = pygame.image.load(bg_path).convert()

        # Cached fonts to avoid recreating each frame (performance)
        self.font_title = pygame.font.SysFont(None, 48)
        self.font_hud = pygame.font.SysFont(None, 28)
        self.font_small = pygame.font.SysFont(None, 24)
        self.font_small18 = pygame.font.SysFont(None, 18)
        self.font_large = pygame.font.SysFont(None, 72)

        # PLAYER INITIALIZATION
        self.player = Player(
            pos=(self.screen_size[0] // 2, self.screen_size[1] // 2),
            speed=300,
            size=(36, 36),
            color=(50, 200, 50)
        )

        self.show_hitboxes = False  # Debug toggle

        # WORLD SETUP (game world is larger than viewport for scrolling effect)
        self.world_dimensions = (self.screen_size[0] * 1.3, self.screen_size[1] * 1.5)
        self.world_bounds = pygame.Rect(0, 0, self.world_dimensions[0], self.world_dimensions[1])

        # WALLS (border walls around world edges)
        wall_thickness = 20
        world_width, world_height = self.world_dimensions
        self.walls = [
            pygame.Rect(0, 0, world_width, wall_thickness),  # top wall
            pygame.Rect(0, world_height - wall_thickness, world_width, wall_thickness),  # bottom wall
            pygame.Rect(0, 0, wall_thickness, world_height),  # left wall
            pygame.Rect(world_width - wall_thickness, 0, wall_thickness, world_height),  # right wall
            pygame.Rect(1800, 500, 100, 300),
        ]

        self.entitymanager = EntityManager(self)

        # COMBAT SYSTEM
        self.shoot_cooldown_max = 0.6  # Cooldown between shots in seconds
        self.shoot_cooldown_timer = 0.0  # Current cooldown countdown
        self.beam_damage = 60  # Damage dealt per beam hit

        # SPAWNING SYSTEM
        self.base_spawn_interval = 2.0  # Base time between enemy spawns
        # world uses this value at initialization

        # NETWORKING
        # network helper
        self.network = NetworkManager(self)
        self.lobby = Lobby(self)
        # remote players state + sprite wrappers
        self.remote_players = {}            # id -> {'x','y','health'} (raw state)
        self.remote_player_objs = {}        # id -> {'obj': Player, 'target':(x,y), 'last':ts}

        # network-driven enemies: id -> Enemy instance
        self.net_enemies = {}               # id -> Enemy
        self.net_enemy_targets = {}         # id -> {'target':(x,y), 'last':ts}
        
        # TIME & PROGRESSION
        self.elapsed_gameplay_time = 0.0  # How long player has survived
        self.kills_this_game = 0  # Track kills for this game session
        self.high_score_best = self.load_high_score_from_registry()
        # AUTH
        self.auth = AuthManager()
        self.current_user = None  # username string when logged in
        self.server_leaderboard = []  # leaderboard data received from server in multiplayer
        
        # GAME STATE
        self.current_game_state = 'menu'  # 'menu' or 'playing'

        # SPAWN INITIAL ENEMIES (3 at game start)
        initial_camera_rect = pygame.Rect(
            (self.screen_size[0] // 2 - self.screen_size[0] // 2,
             self.screen_size[1] // 2 - self.screen_size[1] // 2),
            self.screen_size
        )
        for _ in range(3):
            new_enemy = self.entitymanager.spawn_enemy_at_edge(initial_camera_rect, self.world_bounds, 1.0)
            if new_enemy:
                self.entitymanager.enemies_list.append(new_enemy)

    def load_high_score_from_registry(self):
        """Load high score from Windows registry. Returns 0.0 if not found."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Overloaded') as reg_key:
                score_value, _ = winreg.QueryValueEx(reg_key, 'HighScore')
                return float(score_value)
        except (FileNotFoundError, OSError, ValueError):
            return 0.0

    def save_high_score_to_registry(self):
        """Save current high score to Windows registry."""
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Overloaded') as reg_key:
                winreg.SetValueEx(reg_key, 'HighScore', 0, winreg.REG_SZ, str(self.high_score_best))
        except OSError:
            pass

    def spawn_enemy_at_edge(self, viewport_rect, world_rect, difficulty_multiplier=1.0):

        spawn_margin = 280  # Distance off-screen where enemies spawn
        valid_spawn_positions = []
        
        viewport_left = viewport_rect.left
        viewport_top = viewport_rect.top
        viewport_right = viewport_rect.right
        viewport_bottom = viewport_rect.bottom

        # TOP EDGE SPAWN POINT
        spawn_x = random.randint(viewport_left, viewport_right)
        spawn_y = viewport_top - spawn_margin
        if world_rect.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))

        # RIGHT EDGE SPAWN POINT
        spawn_x = viewport_right + spawn_margin
        spawn_y = random.randint(viewport_top, viewport_bottom)
        if world_rect.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))

        # BOTTOM EDGE SPAWN POINT
        spawn_x = random.randint(viewport_left, viewport_right)
        spawn_y = viewport_bottom + spawn_margin
        if world_rect.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))

        # LEFT EDGE SPAWN POINT
        spawn_x = viewport_left - spawn_margin
        spawn_y = random.randint(viewport_top, viewport_bottom)
        if world_rect.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))

        # Return None if no valid spawn position found
        if not valid_spawn_positions:
            return None

        # Randomly select one of the valid spawn positions
        final_spawn_x, final_spawn_y = random.choice(valid_spawn_positions)
        
        # Create enemy with random speed scaled by difficulty
        enemy_base_speed = random.randint(60, 120)
        scaled_speed = int(enemy_base_speed * difficulty_multiplier)
        scaled_health = int(30 * (difficulty_multiplier**1.2))  # Health scales faster than speed for more challenge
        
        return Enemy(
            pos=(final_spawn_x, final_spawn_y),
            patrol_points=[(final_spawn_x, final_spawn_y)],
            speed=scaled_speed,
            hp=scaled_health
        )


    # ============================================================================
    # COLLISION & PHYSICS METHODS
    # ============================================================================
    
    def clip_beam_to_walls(self, beam_origin, beam_end, walls_list):

        nearest_collision_point = None
        min_distance_squared = None
        
        origin_x = beam_origin.x
        origin_y = beam_origin.y
        
        for wall_rect in walls_list:
            try:
                # Get line segment clipped to wall
                clipped_segment = wall_rect.clipline(
                    (round(origin_x), round(origin_y)),
                    (round(beam_end.x), round(beam_end.y))
                )
            except Exception:
                clipped_segment = None
            
            if clipped_segment:
                # Segment has two points; pick the one closest to origin
                point1, point2 = clipped_segment
                distance1_sq = (point1[0] - origin_x) ** 2 + (point1[1] - origin_y) ** 2
                distance2_sq = (point2[0] - origin_x) ** 2 + (point2[1] - origin_y) ** 2
                closest_point = point1 if distance1_sq < distance2_sq else point2
                
                # Update nearest if this is closer
                if min_distance_squared is None or distance1_sq < min_distance_squared:
                    nearest_collision_point = pygame.Vector2(closest_point)
                    min_distance_squared = distance1_sq

        return nearest_collision_point if nearest_collision_point is not None else beam_end

    def resolve_entity_wall_collision(self, entity, walls_list):
        for wall_rect in walls_list:
            if entity.rect.colliderect(wall_rect):
                x_overlap = min(entity.rect.right - wall_rect.left, wall_rect.right - entity.rect.left)
                y_overlap = min(entity.rect.bottom - wall_rect.top, wall_rect.bottom - entity.rect.top)
                
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
                
                # THE FIX: Sync the player's internal rect/hitbox logic 
                # instead of forcing topleft = pos.
                if hasattr(entity, 'update_rects'): # Best to add this helper to Player
                    entity.update_rects()
                else:
                    # Fallback: keep the rect centered on the new pos
                    entity.rect.center = (round(entity.pos.x), round(entity.pos.y) + 20)


    # ============================================================================
    # GAME LOOP HELPER METHODS
    # ============================================================================

    def handle_player_movement_and_collisions(self, dt):
        """GAME LOGIC: Update player movement and resolve wall collisions."""
        # Player reads input and updates position
        player_input_keys = pygame.key.get_pressed()
        self.player.handle_input(player_input_keys)
        self.player.update(dt)

        # Clamp player inside world bounds
        world_left = self.world_bounds.left
        world_right = self.world_bounds.right
        world_top = self.world_bounds.top
        world_bottom = self.world_bounds.bottom
        
        half_width = self.player.rect.width / 2
        half_height = self.player.rect.height / 2

        clamped_x = max(world_left + half_width,
                        min(self.player.pos.x, world_right - half_width))

        clamped_y = max(world_top + half_height,
                        min(self.player.pos.y, world_bottom - half_height))

        
        self.player.pos.x = clamped_x
        self.player.pos.y = clamped_y
        self.player.rect.center = (round(self.player.pos.x), round(self.player.pos.y) + 50)

        # Resolve wall collisions
        self.resolve_entity_wall_collision(self.player, self.walls)


    def calculate_camera_offset(self):
        screen_width, screen_height = self.screen_size

        # pos is already the center of the player
        camera_x = round(self.player.pos.x - screen_width / 2)
        camera_y = round(self.player.pos.y - screen_height / 2)

        camera_x = max(self.world_bounds.left, min(camera_x, self.world_bounds.right - screen_width))
        camera_y = max(self.world_bounds.top, min(camera_y, self.world_bounds.bottom - screen_height))

        return pygame.Vector2(camera_x, camera_y)


    def update_elapsed_time_and_difficulty(self, dt):
        self.elapsed_gameplay_time += dt

        # Speed scales from 1.0x to 3.0x over time
        speed_multiplier = min(3.0, 1.0 + self.elapsed_gameplay_time * 0.005)
        
        # Spawn rate increases from base interval down to 0.3 seconds minimum
        current_spawn_interval = max(
            0.3,
            self.base_spawn_interval * max(0.2, 1.0 - self.elapsed_gameplay_time * 0.003)
        )
        
        # propagate spawn interval to world
        try:
            self.entitymanager.spawn_interval_current = current_spawn_interval
        except Exception:
            pass
        return speed_multiplier, current_spawn_interval

    def handle_enemy_spawning(self, dt, camera_rect, difficulty_multiplier):
        """GAME LOGIC: Spawn new enemies over time."""
        self.entitymanager.handle_enemy_spawning(dt, camera_rect, difficulty_multiplier)

    def handle_player_shooting(self, dt, camera_offset):
        """GAME LOGIC: Handle player shooting beam attacks."""
        self.shoot_cooldown_timer -= dt
        mouse_buttons = pygame.mouse.get_pressed()
        if mouse_buttons[0] and self.shoot_cooldown_timer <= 0:
            # Player clicked to shoot
            mouse_screen_position = pygame.mouse.get_pos()

            # Convert screen position to world position
            beam_origin = pygame.Vector2(self.player.rect.center)
            mouse_world_position = pygame.Vector2(mouse_screen_position) + camera_offset

            # Calculate beam direction
            direction_vector = mouse_world_position - beam_origin
            if direction_vector.length_squared() == 0:
                direction_vector = pygame.Vector2(0, -1)
            else:
                direction_vector = direction_vector.normalize()

            # Calculate beam end point
            max_beam_range = max(self.screen_size) * 2
            beam_end_before_walls = beam_origin + direction_vector * max_beam_range

            # Clip beam to walls (stops at first wall)
            beam_end_clipped = self.clip_beam_to_walls(
                beam_origin,
                beam_end_before_walls,
                self.walls
            )

            # Damage all local enemies the beam hits
            for enemy in list(self.entitymanager.enemies_list):
                try:
                    collision_rect = enemy.get_collision_rect()
                    if collision_rect.clipline(
                        (round(beam_origin.x), round(beam_origin.y)),
                        (round(beam_end_clipped.x), round(beam_end_clipped.y))
                    ):
                        enemy.take_damage(self.beam_damage)
                        if not enemy.is_alive():
                            try:
                                self.entitymanager.enemies_list.remove(enemy)
                                # Increment kill counter for this game session
                                self.kills_this_game += 1
                            except ValueError:
                                pass
                except Exception:
                    pass

            # Damage networked enemies locally (client-side prediction of hit)
            # If connected, send authoritative shoot event to server
            if self.network.is_connected and self.network.client:
                try:
                    self.network.client.send_shoot(beam_origin.x, beam_origin.y, beam_end_clipped.x, beam_end_clipped.y)
                except Exception:
                    pass

            # Add beam visualization
            self.entitymanager.active_beams.append({
                "start": beam_origin,
                "end": beam_end_clipped,
                "time_to_live": 0.12,
                "color": (180, 220, 255)
            })

            self.shoot_cooldown_timer = self.shoot_cooldown_max

        # If connected, send input updates to server (position + health)
        if self.network.is_connected and self.network.client:
            try:
                self.network.client.send_input(self.player.pos.x, self.player.pos.y, self.player.health)
            except Exception:
                pass

    def update_enemies(self, dt, difficulty_multiplier):
        """GAME LOGIC: Update all enemies - movement, animation, collisions."""
        self.entitymanager.update_enemies(dt, difficulty_multiplier)

    def resolve_enemy_collisions(self):
        """GAME LOGIC: Prevent enemies from overlapping by pushing them apart."""
        self.entitymanager.resolve_enemy_collisions()

    def handle_enemy_player_damage(self):
        """GAME LOGIC: Check for enemy-player collisions and apply damage."""
        self.entitymanager.handle_enemy_player_damage()

    def update_beam_timers(self, dt):
        """GAME LOGIC: Decrease beam TTL and remove expired beams."""
        self.entitymanager.update_beam_timers(dt)

    def check_game_over_condition(self):
        """GAME LOGIC: Check if player died and return true if so."""
        if not self.player.is_alive():
            return True
        return False

    def show_game_over_screen(self):
        """RENDERING & LOGIC: Display game over screen and update high score."""
        # Update high score if this run was best
        if self.elapsed_gameplay_time > self.high_score_best:
            self.high_score_best = self.elapsed_gameplay_time
            self.save_high_score_to_registry()

        # Display game over screen
        game_over_text = self.font_large.render("GAME OVER", True, (220, 60, 60))
        screen_center_x = self.screen_size[0] // 2 - game_over_text.get_width() // 2
        screen_center_y = self.screen_size[1] // 2 - game_over_text.get_height() // 2
        self.screen.blit(game_over_text, (screen_center_x, screen_center_y))
        pygame.display.flip()
        pygame.time.delay(1500)

    def render_game_frame(self, camera_offset):
        """RENDERING: Draw all game elements (background, entities, HUD) to screen."""


        # Fill background
        self.screen.blit(self.space_surface,(0, 0))


        # ==========================
        # DEBUG: DRAW HITBOXES
        # ==========================
        if self.show_hitboxes:
            # --- Player full rect ---
            player_hitbox_screen = self.player.rect.move(-camera_offset.x, -camera_offset.y)
            pygame.draw.rect(self.screen, (0, 255, 0), player_hitbox_screen, 2)

            # --- Player center damage hitbox ---
            player_center_hitbox = pygame.Rect(
                self.player.rect.centerx - 4,
                self.player.rect.centery - 4,
                8,
                8
            )
            player_center_hitbox_screen = player_center_hitbox.move(-camera_offset.x, -camera_offset.y)
            pygame.draw.rect(self.screen, (255, 255, 0), player_center_hitbox_screen, 2)

            # --- Enemy rects ---
            for enemy in self.entitymanager.enemies_list:
                enemy_rect_screen = enemy.rect.move(-camera_offset.x, -camera_offset.y)
                pygame.draw.rect(self.screen, (0, 255, 0), enemy_rect_screen, 2)

                # Smaller beam collision rect
                small_rect = enemy.get_collision_rect()
                small_rect_screen = small_rect.move(-camera_offset.x, -camera_offset.y)
                pygame.draw.rect(self.screen, (0, 200, 255), small_rect_screen, 2)

        
        # RENDERING: Draw walls translated by camera
        for wall in self.walls:
            wall_screen_position = wall.move(-camera_offset.x, -camera_offset.y)
            pygame.draw.rect(self.screen, (80, 80, 90), wall_screen_position)
        screen_rect = self.player.rect.move(-camera_offset.x, -camera_offset.y)
        draw_pos =(screen_rect.centerx, screen_rect.centery - 30)

        # RENDERING: Draw player sprite
        player_draw_rect = self.player.image.get_rect(center=draw_pos)


        # 3. Draw the image
        self.screen.blit(self.player.image, player_draw_rect)


        # RENDERING: Draw enemies
        if self.network.is_connected:
            # draw enemies coming from server
            for eid, enemy in self.net_enemies.items():
                try:
                    enemy_screen_position = enemy.render_rect.move(-camera_offset.x, -camera_offset.y)
                    self.screen.blit(enemy.image, enemy_screen_position)
                except Exception:
                    pass
        else:
            for enemy in self.entitymanager.enemies_list:
                enemy_screen_position = enemy.render_rect.move(-camera_offset.x, -camera_offset.y)
                self.screen.blit(enemy.image, enemy_screen_position)

        # RENDERING: Draw remote players when connected
        if self.network.is_connected:
            # draw remote Player sprite objects (interpolated)
            for pid, wrapper in self.remote_player_objs.items():
                try:
                    p_obj = wrapper.get('obj')
                    if not p_obj:
                        continue
                    # ensure rects up-to-date without running full update (cheaper)
                    try:
                        if hasattr(p_obj, 'update_rect_positions'):
                            p_obj.update_rect_positions()
                        else:
                            p_obj.rect.center = (round(p_obj.pos.x), round(p_obj.pos.y))
                    except Exception:
                        pass
                    draw_rect = p_obj.image.get_rect(center=(round(p_obj.pos.x - camera_offset.x), round(p_obj.pos.y - camera_offset.y)))
                    self.screen.blit(p_obj.image, draw_rect)
                    # health label and username from remote_players raw state
                    pdata = self.remote_players.get(pid)
                    if pdata:
                        health = pdata.get('health', 0)
                        username = pdata.get('username')
                        # Use fallback if username is None or empty
                        if not username:
                            username = f'Player {pid}'
                        htxt = self.font_small18.render(f'{username} HP:{health}', True, ui_theme.TEXT)
                        self.screen.blit(htxt, (draw_rect.centerx - htxt.get_width()//2, draw_rect.top - 18))
                except Exception:
                    pass

        # RENDERING: Draw beams with glow effect (bright outer layer + core)
        for beam in self.entitymanager.active_beams:
            beam_start_screen = (
                round(beam["start"].x - camera_offset.x),
                round(beam["start"].y - camera_offset.y)
            )
            beam_end_screen = (
                round(beam["end"].x - camera_offset.x),
                round(beam["end"].y - camera_offset.y)
            )
            pygame.draw.line(self.screen, (80, 120, 180), beam_start_screen, beam_end_screen, 12)
            pygame.draw.line(self.screen, beam["color"], beam_start_screen, beam_end_screen, 4)

        # RENDERING: Draw HUD (elapsed time, health, enemy count)
        hud_font = self.font_hud
        
        # Elapsed time display (MM:SS format)
        minutes = int(self.elapsed_gameplay_time) // 60
        seconds = int(self.elapsed_gameplay_time) % 60
        timer_text = hud_font.render(f"{minutes:02d}:{seconds:02d}", True, ui_theme.ACCENT)
        timer_screen_x = self.screen_size[0] // 2 - timer_text.get_width() // 2
        self.screen.blit(timer_text, (timer_screen_x, 10))
        
        # Health display with username
        health_label = f"HP: {self.player.health}/{self.player.max_health}"
        if self.current_user:
            health_label = f"{self.current_user} - {health_label}"
        health_text = hud_font.render(health_label, True, ui_theme.TEXT)
        self.screen.blit(health_text, (10, 10))
        
        # Enemy count display (show authoritative count when connected)
        enemy_count = len(self.net_enemies) if self.network.is_connected else len(self.entitymanager.enemies_list)
        enemy_count_text = hud_font.render(
            f"Enemies: {enemy_count}",
            True,
            ui_theme.MUTED
        )
        self.screen.blit(enemy_count_text, (10, 36))
        
        # Kills display (this game session)
        kills_text = hud_font.render(
            f"Kills: {self.kills_this_game}",
            True,
            ui_theme.TEXT
        )
        self.screen.blit(kills_text, (10, 62))

        pygame.display.flip()

    def reset_game(self):
        """GAME LOGIC: Reset all gameplay state for a fresh game."""
        # Reset world entities
        self.entitymanager.reset()
        
        # Reset combat timers
        self.shoot_cooldown_timer = 0.0
        self.spawn_timer = 0.0
        
        # Reset progression timer
        self.elapsed_gameplay_time = 0.0
        self.kills_this_game = 0  # Reset kill counter for new game
        
        # Reset player to center of world with full health
        player_start_x = self.screen_size[0] // 2
        player_start_y = self.screen_size[1] // 2
        self.player.pos = pygame.Vector2(player_start_x, player_start_y)
        self.player.rect.center = (round(self.player.pos.x), round(self.player.pos.y))
        self.player.health = self.player.max_health
        self.player.invuln_timer = 0.0
        
        # Spawn initial enemies
        initial_camera_rect = pygame.Rect(
            (self.screen_size[0] // 2 - self.screen_size[0] // 2,
             self.screen_size[1] // 2 - self.screen_size[1] // 2),
            self.screen_size
        )
        for _ in range(3):
            new_enemy = self.entitymanager.spawn_enemy_at_edge(
                initial_camera_rect,
                self.world_bounds,
                1.0
            )
            if new_enemy:
                if not self.network.is_connected:
                    self.entitymanager.enemies_list.append(new_enemy)

    def run(self):
        """MAIN GAME LOOP: Handle menu/game state and coordinate all game systems."""
        running = True
        
        while running:
            try:
                # ===== MENU STATE =====
                if self.current_game_state == 'menu':
                    menu_choice = self.menu_loop()

                    if menu_choice == 'single player':
                        # single-player
                        try:
                            self.network.stop_network()
                        except Exception:
                            pass
                        self.reset_game()
                        self.current_game_state = 'playing'

                    elif menu_choice == 'create room':
                        # start server, join local client, then go to host-wait screen
                        try:
                            self.network.start_host(username=self.current_user)
                            import time as _t
                            _t.sleep(0.15)
                            joined_ok = self.network.join_server('localhost')
                            if not joined_ok:
                                try:
                                    self.network.stop_network()
                                except Exception:
                                    pass
                                continue

                            # enter waiting state and show host wait screen
                            self.current_game_state = 'waiting'
                            started = False
                            try:
                                started = self.lobby.wait_screen(is_host=True)
                            except Exception:
                                started = False

                            if started:
                                # server has started the game and broadcast state
                                self.reset_game()
                                self.current_game_state = 'playing'
                            else:
                                # host cancelled or disconnected
                                try:
                                    self.network.stop_network()
                                except Exception:
                                    pass
                                self.current_game_state = 'menu'

                        except Exception:
                            try:
                                self.network.stop_network()
                            except Exception:
                                pass
                            self.current_game_state = 'menu'

                    elif menu_choice == 'join room':
                        # Show server discovery screen
                        selected_server = self.show_server_discovery_screen()
                        
                        if selected_server:
                            # Try to join the selected server
                            if self.network.join_server(selected_server['ip'], selected_server['port']):
                                # enter waiting state and show client wait screen
                                self.current_game_state = 'waiting'
                                started = False
                                try:
                                    started = self.lobby.wait_screen(is_host=False)
                                except Exception:
                                    started = False

                                if started:
                                    self.reset_game()
                                    self.current_game_state = 'playing'
                                else:
                                    # cancelled or disconnected
                                    try:
                                        self.network.stop_network()
                                    except Exception:
                                        pass
                                    self.current_game_state = 'menu'

                            else:
                                # failed to connect
                                self.current_game_state = 'menu'
                        else:
                            # user cancelled discovery
                            self.current_game_state = 'menu'

                    elif menu_choice == 'leave':
                        # client leave server
                        try:
                            self.network.stop_network()
                        except Exception:
                            pass
                        self.current_game_state = 'menu'
                        continue

                    elif menu_choice == 'stop host':
                        # stop hosting and disconnect
                        try:
                            self.network.stop_network()
                        except Exception:
                            pass
                        self.current_game_state = 'menu'
                        continue

                    elif menu_choice == 'quit' or menu_choice is None:
                        running = False
                        continue
            except Exception as e:
                # Catch unexpected errors per-frame to avoid crashing the whole app
                print(f"Game loop caught exception: {e}")
                # small sleep to avoid busy-loop if persistent error
                pygame.time.delay(100)
                continue

            # ===== PLAYING STATE =====
            if self.current_game_state == 'playing':
                dt = self.clock.tick(60) / 1000.0
                
                # GAME LOGIC: Handle input events (ESC to menu, window close)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_h:
                            self.show_hitboxes = not self.show_hitboxes


                        if event.key == pygame.K_ESCAPE:
                            self.current_game_state = 'menu'
                            # Stop network and disconnect from game
                            try:
                                if self.network.is_connected:
                                    self.network.stop_network()
                            except Exception:
                                pass
                            break
                
                # GAME LOGIC: Update player and resolve world collisions
                self.handle_player_movement_and_collisions(dt)
                
                # GAME LOGIC: Calculate viewport center on player
                camera_viewport_rect = pygame.Rect(
                    0, 0,
                    self.screen_size[0],
                    self.screen_size[1]
                )
                camera_offset = self.calculate_camera_offset()
                camera_viewport_rect.topleft = (camera_offset.x, camera_offset.y)
                
                # GAME LOGIC: Update difficulty and get multipliers
                speed_multiplier, self.spawn_interval_current = self.update_elapsed_time_and_difficulty(dt)
                
                # GAME LOGIC: Spawn new enemies over time
                self.handle_enemy_spawning(dt, camera_viewport_rect, speed_multiplier)
                
                # GAME LOGIC: Handle player shooting
                self.handle_player_shooting(dt, camera_offset)
                
                # GAME LOGIC: Update all enemies
                self.update_enemies(dt, speed_multiplier)
                
                # GAME LOGIC: Check for enemy-player collisions and apply damage
                self.handle_enemy_player_damage()
                
                # GAME LOGIC: Update beam timers and remove expired beams
                self.update_beam_timers(dt)

                # NETWORK: If connected as client, poll latest server state and apply
                if self.network.is_connected and self.network.client:
                    try:
                        state = self.network.client.get_latest_state()
                        if state:
                            self.apply_network_state(state)
                    except Exception:
                        pass

                # NETWORK: update interpolation/smoothing for remote entities
                if self.network.is_connected:
                    try:
                        self.update_network_interpolation(dt)
                    except Exception:
                        pass
                
                # GAME LOGIC: Check if player died
                if self.check_game_over_condition():
                    self.show_game_over_screen()
                    # Submit final kill count for this game session
                    if self.current_user:
                        try:
                            self.auth.record_game_kills(self.current_user, self.kills_this_game)
                        except Exception as e:
                            print(f"Error recording game kills: {e}")
                    self.current_game_state = 'menu'
                    # Stop network when game ends
                    try:
                        if self.network.is_connected:
                            self.network.stop_network()
                    except Exception:
                        pass
                    continue

                self.resolve_enemy_collisions()
                
                # RENDERING: Draw entire game frame
                self.render_game_frame(camera_offset)
            else:
                # Not in playing state, just tick the clock and handle quit events
                self.clock.tick(30)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False

        # Cleanup on exit
        self.save_high_score_to_registry()
        pygame.quit()
        sys.exit()

    def menu_loop(self):
        selected_option_index = 0
        # If no user logged in, show account menu first (login/register/continue as guest)
        if not self.current_user:
            while True:
                try:
                    res = self.account_menu()
                except Exception:
                    res = None
                # If user logged in or chose to continue as guest, break out
                if res in ('logged_in', 'continue_guest'):
                    break
                # If they cancelled (pressed Escape), just proceed to main menu
                if res is None:
                    break
        # build dynamic menu based on networking state
        if self.network.is_connected:
            # if hosting, allow stopping host; always allow leaving
            if self.network.is_hosting:
                menu_options = ['Start', 'Leave', 'Stop Host', 'Account', 'Quit']
            else:
                menu_options = ['Start', 'Leave', 'Account', 'Quit']
        else:
            menu_options = ['Single Player', 'Create Room', 'Join Room', 'Account', 'Quit']
        title_font = self.font_title
        hud_font = self.font_hud

        while True:
            dt = self.clock.tick(30) / 1000.0

            # RENDERING: Draw menu background and title (themed)
            self.screen.fill(ui_theme.BG)
            title_text = self.font_title.render('OVERLOADED', True, ui_theme.ACCENT)
            title_rect = title_text.get_rect()
            title_rect.topleft = (
                self.screen_size[0] // 2 - title_text.get_width() // 2,
                120
            )
            self.screen.blit(title_text, title_rect)

            # RENDERING: Draw menu options
            option_rects = []
            for option_index, option_text in enumerate(menu_options):
                # Highlight selected option using theme
                is_selected = option_index == selected_option_index
                option_color = ui_theme.HIGHLIGHT if is_selected else ui_theme.MUTED
                
                rendered_option = self.font_title.render(option_text, True, option_color)
                option_rect = rendered_option.get_rect()
                option_rect.topleft = (
                    self.screen_size[0] // 2 - rendered_option.get_width() // 2,
                    260 + option_index * 64
                )
                option_rects.append(option_rect)
                pygame.draw.rect(self.screen, 'black', option_rect)
                pygame.draw.rect(self.screen, 'black', option_rect, 10)
                self.screen.blit(rendered_option, option_rect)
                # show small helper text for Host/Join
                if option_text.lower() == 'host':
                    helper = self.font_hud.render('Host local server and join', True, ui_theme.MUTED)
                    self.screen.blit(helper, (option_rect.right + 8, option_rect.top))
                if option_text.lower() == 'join':
                    helper = self.font_hud.render('Connect to a server IP', True, ui_theme.MUTED)
                    self.screen.blit(helper, (option_rect.right + 8, option_rect.top))

            # RENDERING: Draw high score display
            high_score_minutes = int(self.high_score_best) // 60
            high_score_seconds = int(self.high_score_best) % 60
            high_score_text = self.font_hud.render(
                f'Best: {high_score_minutes:02d}:{high_score_seconds:02d}',
                True,
                ui_theme.TEXT
            )
            high_score_rect = high_score_text.get_rect()
            high_score_rect.topleft = (
                self.screen_size[0] // 2 - high_score_text.get_width() // 2,
                185
            )
            self.screen.blit(high_score_text, high_score_rect)
            
            # RENDERING: Draw username in top left if logged in
            if self.current_user:
                user_text = self.font_small18.render(f'User: {self.current_user}', True, ui_theme.TEXT)
                self.screen.blit(user_text, (10, 10))
            
            # RENDERING: Draw leaderboard in bottom right
            leaderboard_x = self.screen_size[0] - 300
            leaderboard_y = self.screen_size[1] - 270
            self.render_leaderboard(self.screen, leaderboard_x, leaderboard_y)

            # GAME LOGIC: Check for mouse hover to update selection
            mouse_position = pygame.mouse.get_pos()
            for option_index, option_rect in enumerate(option_rects):
                if option_rect.collidepoint(mouse_position):
                    selected_option_index = option_index
                    break

            # GAME LOGIC: Handle input events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return 'quit'
                    
                    if event.key == pygame.K_UP:
                        selected_option_index = (selected_option_index - 1) % len(menu_options)
                    
                    if event.key == pygame.K_DOWN:
                        selected_option_index = (selected_option_index + 1) % len(menu_options)
                    
                    if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        # map index to current menu option
                        choice = menu_options[selected_option_index].lower()
                        # handle Account submenu synchronously
                        if choice == 'account':
                            res = self.account_menu()
                            # account_menu returns None to continue showing menu
                            if res == 'logged_in':
                                # keep in menu and let user choose next
                                pass
                            continue
                        return choice
                    
                
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left mouse button
                        for option_index, option_rect in enumerate(option_rects):
                            if option_rect.collidepoint(event.pos):
                                return menu_options[option_index].lower()

            pygame.display.flip()

    def _login_flow(self):
        while True:
            uname = self.prompt_text_input('Username:')
            if not uname:
                return False
            pwd = self.prompt_password_input('Password:')
            if not pwd:
                return False
            if self.network.is_connected and self.network.client:
                ok = self.network.client.send_auth(uname, pwd)
            else:
                ok = self.auth.authenticate(uname, pwd)
            print(f"Auth attempt for '{uname}': {ok}")
            if ok:
                self.current_user = uname
                try:
                    self.auth.set_last_user(uname)
                except Exception:
                    pass
                self.show_message('Login successful')
                return True
            else:
                self.show_message('Login failed - please try again')
                # Loop continues, user tries again

    def _register_flow(self):
        while True:
            uname = self.prompt_text_input('Choose username:')
            if not uname:
                return False
            pwd = self.prompt_password_input('Choose password:')
            if not pwd:
                return False
            if self.network.is_connected and self.network.client:
                ok, msg = self.network.client.send_register(uname, pwd)
            else:
                ok, msg = self.auth.register(uname, pwd)
            print(f"Register attempt for '{uname}': {ok} - {msg}")
            if ok:
                self.show_message('Registered successfully')
                self.current_user = uname
                try:
                    self.auth.set_last_user(uname)
                except Exception:
                    pass
                return True
            else:
                self.show_message(msg + ' - please try again')
                # Loop continues, user tries again


    # -----------------
    # NETWORK HELPERS
    # -----------------
    def start_host(self, host='localhost', port=12345):
        return self.network.start_host(host=host, port=port)

    def join_server(self, host='localhost', port=12345):
        return self.network.join_server(host=host, port=port)

    def host_wait_screen(self):
        """UI for host to wait for players to join and start the game.

        Returns True if host pressed Start, False if cancelled.
        """
        return self.lobby.host_wait_screen()

    def client_wait_screen(self):
        return self.lobby.client_wait_screen()

    def stop_network(self):
        return self.network.stop_network()

    def apply_network_state(self, state):
        """Apply authoritative server state (players and enemies).

        State format expected: {'type':'state','players':[...],'enemies':[...]}.
        """
        if not isinstance(state, dict):
            return

        # Update remote players (store raw state and set interpolation targets)
        players = state.get('players', [])
        stype = state.get('type')
        # Only create visual remote Player objects when server is in active 'state'
        if stype != 'state':
            # update raw lobby players but don't spawn in-world sprites
            new_remote = {}
            for p in players:
                pid = p.get('id')
                if pid is None:
                    continue
                pusername = p.get('username')
                # Use fallback if username is None or empty
                if not pusername:
                    pusername = f'Player {pid}'
                new_remote[pid] = {'x': float(p.get('x',0.0)), 'y': float(p.get('y',0.0)), 'health': int(p.get('health',0)), 'username': pusername}
            self.remote_players = new_remote
            return
        new_remote = {}
        now = time.time()
        seen_players = set()
        if 'leaderboard' in state:
            self.server_leaderboard = state['leaderboard']

        for p in players:
            pid = p.get('id')
            if pid is None:
                continue
            # skip local player's own id if server assigned one, but read kills first
            if self.network.client and pid == getattr(self.network.client, 'client_id', None):
                server_kills = p.get('kills')
                if server_kills is not None:
                    self.kills_this_game = server_kills
                continue
            seen_players.add(pid)
            rx = float(p.get('x', 0.0))
            ry = float(p.get('y', 0.0))
            rh = int(p.get('health', 0))
            rusername = p.get('username')
            # Use fallback if username is None or empty
            if not rusername:
                rusername = f'Player {pid}'
            new_remote[pid] = {'x': rx, 'y': ry, 'health': rh, 'username': rusername}

            # ensure we have a Player object for this remote id
            if pid in self.remote_player_objs:
                wrapper = self.remote_player_objs[pid]
                # set target to new position
                wrapper['target'] = (rx, ry)
                wrapper['last'] = now
            else:
                try:
                    # create a Player sprite for remote player (no input)
                    p_obj = Player(pos=(rx, ry), speed=0)
                    p_obj.pos = pygame.Vector2(rx, ry)
                    p_obj.rect.center = (round(rx), round(ry))
                    wrapper = {'obj': p_obj, 'target': (rx, ry), 'last': now}
                    self.remote_player_objs[pid] = wrapper
                except Exception:
                    pass

        self.remote_players = new_remote
        
        # Remove players that are no longer in the server state
        for pid in list(self.remote_player_objs.keys()):
            if pid not in seen_players:
                try:
                    del self.remote_player_objs[pid]
                except KeyError:
                    pass

        # Update enemies
        enemies = state.get('enemies', [])
        # create/update enemy instances in self.net_enemies
        seen = set()
        for e in enemies:
            eid = e.get('id')
            if eid is None:
                continue
            seen.add(eid)
            ex = float(e.get('x', 0.0))
            ey = float(e.get('y', 0.0))
            ehp = int(e.get('hp', 0))
            if eid in self.net_enemies:
                # set interpolation target for enemy
                self.net_enemy_targets[eid] = {'target': (ex, ey), 'last': now}
                # update hp immediately
                try:
                    self.net_enemies[eid].health = ehp
                except Exception:
                    pass
            else:
                # create enemy instance and set target
                try:
                    new_e = Enemy(pos=(ex, ey), patrol_points=[(ex, ey)], speed=60, hp=ehp)
                    self.net_enemies[eid] = new_e
                    self.net_enemy_targets[eid] = {'target': (ex, ey), 'last': now}
                except Exception:
                    pass

        # remove enemies that are no longer present
        for eid in list(self.net_enemies.keys()):
            if eid not in seen:
                try:
                    del self.net_enemies[eid]
                except Exception:
                    pass



    def prompt_text_input(self, prompt_text):
        """Centered single-line text input with boxed UI."""
        input_str = ''
        active = True
        # choose fonts: large prompt and medium input
        prompt_font = self.font_title
        input_font = self.font_hud
        caret_visible = True
        caret_timer = 0.0

        panel_w = min(900, self.screen_size[0] - 200)
        panel_h = 160
        panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        panel_rect.center = (self.screen_size[0] // 2, self.screen_size[1] // 2)

        while active:
            dt = self.clock.tick(30) / 1000.0
            caret_timer += dt
            if caret_timer >= 0.5:
                caret_timer = 0.0
                caret_visible = not caret_visible

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return ''
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        active = False
                        break
                    if event.key == pygame.K_BACKSPACE:
                        input_str = input_str[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        return ''
                    else:
                        if event.unicode and len(event.unicode) == 1:
                            input_str += event.unicode

            # draw panel
            self.screen.fill(ui_theme.BG)
            pygame.draw.rect(self.screen, ui_theme.PANEL, panel_rect, border_radius=8)
            # title prompt centered
            title_surf = prompt_font.render(prompt_text, True, ui_theme.TEXT)
            title_rect = title_surf.get_rect(center=(panel_rect.centerx, panel_rect.top + 36))
            self.screen.blit(title_surf, title_rect)

            # input box
            input_box_w = panel_w - 80
            input_box_h = 44
            input_box_rect = pygame.Rect(0, 0, input_box_w, input_box_h)
            input_box_rect.center = (panel_rect.centerx, panel_rect.centery + 18)
            pygame.draw.rect(self.screen, (10, 10, 12), input_box_rect, border_radius=6)
            pygame.draw.rect(self.screen, ui_theme.ACCENT, input_box_rect, 2, border_radius=6)

            # render input text
            display_text = input_str
            # truncate if too long
            while input_font.size(display_text)[0] > input_box_w - 20 and len(display_text) > 0:
                display_text = display_text[1:]

            txt_surf = input_font.render(display_text, True, ui_theme.TEXT)
            txt_rect = txt_surf.get_rect(midleft=(input_box_rect.left + 10, input_box_rect.centery))
            self.screen.blit(txt_surf, txt_rect)

            # caret
            if caret_visible:
                caret_x = txt_rect.right + 3
                caret_y1 = input_box_rect.top + 8
                caret_y2 = input_box_rect.bottom - 8
                pygame.draw.line(self.screen, ui_theme.ACCENT, (caret_x, caret_y1), (caret_x, caret_y2), 2)

            pygame.display.flip()

        return input_str

    def prompt_password_input(self, prompt_text):
        """Masked password input using same boxed UI style."""
        input_str = ''
        active = True
        prompt_font = self.font_title
        input_font = self.font_hud
        caret_visible = True
        caret_timer = 0.0

        panel_w = min(900, self.screen_size[0] - 200)
        panel_h = 160
        panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        panel_rect.center = (self.screen_size[0] // 2, self.screen_size[1] // 2)

        while active:
            dt = self.clock.tick(30) / 1000.0
            caret_timer += dt
            if caret_timer >= 0.5:
                caret_timer = 0.0
                caret_visible = not caret_visible

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return ''
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        active = False
                        break
                    if event.key == pygame.K_BACKSPACE:
                        input_str = input_str[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        return ''
                    else:
                        if event.unicode and len(event.unicode) == 1:
                            input_str += event.unicode

            # draw panel
            self.screen.fill(ui_theme.BG)
            pygame.draw.rect(self.screen, ui_theme.PANEL, panel_rect, border_radius=8)
            # title prompt centered
            title_surf = prompt_font.render(prompt_text, True, ui_theme.TEXT)
            title_rect = title_surf.get_rect(center=(panel_rect.centerx, panel_rect.top + 36))
            self.screen.blit(title_surf, title_rect)

            # input box
            input_box_w = panel_w - 80
            input_box_h = 44
            input_box_rect = pygame.Rect(0, 0, input_box_w, input_box_h)
            input_box_rect.center = (panel_rect.centerx, panel_rect.centery + 18)
            pygame.draw.rect(self.screen, (10, 10, 12), input_box_rect, border_radius=6)
            pygame.draw.rect(self.screen, ui_theme.ACCENT, input_box_rect, 2, border_radius=6)

            # render masked input text
            masked = '*' * len(input_str)
            display_text = masked
            while input_font.size(display_text)[0] > input_box_w - 20 and len(display_text) > 0:
                display_text = display_text[1:]

            txt_surf = input_font.render(display_text, True, ui_theme.TEXT)
            txt_rect = txt_surf.get_rect(midleft=(input_box_rect.left + 10, input_box_rect.centery))
            self.screen.blit(txt_surf, txt_rect)

            # caret
            if caret_visible:
                caret_x = txt_rect.right + 3
                caret_y1 = input_box_rect.top + 8
                caret_y2 = input_box_rect.bottom - 8
                pygame.draw.line(self.screen, ui_theme.ACCENT, (caret_x, caret_y1), (caret_x, caret_y2), 2)

            pygame.display.flip()

        return input_str

    def show_message(self, message):
        """Display a centered message dialog that waits for user to press Enter."""
        active = True
        message_font = self.font_hud

        panel_w = min(700, self.screen_size[0] - 200)
        panel_h = 180
        panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        panel_rect.center = (self.screen_size[0] // 2, self.screen_size[1] // 2)

        while active:
            dt = self.clock.tick(30) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        active = False
                        break
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        active = False
                        break

            # draw panel
            self.screen.fill(ui_theme.BG)
            pygame.draw.rect(self.screen, ui_theme.PANEL, panel_rect, border_radius=8)
            
            # render message text (word wrap if needed)
            message_lines = []
            words = message.split()
            current_line = ''
            for word in words:
                test_line = current_line + (' ' if current_line else '') + word
                if message_font.size(test_line)[0] > panel_w - 60:
                    if current_line:
                        message_lines.append(current_line)
                    current_line = word
                else:
                    current_line = test_line
            if current_line:
                message_lines.append(current_line)

            # render each line centered
            start_y = panel_rect.top + 40
            for i, line in enumerate(message_lines):
                line_surf = message_font.render(line, True, ui_theme.TEXT)
                line_rect = line_surf.get_rect(center=(panel_rect.centerx, start_y + i * 32))
                self.screen.blit(line_surf, line_rect)

            # render prompt text
            prompt_surf = self.font_small18.render('Press Enter or click to continue', True, ui_theme.MUTED)
            prompt_rect = prompt_surf.get_rect(center=(panel_rect.centerx, panel_rect.bottom - 30))
            self.screen.blit(prompt_surf, prompt_rect)

            pygame.display.flip()

    def account_menu(self):
        """Simple account submenu: Login, Register, Logout.

        Supports keyboard and mouse. When not logged in shows
        Login / Register / Continue as Guest.
        """
        # Simple textual menu in center
        options = []
        if self.current_user:
            options = ['Logout', 'Back']
        else:
            options = ['Login', 'Register', 'Continue as Guest']

        selected = 0
        while True:
            dt = self.clock.tick(30) / 1000.0

            # layout
            panel_w = 640
            panel_h = 240
            panel = pygame.Rect(0, 0, panel_w, panel_h)
            panel.center = (self.screen_size[0] // 2, self.screen_size[1] // 2)

            option_rects = [pygame.Rect(panel.left + 48, panel.top + 72 + i * 40, panel_w - 96, 32)
                            for i in range(len(options))]

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    if event.key == pygame.K_UP:
                        selected = (selected - 1) % len(options)
                    if event.key == pygame.K_DOWN:
                        selected = (selected + 1) % len(options)
                    if event.key == pygame.K_RETURN:
                        choice = options[selected].lower()
                        # handle below after event processing
                        handled = False
                if event.type == pygame.MOUSEMOTION:
                    mx, my = event.pos
                    for i, r in enumerate(option_rects):
                        if r.collidepoint(mx, my):
                            selected = i
                            break
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        mx, my = event.pos
                        for i, r in enumerate(option_rects):
                            if r.collidepoint(mx, my):
                                selected = i
                                choice = options[selected].lower()
                                handled = True
                                break

            # if a choice was made via keyboard Enter or mouse click handle it
            if 'choice' in locals():
                ch = choice
                del choice
                if ch == 'back':
                    return None
                if ch == 'logout':
                    self.current_user = None
                    return 'logged_out'
                if ch == 'continue as guest' or ch == 'continue':
                    return 'continue_guest'
                if ch == 'login':
                    if self._login_flow():
                        return 'logged_in'
                    else:
                        continue
                if ch == 'register':
                    if self._register_flow():
                        return 'logged_in'
                    else:
                        continue
            # draw menu panel and options
            self.screen.fill(ui_theme.BG)
            pygame.draw.rect(self.screen, ui_theme.PANEL, panel, border_radius=8)
            title = self.font_title.render('Account', True, ui_theme.ACCENT)
            self.screen.blit(title, (panel.centerx - title.get_width()//2, panel.top + 16))

            # render options with hover/selection
            for i, opt in enumerate(options):
                color = ui_theme.HIGHLIGHT if i == selected else ui_theme.TEXT
                surf = self.font_hud.render(opt, True, color)
                self.screen.blit(surf, (panel.left + 56, panel.top + 72 + i*40))

            # show current user
            if self.current_user:
                cur = self.font_small.render(f'Logged in: {self.current_user}', True, ui_theme.MUTED)
                self.screen.blit(cur, (panel.left + 48, panel.bottom - 40))

            pygame.display.flip()

    def update_network_interpolation(self, dt):
        """Smoothly interpolate remote players and enemies toward latest server targets."""
            # exponential smoothing factor
        SMOOTHING_SPEED = 8.0

        # Remote players
        for pid, wrapper in list(self.remote_player_objs.items()):
            try:
                obj = wrapper['obj']
                tx, ty = wrapper.get('target', (obj.pos.x, obj.pos.y))
                # move displayed pos toward target
                dx = tx - obj.pos.x
                dy = ty - obj.pos.y
                obj.pos.x += dx * min(1.0, SMOOTHING_SPEED * dt)
                obj.pos.y += dy * min(1.0, SMOOTHING_SPEED * dt)
                # update image rects and animation
                try:
                    obj.update(dt)
                except Exception:
                    try:
                        obj.update_rect_positions()
                    except Exception:
                        pass
            except Exception:
                pass

        # Net enemies
        # build list of potential targets for enemy facing/animation (local + remote)
        enemy_targets = [self.player]
        for wrapper in self.remote_player_objs.values():
            if 'obj' in wrapper:
                enemy_targets.append(wrapper['obj'])

        for eid, enemy in list(self.net_enemies.items()):
            try:
                target_info = self.net_enemy_targets.get(eid)
                if not target_info:
                    continue
                tx, ty = target_info.get('target', (enemy.pos.x, enemy.pos.y))
                dx = tx - enemy.pos.x
                dy = ty - enemy.pos.y
                enemy.pos.x += dx * min(1.0, SMOOTHING_SPEED * dt)
                enemy.pos.y += dy * min(1.0, SMOOTHING_SPEED * dt)
                # update render rects
                try:
                    enemy.render_rect = enemy.image.get_rect(center=(round(enemy.pos.x), round(enemy.pos.y)))
                    enemy.rect.center = (enemy.render_rect.centerx, enemy.render_rect.centery + 15)
                except Exception:
                    pass
                # also update animation & facing using enemy.update, passing nearby targets
                try:
                    enemy.update(dt, target=enemy_targets)
                    # enforce facing toward nearest target (fix cases where animation facing isn't updated)
                    # find nearest target x
                    nearest = None
                    min_d2 = None
                    for t in enemy_targets:
                        try:
                            tx2 = t.pos.x if hasattr(t, 'pos') else (t.rect.centerx if hasattr(t, 'rect') else None)
                            ty2 = t.pos.y if hasattr(t, 'pos') else (t.rect.centery if hasattr(t, 'rect') else None)
                            if tx2 is None:
                                continue
                            d2 = (tx2 - enemy.pos.x) ** 2 + (ty2 - enemy.pos.y) ** 2
                            if min_d2 is None or d2 < min_d2:
                                min_d2 = d2
                                nearest = (tx2, ty2)
                        except Exception:
                            continue
                    if nearest is not None:
                        if nearest[0] > enemy.pos.x:
                            enemy.is_facing_right = True
                        else:
                            enemy.is_facing_right = False
                except Exception:
                    pass
            except Exception:
                pass

    def render_leaderboard(self, target_surface, x, y, width=280, height=240):
        """Render top 10 leaderboard in the bottom right corner."""
        try:
            if self.network.is_connected and self.server_leaderboard:
                leaderboard = self.server_leaderboard
            else:
                leaderboard = self.auth.get_leaderboard(10)
            
            # Panel background
            panel_rect = pygame.Rect(x, y, width, height)
            pygame.draw.rect(target_surface, ui_theme.PANEL, panel_rect, border_radius=8)
            pygame.draw.rect(target_surface, ui_theme.ACCENT, panel_rect, 2, border_radius=8)
            
            # Title
            title_surf = self.font_small.render('Top Killers', True, ui_theme.ACCENT)
            title_rect = title_surf.get_rect(center=(panel_rect.centerx, panel_rect.top + 14))
            target_surface.blit(title_surf, title_rect)
            
            # If no leaderboard data, show empty message
            if not leaderboard:
                empty_surf = self.font_small18.render('No kills yet', True, ui_theme.MUTED)
                empty_rect = empty_surf.get_rect(center=(panel_rect.centerx, panel_rect.centery))
                target_surface.blit(empty_surf, empty_rect)
                return
            
            # Leaderboard entries
            start_y = panel_rect.top + 32
            entry_height = 18
            for i, entry in enumerate(leaderboard):
                if i >= 10:
                    break
                
                # Handle both tuple and dict formats
                if isinstance(entry, (list, tuple)):
                    username, kills = entry[0], entry[1]
                else:
                    username, kills = entry.get('username'), entry.get('kills', 0)
                
                # Skip if no username
                if not username:
                    continue
                
                entry_y = start_y + i * entry_height
                if entry_y + entry_height > panel_rect.bottom:
                    break
                
                # Rank + username
                rank_text = f"{i+1}. {username}"
                rank_surf = self.font_small18.render(rank_text, True, ui_theme.TEXT)
                rank_rect = rank_surf.get_rect(topleft=(panel_rect.left + 12, entry_y))
                target_surface.blit(rank_surf, rank_rect)
                
                # Kills count (right aligned)
                kills_text = str(kills)
                kills_surf = self.font_small18.render(kills_text, True, ui_theme.MUTED)
                kills_rect = kills_surf.get_rect(topright=(panel_rect.right - 12, entry_y))
                target_surface.blit(kills_surf, kills_rect)
        except Exception as e:
            print(f"Leaderboard render error: {e}")
            pass

    def show_server_discovery_screen(self):
        """Display available servers and allow player to select one to join.
        
        Returns:
            Selected server dict with 'ip' and 'port' keys, or None if cancelled.
        """
        # First, show a "searching" screen while discovering servers
        searching = True
        discovered_servers = []
        search_thread = None
        
        def discover_in_background():
            nonlocal discovered_servers
            discovered_servers = self.network.discover_available_servers(timeout=3.0)
        
        # Start discovery in background thread
        search_thread = threading.Thread(target=discover_in_background, daemon=True)
        search_thread.start()
        
        # Show searching screen while discovery is happening
        start_time = time.time()
        while searching and time.time() - start_time < 4.0:
            self.clock.tick(30)
            
            self.screen.fill(ui_theme.BG)
            
            # Title
            title_surf = self.font_title.render('Searching for Rooms...', True, ui_theme.ACCENT)
            title_rect = title_surf.get_rect(center=(self.screen_size[0] // 2, 100))
            self.screen.blit(title_surf, title_rect)
            
            # Loading indicator with dots
            dots = '.' * (int(time.time() * 2) % 4)
            loading_surf = self.font_hud.render(f'Searching{dots}', True, ui_theme.TEXT)
            loading_rect = loading_surf.get_rect(center=(self.screen_size[0] // 2, 200))
            self.screen.blit(loading_surf, loading_rect)
            
            # Hint
            hint_surf = self.font_small18.render('(Press ESC to cancel)', True, ui_theme.MUTED)
            hint_rect = hint_surf.get_rect(center=(self.screen_size[0] // 2, 280))
            self.screen.blit(hint_surf, hint_rect)
            
            pygame.display.flip()
            
            # Check for ESC key
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
            
            # If discovery is done, show results
            if not search_thread.is_alive():
                searching = False
        
        # If still searching after timeout, wait a bit more
        search_thread.join(timeout=0.5)
        
        # Show server selection screen
        if not discovered_servers:
            # No servers found - show message with manual IP option
            btn_w, btn_h = 320, 52
            btn_manual = pygame.Rect(0, 0, btn_w, btn_h)
            btn_manual.center = (self.screen_size[0] // 2, self.screen_size[1] // 2 + 20)
            btn_cancel = pygame.Rect(0, 0, btn_w, btn_h)
            btn_cancel.center = (self.screen_size[0] // 2, self.screen_size[1] // 2 + 90)
            selected_btn = 0  # 0 = manual, 1 = cancel

            while True:
                self.clock.tick(30)
                self.screen.fill(ui_theme.BG)

                title_surf = self.font_title.render('No Rooms Found', True, ui_theme.ACCENT)
                title_rect = title_surf.get_rect(center=(self.screen_size[0] // 2, self.screen_size[1] // 2 - 120))
                self.screen.blit(title_surf, title_rect)

                msg_surf = self.font_hud.render('No servers discovered on the network.', True, ui_theme.TEXT)
                msg_rect = msg_surf.get_rect(center=(self.screen_size[0] // 2, self.screen_size[1] // 2 - 60))
                self.screen.blit(msg_surf, msg_rect)

                hint_surf = self.font_small18.render('You can enter the host IP address manually instead.', True, ui_theme.MUTED)
                hint_rect = hint_surf.get_rect(center=(self.screen_size[0] // 2, self.screen_size[1] // 2 - 30))
                self.screen.blit(hint_surf, hint_rect)

                # Manual IP button
                mx, my = pygame.mouse.get_pos()
                hover_manual = btn_manual.collidepoint(mx, my)
                hover_cancel = btn_cancel.collidepoint(mx, my)
                if hover_manual: selected_btn = 0
                if hover_cancel: selected_btn = 1

                pygame.draw.rect(self.screen, ui_theme.HIGHLIGHT if selected_btn == 0 else ui_theme.PANEL, btn_manual, border_radius=8)
                pygame.draw.rect(self.screen, ui_theme.ACCENT, btn_manual, 2, border_radius=8)
                manual_surf = self.font_hud.render('Enter IP Manually', True, ui_theme.BG if selected_btn == 0 else ui_theme.TEXT)
                manual_rect = manual_surf.get_rect(center=btn_manual.center)
                self.screen.blit(manual_surf, manual_rect)

                # Cancel button
                pygame.draw.rect(self.screen, ui_theme.HIGHLIGHT if selected_btn == 1 else ui_theme.PANEL, btn_cancel, border_radius=8)
                pygame.draw.rect(self.screen, ui_theme.ACCENT, btn_cancel, 2, border_radius=8)
                cancel_surf = self.font_hud.render('Cancel', True, ui_theme.BG if selected_btn == 1 else ui_theme.TEXT)
                cancel_rect = cancel_surf.get_rect(center=btn_cancel.center)
                self.screen.blit(cancel_surf, cancel_rect)

                pygame.display.flip()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return None
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            return None
                        if event.key == pygame.K_UP or event.key == pygame.K_DOWN:
                            selected_btn = 1 - selected_btn  # toggle between 0 and 1
                        if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                            if selected_btn == 0:
                                ip = self.prompt_text_input('Enter Host IP Address:')
                                if ip:
                                    return {'ip': ip.strip(), 'port': 12345}
                            else:
                                return None
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if btn_manual.collidepoint(event.pos):
                            ip = self.prompt_text_input('Enter Host IP Address:')
                            if ip:
                                return {'ip': ip.strip(), 'port': 12345}
                        elif btn_cancel.collidepoint(event.pos):
                            return None
        
        # Server selection UI
        selected_index = 0
        
        while True:
            self.clock.tick(30)
            
            self.screen.fill(ui_theme.BG)
            
            # Title
            title_surf = self.font_title.render('Available Rooms', True, ui_theme.ACCENT)
            title_rect = title_surf.get_rect(center=(self.screen_size[0] // 2, 60))
            self.screen.blit(title_surf, title_rect)
            
            # Server list
            server_rects = []
            start_y = 150
            item_height = 80
            item_width = min(800, self.screen_size[0] - 100)
            
            for i, server in enumerate(discovered_servers):
                x = self.screen_size[0] // 2 - item_width // 2
                y = start_y + i * (item_height + 10)
                
                # Skip if off-screen
                if y > self.screen_size[1] - 200:
                    break
                
                rect = pygame.Rect(x, y, item_width, item_height)
                server_rects.append((rect, i))
                
                # Highlight selected
                is_selected = i == selected_index
                border_color = ui_theme.HIGHLIGHT if is_selected else ui_theme.ACCENT
                bg_color = (30, 35, 40) if is_selected else ui_theme.PANEL
                
                pygame.draw.rect(self.screen, bg_color, rect, border_radius=8)
                pygame.draw.rect(self.screen, border_color, rect, 3 if is_selected else 1, border_radius=8)
                
                # Host username (primary display)
                host_username = server.get('host_username', 'Unknown Host')
                host_surf = self.font_hud.render(host_username, True, ui_theme.HIGHLIGHT if is_selected else ui_theme.TEXT)
                host_rect = host_surf.get_rect(topleft=(x + 16, y + 16))
                self.screen.blit(host_surf, host_rect)
                
                # Players count and game status
                players = server.get('players', 0)
                max_players = server.get('max_players', 4)
                game_started = server.get('game_started', False)
                
                status_text = f"{players}/{max_players} Players - {'Game Started' if game_started else 'Waiting'}"
                status_color = ui_theme.MUTED if game_started else ui_theme.TEXT
                status_surf = self.font_small18.render(status_text, True, status_color)
                status_rect = status_surf.get_rect(topleft=(x + 16, y + 40))
                self.screen.blit(status_surf, status_rect)
                
                # IP and Port
                ip = server.get('ip', '?')
                port = server.get('port', '?')
                ip_surf = self.font_small18.render(f"{ip}:{port}", True, ui_theme.MUTED)
                ip_rect = ip_surf.get_rect(topleft=(x + 16, y + 58))
                self.screen.blit(ip_surf, ip_rect)
            
            # Manual IP button at bottom left
            btn_w, btn_h = 220, 40
            manual_btn = pygame.Rect(40, self.screen_size[1] - 70, btn_w, btn_h)
            mx, my = pygame.mouse.get_pos()
            hover_manual = manual_btn.collidepoint(mx, my)
            pygame.draw.rect(self.screen, ui_theme.HIGHLIGHT if hover_manual else ui_theme.PANEL, manual_btn, border_radius=6)
            pygame.draw.rect(self.screen, ui_theme.ACCENT, manual_btn, 2, border_radius=6)
            manual_surf = self.font_small.render('Enter IP Manually', True, ui_theme.BG if hover_manual else ui_theme.TEXT)
            manual_rect = manual_surf.get_rect(center=manual_btn.center)
            self.screen.blit(manual_surf, manual_rect)

            # Instructions
            instr_y = self.screen_size[1] - 50
            instr1_surf = self.font_small18.render('UP/DOWN: Select | ENTER: Join | ESC: Cancel', True, ui_theme.MUTED)
            instr1_rect = instr1_surf.get_rect(center=(self.screen_size[0] // 2, instr_y))
            self.screen.blit(instr1_surf, instr1_rect)
            
            pygame.display.flip()
            
            # Input handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    
                    if event.key == pygame.K_UP:
                        selected_index = max(0, selected_index - 1)
                    
                    if event.key == pygame.K_DOWN:
                        selected_index = min(len(discovered_servers) - 1, selected_index + 1)
                    
                    if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        return discovered_servers[selected_index]

                    if event.key == pygame.K_i:
                        # I key as shortcut for manual IP
                        ip = self.prompt_text_input('Enter Host IP Address:')
                        if ip:
                            return {'ip': ip.strip(), 'port': 12345}
                
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        # Check manual IP button
                        if manual_btn.collidepoint(event.pos):
                            ip = self.prompt_text_input('Enter Host IP Address:')
                            if ip:
                                return {'ip': ip.strip(), 'port': 12345}
                        # Check server list
                        for rect, idx in server_rects:
                            if rect.collidepoint(event.pos):
                                selected_index = idx
                                return discovered_servers[idx]
                
                if event.type == pygame.MOUSEMOTION:
                    for rect, idx in server_rects:
                        if rect.collidepoint(event.pos):
                            selected_index = idx
                            break


if __name__ == "__main__":
    Game().run()