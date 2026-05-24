import pygame
import os


class Player(pygame.sprite.Sprite):
	"""Player character - controllable sprite with movement, health, and immunity system."""

	def __init__(self, pos=(0, 0), speed=300, size=(32, 32), color=(255, 255, 255)):
		"""Initialize the player.
		
		Args:
			pos: Starting position as (x, y) tuple
			speed: Movement speed in pixels per second
			size: Sprite dimensions as (width, height)
			color: RGB color tuple for sprite appearance
		"""
		super().__init__()
		
		# === SPRITE / ANIMATION ===
		self.animation_frames = []
		self.animation_frames_flipped = []
		self.current_frame_index = 0
		self.frame_timer = 0.0  # Timer to control animation frame rate
		self.is_facing_right = True
		self.idle_frames = []
		self.run_frames = []
		self.idle_frames_flipped = []
		self.run_frames_flipped = []

		self.load_necromancer_sprite()

		if self.animation_frames:
			self.image = self.animation_frames[0]
		else:
			self.image = pygame.Surface(size, pygame.SRCALPHA)
			self.image.fill(color)

		self.rect = self.image.get_rect(center=pos)
		self.rect.center = (self.rect.centerx, self.rect.centery + 20) 
		self.base_rect = self.image.get_rect()
		self.hitbox = pygame.Rect(0, 0, 10, 10) # Adjust width/height as needed
		self.hitbox.center = (self.rect.centerx, self.rect.centery + 10)

		
		# MOVEMENT PROPERTIES
		self.pos = pygame.Vector2(self.rect.center)
		self.velocity = pygame.Vector2(0, 0)  # Current velocity in pixels/second
		self.movement_speed = speed  # Base movement speed
		
		# HEALTH SYSTEM
		self.max_health = 100
		self.health = self.max_health
		
		# INVULNERABILITY AFTER DAMAGE
		self.invuln_timer = 0.0  # Countdown timer for invulnerability period
		self.invuln_duration = 1.0  # How long invulnerability lasts after taking damage

	def handle_input(self, keys=None):
		"""Process keyboard input and update velocity direction.
		
		WASD Controls:
		- W: Move up
		- A: Move left
		- S: Move down
		- D: Move right
		
		Args:
			keys: Optional pygame key state (defaults to pygame.key.get_pressed())
		"""
		if keys is None:
			keys = pygame.key.get_pressed()

		# Read directional input
		dx = 0
		dy = 0
		if keys[pygame.K_d]:
			dx += 1
		if keys[pygame.K_a]:
			dx -= 1
		if keys[pygame.K_s]:
			dy += 1
		if keys[pygame.K_w]:
			dy -= 1

		# Set velocity based on input
		self.velocity.x = dx
		self.velocity.y = dy
		
		# Normalize diagonal movement so moving diagonally isn't faster
		if self.velocity.length_squared() > 1:
			self.velocity = self.velocity.normalize()

	def load_necromancer_sprite(self):
			try:
				asset_directory = os.path.join(os.path.dirname(__file__), 'assets', 'player')
				sprite_path = os.path.join(asset_directory, 'Necromancer_creativekind-Sheet.png')
				sheet = pygame.image.load(sprite_path).convert_alpha()

				ROWS = 7
				FRAMES_PER_ROW = [8, 8, 13, 13, 17, 5, 9]  
				
				# --- THE FIX IS HERE ---
				MAX_COLUMNS = max(FRAMES_PER_ROW) # Finds the longest row (17)
				FRAME_WIDTH = sheet.get_width() // MAX_COLUMNS # Fixed width for ALL frames
				FRAME_HEIGHT = sheet.get_height() // ROWS
				SCALE = 1.5

				self.idle_frames = []
				self.run_frames = []
				self.idle_frames_flipped = []
				self.run_frames_flipped = []

				for row_index, frame_count in enumerate(FRAMES_PER_ROW):
					for i in range(frame_count):
						frame = pygame.Surface((FRAME_WIDTH, FRAME_HEIGHT), pygame.SRCALPHA)
						frame.blit(
							sheet,
							(0, 0),
							(i * FRAME_WIDTH, row_index * FRAME_HEIGHT, FRAME_WIDTH, FRAME_HEIGHT)
						)

						scaled = pygame.transform.scale(
							frame,
							(int(FRAME_WIDTH * SCALE), int(FRAME_HEIGHT * SCALE))
						)

						if row_index == 0:
							self.idle_frames.append(scaled)
							self.idle_frames_flipped.append(pygame.transform.flip(scaled, True, False))
						elif row_index == 1:
							self.run_frames.append(scaled)
							self.run_frames_flipped.append(pygame.transform.flip(scaled, True, False))

			except Exception as e:
				print("Failed loading necromancer:", e)



	def update(self, dt):
		"""Update player position, animation, and invulnerability each frame."""
		
		# 1) Move by velocity (The "Source of Truth" for position)
		self.pos += self.velocity * self.movement_speed * dt

		# 2) Choose which animation set to use
		moving = self.velocity.length_squared() > 0
		if moving and self.run_frames:
			frames = self.run_frames
			frames_flipped = self.run_frames_flipped
		elif self.idle_frames:
			frames = self.idle_frames
			frames_flipped = self.idle_frames_flipped
		else:
			return

		# 3) Advance animation timer
		self.frame_timer += dt
		if self.frame_timer >= 0.1:
			self.frame_timer = 0
			self.current_frame_index = (self.current_frame_index + 1) % len(frames)

		# 4) Update facing direction
		if self.velocity.x > 0:
			self.is_facing_right = True
		elif self.velocity.x < 0:
			self.is_facing_right = False

		# 5) Set image for this frame
		if self.is_facing_right:
			self.image = frames[self.current_frame_index]
		else:
			self.image = frames_flipped[self.current_frame_index]



		# This centers the small physical hitbox on the player's position
		# ADJUST THE +15 BELOW: Increase it to move the green box down towards the feet
		HITBOX_Y_OFFSET = 50
		self.hitbox.center = (round(self.pos.x), round(self.pos.y) + HITBOX_Y_OFFSET)

		# 7) Invulnerability timer
		if hasattr(self, "invuln_timer"):
			self.invuln_timer = max(0.0, self.invuln_timer - dt)

		# 6) SYNC RECTS (Must happen AFTER setting the image)
		# This centers the large visual image on the player's position

		self.rect = pygame.Rect(0, 20, 40, 70) 
		self.rect.center = (self.rect.centerx, self.rect.centery + 50)

		self.update_rect_positions()


	def update_rect_positions(self):
		# This is the 'master' offset. 
		# Increase this number to move the RECT lower on the sprite.
		RECT_OFFSET_Y = 50
		
		# We update the rect based on our world position (self.pos) + our offset
		self.rect.center = (round(self.pos.x), round(self.pos.y) + RECT_OFFSET_Y)
		
		# If you want the green hitbox to be even lower (at the feet):
		HITBOX_OFFSET_Y = 35
		self.hitbox.center = (round(self.pos.x), round(self.pos.y) + HITBOX_OFFSET_Y)



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
		"""Check if player is still alive.
		
		Returns:
			True if health > 0, False if dead
		"""
		return self.health > 0

	def receive_damage(self, damage_amount):
		"""GAME LOGIC: Apply damage only if not currently invulnerable.
		
		After taking damage, the player becomes temporarily immune for a brief period.
		
		Args:
			damage_amount: Amount of damage to apply
			
		Returns:
			True if damage was applied, False if player was invulnerable
		"""
		# Check if invulnerability timer has expired
		if getattr(self, "invuln_timer", 0) <= 0:
			self.take_damage(damage_amount)
			# Start new invulnerability period
			self.invuln_timer = getattr(self, "invuln_duration", 1.0)
			return True
		# Damage blocked by invulnerability
		return False


