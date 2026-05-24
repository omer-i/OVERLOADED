import pygame
import sys
import json
import os


class Enemy(pygame.sprite.Sprite):
	"""Enemy goblin sprite - chases player or patrols when player not nearby."""

	def __init__(self, pos=(0, 0), patrol_points=None, speed=120, size=(32, 32), color=(50, 200, 50), aggro_range=150, hp=50):
		super().__init__()
		
		# MOVEMENT PROPERTIES
		self.pos = pygame.Vector2(pos)
		self.velocity = pygame.Vector2(0, 0)
		self.movement_speed = speed  # Current speed (can be scaled by game over time)
		self.base_speed = speed  # Store original speed for difficulty scaling
		
		# HEALTH & DAMAGE
		self.health = hp
		self.base_health = 50
		self.max_health = hp
		self.contact_damage = 10  # Damage dealt to player on collision

		# SPRITE ANIMATION PROPERTIES
		self.animation_frames = []  # List of animation frame surfaces
		self.animation_frames_flipped = []  # Flipped versions for facing left
		self.current_frame_index = 0  # Current animation frame
		self.frame_display_time = 0.0  # Accumulator for frame timing
		self.is_facing_right = True  # Current facing direction
		self.load_goblin_sprite()  # Load sprite sheet and extract frames

		# Set initial image based on loaded frames
		if self.animation_frames:
			self.image = self.animation_frames[0]
		else:
			# Fallback sprite if loading fails
			self.image = pygame.Surface(size, pygame.SRCALPHA)
			self.image.fill(color)

		# Position rect at center (enemy tracking uses center positions)
		self.rect = self.image.get_rect(center=self.pos)

		# PATROL BEHAVIOR PROPERTIES
		if patrol_points is None:
			# Default: patrol between current position and 100 pixels right
			self.patrol_waypoints = [pygame.Vector2(self.pos), pygame.Vector2(self.pos) + pygame.Vector2(100, 0)]
		else:
			self.patrol_waypoints = [pygame.Vector2(p) for p in patrol_points]

		self.current_patrol_waypoint_index = 0
		self.aggro_range = aggro_range  # Not currently used but kept for future features

	def load_goblin_sprite(self):
		"""Load goblin sprite sheet from assets and extract animation frames.
		
		Loads the run animation from JSON frame data and sprite sheet PNG.
		Applies red tint and scales up all frames.
		Stores both normal and horizontally-flipped versions for direction changes.
		"""
		try:
			# Build path to goblin sprite assets
			asset_directory = os.path.join(os.path.dirname(__file__), 'assets', 'goblin')
			json_file_path = os.path.join(asset_directory, 'goblin scout - silhouette all animations-run.json')
			png_file_path = os.path.join(asset_directory, 'goblin scout - silhouette all animations-run.png')

			# Load frame data from JSON
			with open(json_file_path, 'r') as f:
				frame_data_dict = json.load(f)

			# Load sprite sheet image
			spritesheet_image = pygame.image.load(png_file_path).convert_alpha()

			# Scale factor to make goblins larger (3.5x original sprite size)
			SPRITE_SCALE_FACTOR = 3.5

			# Extract each frame from sprite sheet and process it
			for frame_info in frame_data_dict['frames']:
				frame_coords = frame_info['frame']
				frame_x = frame_coords['x']
				frame_y = frame_coords['y']
				frame_width = frame_coords['w']
				frame_height = frame_coords['h']

				# Extract this frame from the sprite sheet
				frame_surface = pygame.Surface((frame_width, frame_height), pygame.SRCALPHA)
				frame_surface.blit(spritesheet_image, (0, 0), (frame_x, frame_y, frame_width, frame_height))

				# Apply red color tint to match goblin appearance
				frame_surface = self._apply_green_tint(frame_surface)

				# Scale frame to larger size
				scaled_frame = pygame.transform.scale(
					frame_surface, 
					(int(frame_width * SPRITE_SCALE_FACTOR), int(frame_height * SPRITE_SCALE_FACTOR))
				)

				# Store normal and flipped versions for direction changes
				self.animation_frames.append(scaled_frame)
				self.animation_frames_flipped.append(pygame.transform.flip(scaled_frame, True, False))

		except Exception as load_error:
			print(f"Error loading goblin sprite: {load_error}")
			self.animation_frames = []
			self.animation_frames_flipped = []

	def _apply_green_tint(self, surface):
		"""Apply green color tint to sprite surface for goblin appearance."""
		tinted_surface = surface.copy()
		green_overlay = pygame.Surface(tinted_surface.get_size())
		green_overlay.fill((0, 255, 0))
		# Blend green overlay using multiply mode
		tinted_surface.blit(green_overlay, (0, 0), special_flags=pygame.BLEND_MULT)
		return tinted_surface

	def _move_towards(self, target_x, target_y, dt):
		"""GAME LOGIC: Move towards target position.
		
		Args:
			target_x: Target X coordinate
			target_y: Target Y coordinate
			dt: Delta time since last frame
		"""
		# Calculate direction to target
		dx = target_x - self.pos.x
		dy = target_y - self.pos.y
		distance_squared = dx * dx + dy * dy
		
		if distance_squared > 0:
			distance = (distance_squared) ** 0.5
			# Normalize and move
			self.pos.x += (dx / distance) * self.movement_speed * dt
			self.pos.y += (dy / distance) * self.movement_speed * dt

	def update(self, dt, target=None):
		"""GAME LOGIC: Update enemy each frame with movement and animation.

		Args:
			dt: Delta time since last frame (in seconds)
			target: Optional target object with 'rect' attribute to chase
		"""
		# BEHAVIOR: If one or more targets provided, chase the nearest player
		nearest_target = None
		if target is not None:
			# Allow passing a single target or an iterable of targets
			try:
				iter(target)
				candidates = []
				for t in target:
					if hasattr(t, 'rect'):
						cx, cy = t.rect.center
					elif hasattr(t, 'pos'):
						cx, cy = (round(t.pos.x), round(t.pos.y))
					elif isinstance(t, dict):
						cx, cy = (t.get('x', 0), t.get('y', 0))
					else:
						continue
					candidates.append((cx, cy, t))
				if candidates:
					candidates.sort(key=lambda c: (c[0]-self.pos.x)**2 + (c[1]-self.pos.y)**2)
					nearest_target = candidates[0][2]
			except TypeError:
				# Not iterable: treat as single target object
				if hasattr(target, 'rect') or hasattr(target, 'pos') or isinstance(target, dict):
					nearest_target = target

		if nearest_target is not None:
			if hasattr(nearest_target, 'rect'):
				px, py = nearest_target.rect.center
			elif hasattr(nearest_target, 'pos'):
				px, py = (round(nearest_target.pos.x), round(nearest_target.pos.y))
			elif isinstance(nearest_target, dict):
				px, py = (nearest_target.get('x', 0), nearest_target.get('y', 0))
			else:
				px, py = (self.pos.x, self.pos.y)
			self._move_towards(px, py, dt)
		else:
			# No valid target, patrol between waypoints
			current_waypoint = self.patrol_waypoints[self.current_patrol_waypoint_index]
			if (current_waypoint - self.pos).length_squared() < 4:
				# Reached waypoint, move to next one
				self.current_patrol_waypoint_index = (self.current_patrol_waypoint_index + 1) % len(self.patrol_waypoints)
			else:
				self._move_towards(current_waypoint.x, current_waypoint.y, dt)

		# RENDERING: Update animation frame
		if self.animation_frames:
			self.frame_display_time += dt
			# Advance frame every 100ms (per sprite sheet timing)
			if self.frame_display_time >= 0.1:
				self.frame_display_time -= 0.1
				self.current_frame_index = (self.current_frame_index + 1) % len(self.animation_frames)

			# LOGIC: Determine facing direction based on chosen target
			# Use the nearest_target (computed above) when an iterable of targets
			chosen_target = nearest_target if nearest_target is not None else target
			if chosen_target is not None:
				if hasattr(chosen_target, "rect"):
					target_x_position = chosen_target.rect.centerx
				elif hasattr(chosen_target, "pos"):
					target_x_position = chosen_target.pos.x
				elif isinstance(chosen_target, dict):
					target_x_position = chosen_target.get('x', self.pos.x)
				else:
					target_x_position = self.pos.x

				# Face towards the target
				self.is_facing_right = (target_x_position > self.pos.x)

			# Select appropriate frame (normal or flipped based on facing)
			if self.is_facing_right:
				self.image = self.animation_frames[self.current_frame_index]
			else:
				self.image = self.animation_frames_flipped[self.current_frame_index]
		self.render_rect = self.image.get_rect(center=(round(self.pos.x), round(self.pos.y)))

		# Smaller collision rect
		body_width = int(self.render_rect.width * 0.5 -60)
		body_height = int(self.render_rect.height * 0.6 - 65)

		self.rect = pygame.Rect(0, 0, body_width, body_height)
		self.rect.center = (self.render_rect.centerx, self.render_rect.centery + 15)


	def draw(self, surface):
		"""RENDERING: Draw enemy sprite on the given surface.
		
		Args:
			surface: Pygame surface to draw on
		"""
		surface.blit(self.image, self.rect)

	def update_rect_positions(self):
		"""Update render_rect and collision rect from current `self.pos` and image."""
		try:
			self.render_rect = self.image.get_rect(center=(round(self.pos.x), round(self.pos.y)))
			# compute body rect but ensure minimum sensible size
			body_width = max(16, int(self.render_rect.width * 0.5) - 60)
			body_height = max(16, int(self.render_rect.height * 0.6) - 65)
			self.rect = pygame.Rect(0, 0, body_width, body_height)
			self.rect.center = (self.render_rect.centerx, self.render_rect.centery + 15)
		except Exception:
			# fallback
			self.rect = self.image.get_rect(center=(round(self.pos.x), round(self.pos.y)))

	def take_damage(self, damage_amount):
		"""GAME LOGIC: Reduce health by damage amount.
		
		Args:
			damage_amount: Amount of damage to subtract from health
			
		Returns:
			Updated health value
		"""
		self.health = max(0, self.health - damage_amount)
		return self.health

	def is_alive(self):
		"""Check if enemy is still alive.
		
		Returns:
			True if health > 0, False if dead
		"""
		return self.health > 0

	def get_collision_rect(self):
		"""GAME LOGIC: Get a smaller hitbox for beam collision detection.
		
		Returns a rect that's 40% the size of the sprite, centered on the enemy.
		This makes enemies harder to hit without penalizing shots from slightly off-angle.
		
		Returns:
			pygame.Rect collision hitbox, centered on enemy position
		"""
		# Shrink to 40% of original size from center
		width_factor = 1
		height_factor = 1

		rect_width = int(self.rect.width * width_factor)
		rect_height = int(self.rect.height * height_factor)

		collision_rect = pygame.Rect(0, 0, rect_width, rect_height)

		# Center it properly
		collision_rect.center = self.rect.center

		return collision_rect
