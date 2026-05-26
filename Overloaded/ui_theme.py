import pygame


BG = (18, 20, 34)
PANEL = (28, 32, 46)
ACCENT = (180, 220, 255)
TEXT = (230, 230, 240)
MUTED = (150, 160, 175)
HIGHLIGHT = (255, 200, 120)


def draw_centered_text(screen, font, text, pos, color=TEXT):
    surf = font.render(text, True, color)
    rect = surf.get_rect(center=pos)
    screen.blit(surf, rect)


def draw_panel(screen, rect, color=PANEL, border=0):
    pygame.draw.rect(screen, color, rect)
    if border:
        pygame.draw.rect(screen, (0, 0, 0), rect, border)
