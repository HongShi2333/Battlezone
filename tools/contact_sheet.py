"""把多张截图拼成一张 (调试用)"""
import sys, pygame
out, names = sys.argv[1], sys.argv[2:]
W, H = 640, 360
sheet = pygame.Surface((W * 3, H * ((len(names) + 2) // 3)))
for i, n in enumerate(names):
    sheet.blit(pygame.transform.smoothscale(pygame.image.load('screens/%s.png' % n), (W, H)), ((i % 3) * W, (i // 3) * H))
pygame.image.save(sheet, out)
