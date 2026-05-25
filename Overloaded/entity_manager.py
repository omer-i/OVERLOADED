import pygame
import random
from Enemy import Enemy

class EntityManager:
    def __init__(self, game):
        self.game = game
        self.enemies_list = []
        self.active_beams = []
        self.spawn_timer = 0.0
        self.base_spawn_interval = game.base_spawn_interval if hasattr(game, 'base_spawn_interval') else 2.0
        self.spawn_interval_current = self.base_spawn_interval

    def spawn_enemy_at_edge(self, viewport_rect, world_rect, difficulty_multiplier=1.0):
        spawn_margin = 280
        valid_spawn_positions = []
        viewport_left = viewport_rect.left
        viewport_top = viewport_rect.top
        viewport_right = viewport_rect.right
        viewport_bottom = viewport_rect.bottom

        # TOP
        spawn_x = random.randint(viewport_left, viewport_right)
        spawn_y = viewport_top - spawn_margin
        if world_rect.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))
        # RIGHT
        spawn_x = viewport_right + spawn_margin
        spawn_y = random.randint(viewport_top, viewport_bottom)
        if world_rect.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))
        # BOTTOM
        spawn_x = random.randint(viewport_left, viewport_right)
        spawn_y = viewport_bottom + spawn_margin
        if world_rect.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))
        # LEFT
        spawn_x = viewport_left - spawn_margin
        spawn_y = random.randint(viewport_top, viewport_bottom)
        if world_rect.collidepoint(spawn_x, spawn_y):
            valid_spawn_positions.append((spawn_x, spawn_y))

        if not valid_spawn_positions:
            return None
        final_spawn_x, final_spawn_y = random.choice(valid_spawn_positions)
        enemy_base_speed = random.randint(60, 120)
        scaled_speed = int(enemy_base_speed * difficulty_multiplier)
        scaled_health = int(30 * (difficulty_multiplier**1.2))
        return Enemy(pos=(final_spawn_x, final_spawn_y), patrol_points=[(final_spawn_x, final_spawn_y)], speed=scaled_speed, hp=scaled_health)

    def handle_enemy_spawning(self, dt, camera_rect, difficulty_multiplier):
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            new_enemy = self.spawn_enemy_at_edge(camera_rect, self.game.world_bounds, difficulty_multiplier)
            if new_enemy:
                if not self.game.network.is_connected:
                    self.enemies_list.append(new_enemy)
            self.spawn_timer = self.spawn_interval_current

    def update_enemies(self, dt, difficulty_multiplier):
        if self.game.network.is_connected:
            for eid, enemy in list(self.game.net_enemies.items()):
                try:
                    enemy.update_rect_positions()
                except Exception:
                    pass
            return

        for enemy in list(self.enemies_list):
            try:
                enemy.movement_speed = int(enemy.base_speed * difficulty_multiplier)
                enemy.max_health = int(enemy.base_health * difficulty_multiplier)
            except Exception:
                pass
            enemy.update(dt, target=self.game.player)
            self.game.resolve_entity_wall_collision(enemy, self.game.walls)

    def resolve_enemy_collisions(self, enemies_list=None):
        """Prevent enemies from overlapping. Can take a custom enemies_list or use self.enemies_list."""
        if enemies_list is None:
            enemies_list = self.enemies_list
        
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

    def handle_enemy_player_damage(self, player_list=None):
        """Handle enemy-player collisions. Can work with client (single player) or server (multiple players).
        
        Args:
            player_list: Optional list of player objects/data. If None, uses game.player (client mode).
                        Format can be: [player_obj, ...] or [{'rect': rect, 'pos': pos}, ...]
        """
        if not self.game.network.is_connected and player_list is None:
            # Client mode - single player
            player_hitbox = self.game.player.hitbox
            for enemy in list(self.enemies_list):
                if enemy.rect.colliderect(player_hitbox):
                    if self.game.player.receive_damage(getattr(enemy, "contact_damage", 15)):
                        try:
                            push_direction = pygame.Vector2(enemy.rect.center) - pygame.Vector2(self.game.player.pos)
                            if push_direction.length_squared() > 0:
                                push_direction = push_direction.normalize()
                                enemy.pos += push_direction * 20
                                enemy.rect.center = (round(enemy.pos.x), round(enemy.pos.y))
                        except Exception:
                            pass
        elif self.game.network.is_connected and player_list is None:
            # Network mode - remote enemies
            for eid, enemy in list(self.game.net_enemies.items()):
                try:
                    try:
                        enemy.update_rect_positions()
                    except Exception:
                        pass
                    if enemy.rect.colliderect(self.game.player.hitbox):
                        if self.game.player.receive_damage(getattr(enemy, "contact_damage", 15)):
                            try:
                                push_direction = pygame.Vector2(enemy.rect.center) - pygame.Vector2(self.game.player.pos)
                                if push_direction.length_squared() > 0:
                                    push_direction = push_direction.normalize()
                                    enemy.pos += push_direction * 20
                                    enemy.update_rect_positions()
                            except Exception:
                                pass
                except Exception:
                    pass
        else:
            # Server mode or custom player list provided
            if player_list is None:
                return
            
            # Work with provided player list (for server)
            for enemy in self.enemies_list:
                for player_data in player_list:
                    # Handle both object and dict formats
                    if hasattr(player_data, 'rect'):
                        player_rect = player_data.rect
                    elif isinstance(player_data, dict) and 'rect' in player_data:
                        player_rect = player_data['rect']
                    elif isinstance(player_data, dict):
                        # Create rect from position
                        x = player_data.get('x', 0)
                        y = player_data.get('y', 0)
                        player_rect = pygame.Rect(x - 18, y - 18, 36, 36)
                    else:
                        continue
                    
                    if enemy.rect.colliderect(player_rect):
                        # For server, just mark that collision happened
                        # Server will handle damage separately
                        if isinstance(player_data, dict):
                            damage = getattr(enemy, 'contact_damage', 10)
                            player_data['health'] = max(0, player_data.get('health', 100) - damage)

    def update_beam_timers(self, dt):
        for beam in list(self.active_beams):
            beam["time_to_live"] -= dt
            if beam["time_to_live"] <= 0:
                try:
                    self.active_beams.remove(beam)
                except ValueError:
                    pass

    def reset(self):
        self.enemies_list.clear()
        self.active_beams.clear()
        self.spawn_timer = 0.0

