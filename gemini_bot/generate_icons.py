import zlib
import struct
import math
from pathlib import Path

def create_png(width, height, get_pixel):
    """
    Генерирует валидный PNG-файл без внешних зависимостей (только zlib и struct из stdlib).
    """
    # Сигнатура PNG
    png_signature = b"\x89PNG\r\n\x1a\n"

    # IHDR чанк
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xffffffff)
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + ihdr_crc

    # Сырые данные строк с фильтром 0
    raw_data = bytearray()
    for y in range(height):
        raw_data.append(0)  # filter type 0 (None)
        for x in range(width):
            r, g, b, a = get_pixel(x, y, width, height)
            raw_data.extend((r, g, b, a))

    compressed = zlib.compress(bytes(raw_data), 9)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xffffffff)
    idat_chunk = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc

    # IEND чанк
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xffffffff)
    iend_chunk = struct.pack(">I", 0) + b"IEND" + iend_crc

    return png_signature + ihdr_chunk + idat_chunk + iend_chunk

def icon_pixel(x, y, w, h):
    # Нормализованные координаты [-1, 1]
    nx = (x / w) * 2.0 - 1.0
    ny = (y / h) * 2.0 - 1.0
    dist = math.sqrt(nx * nx + ny * ny)

    # 1. Фон: темный градиент с закругленными углами
    # Скругленный прямоугольник (squircle)
    corner_r = 0.82
    q = (abs(nx)**4 + abs(ny)**4)**0.25
    if q > corner_r:
        # Прозрачность за пределами иконки для красивой маски
        edge = (q - corner_r) / 0.08
        if edge >= 1.0:
            return (0, 0, 0, 0)
        alpha = int((1.0 - edge) * 255)
    else:
        alpha = 255

    # Цвет фона: темно-синий глубокий градиент
    bg_r = int(15 + 15 * (1.0 - ny))
    bg_g = int(23 + 20 * (1.0 - ny))
    bg_b = int(42 + 45 * (1.0 - ny))

    # 2. Неоновый светящийся логотип в центре (AI Star / Sparkle)
    # Звезда искусственного интеллекта (как у Gemini)
    # Уравнение астроиды: (x/a)^(2/3) + (y/b)^(2/3) <= 1
    sx = abs(nx) / 0.48
    sy = abs(ny) / 0.48
    if sx > 0 and sy > 0:
        star_val = (sx**(2/3) + sy**(2/3))
    else:
        star_val = 0.0

    if star_val <= 1.0:
        # Внутри звезды: яркий градиент от лазурного (#38bdf8) к фиолетовому (#a855f7)
        t = (nx + ny + 1.0) / 2.0
        r = int(56 + (168 - 56) * t)
        g = int(189 + (85 - 189) * t)
        b = int(248 + (247 - 248) * t)
        return (r, g, b, alpha)
    elif star_val <= 1.25:
        # Мягкое неоновое свечение вокруг звезды
        glow = (1.25 - star_val) / 0.25
        r = int(bg_r + (56 - bg_r) * glow * 0.7)
        g = int(bg_g + (189 - bg_g) * glow * 0.7)
        b = int(bg_b + (248 - bg_b) * glow * 0.7)
        return (r, g, b, alpha)

    # Точечный блик в верхнем левом углу
    dot_dist = math.sqrt((nx + 0.35)**2 + (ny + 0.35)**2)
    if dot_dist < 0.12:
        d_glow = (0.12 - dot_dist) / 0.12
        r = int(bg_r + (255 - bg_r) * d_glow)
        g = int(bg_g + (255 - bg_g) * d_glow)
        b = int(bg_b + (255 - bg_b) * d_glow)
        return (r, g, b, alpha)

    return (bg_r, bg_g, bg_b, alpha)

def main():
    icons_dir = Path(__file__).resolve().parent / "static" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    sizes = [
        ("icon-192.png", 192, 192),
        ("icon-512.png", 512, 512),
        ("apple-touch-icon.png", 180, 180),
    ]

    for filename, w, h in sizes:
        png_bytes = create_png(w, h, icon_pixel)
        target = icons_dir / filename
        with open(target, "wb") as f:
            f.write(png_bytes)
        print(f"Generated {filename} ({w}x{h}, {len(png_bytes)} bytes)")

if __name__ == "__main__":
    main()
