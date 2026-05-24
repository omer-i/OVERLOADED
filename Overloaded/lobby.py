import pygame
import ui_theme


class Lobby:
    def __init__(self, game):
        self.game = game

    def wait_screen(self, is_host=False):
        """Unified wait screen for both Host and Client."""
        # reuse game's cached fonts for performance
        font = getattr(self.game, 'font_title', pygame.font.SysFont(None, 40))
        small_font = getattr(self.game, 'font_small', pygame.font.SysFont(None, 24))

        while True:
            self.game.clock.tick(30)

            # 1. Check Network State to transition
            if self.game.network.client:
                state = self.game.network.client.get_latest_state()
                if state and state.get('type') == 'state':
                    # The server officially started the game!
                    pygame.event.clear()
                    return True

            # 2. Event Handling
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.game.network.stop_network()
                        return False

                    # Only the host can signal the server to start
                    if is_host and event.key == pygame.K_RETURN:
                        if self.game.network.server:
                            self.game.network.server.start_game()


            # 3. Drawing (themed layout)
            self.game.screen.fill(ui_theme.BG)

            # Host view: centered lobby panel with horizontal player list
            if is_host:
                panel_w = min(1000, self.game.screen_size[0] - 160)
                panel_h = 220
                panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
                panel_rect.center = (self.game.screen_size[0] // 2, self.game.screen_size[1] // 2 - 20)
                pygame.draw.rect(self.game.screen, ui_theme.PANEL, panel_rect, border_radius=8)

                # Title
                title_surf = font.render('Lobby — Press ENTER to Start', True, ui_theme.ACCENT)
                title_rect = title_surf.get_rect(center=(panel_rect.centerx, panel_rect.top + 28))
                self.game.screen.blit(title_surf, title_rect)

                # player boxes horizontally
                players = []
                if self.game.network.client:
                    st = self.game.network.client.get_latest_state()
                    if st: players = st.get('players', [])

                box_w = 140
                box_h = 96
                spacing = 18
                count = max(1, len(players))
                total_w = count * box_w + (count - 1) * spacing
                start_x = panel_rect.centerx - total_w // 2
                y_top = panel_rect.centery - box_h // 2 + 12

                for i, p in enumerate(players):
                    bx = start_x + i * (box_w + spacing)
                    brect = pygame.Rect(bx, y_top, box_w, box_h)
                    pygame.draw.rect(self.game.screen, (12, 12, 14), brect, border_radius=6)
                    pygame.draw.rect(self.game.screen, ui_theme.ACCENT, brect, 2, border_radius=6)
                    # small avatar: show initials if username present
                    uname = p.get('username') or f"P{p.get('id')}"
                    initials = ''.join([part[0].upper() for part in str(uname).split()][:2])
                    avatar_pos = (brect.left + 28, brect.centery)
                    pygame.draw.circle(self.game.screen, ui_theme.HIGHLIGHT, avatar_pos, 18)
                    init_surf = small_font.render(initials, True, ui_theme.TEXT)
                    init_rect = init_surf.get_rect(center=avatar_pos)
                    self.game.screen.blit(init_surf, init_rect)
                    # name
                    name_label = uname if uname else f"Player {p.get('id')}"
                    name_surf = small_font.render(name_label, True, ui_theme.TEXT)
                    name_rect = name_surf.get_rect(midleft=(brect.left + 56, brect.centery - 6))
                    self.game.screen.blit(name_surf, name_rect)
                    # ready indicator (green dot) or muted
                    if p.get('ready'):
                        pygame.draw.circle(self.game.screen, (0,200,0), (brect.right - 18, brect.top + 18), 8)
                    else:
                        pygame.draw.circle(self.game.screen, ui_theme.MUTED, (brect.right - 18, brect.top + 18), 6)

                # Draw leaderboard in bottom right
                leaderboard_x = self.game.screen_size[0] - 300
                leaderboard_y = self.game.screen_size[1] - 270
                self.game.render_leaderboard(self.game.screen, leaderboard_x, leaderboard_y)

                pygame.display.flip()
            else:
                # Non-host (joining) view: large centered waiting message
                msg = 'Waiting for Host to start the game...'
                msg_surf = font.render(msg, True, ui_theme.ACCENT)
                msg_rect = msg_surf.get_rect(center=(self.game.screen_size[0] // 2, self.game.screen_size[1] // 2 - 20))
                self.game.screen.blit(msg_surf, msg_rect)

                # Show logged-in account name if available
                if getattr(self.game, 'current_user', None):
                    name_surf = small_font.render(f'You: {self.game.current_user}', True, ui_theme.TEXT)
                    name_rect = name_surf.get_rect(center=(self.game.screen_size[0] // 2, msg_rect.bottom + 24))
                    self.game.screen.blit(name_surf, name_rect)

                # Draw leaderboard in bottom right
                leaderboard_x = self.game.screen_size[0] - 300
                leaderboard_y = self.game.screen_size[1] - 270
                self.game.render_leaderboard(self.game.screen, leaderboard_x, leaderboard_y)

                pygame.display.flip()