"""
Alpuerta Premiaciones — Image Generator API
Sistema de fondos dinamicos con sombra elipsoidal limpia.
- Analiza tono del producto (warm/cool/neutral)
- Elige fondo que contrasta (dark_cool, dark_warm, light_cream, neutral_gray)
- Usa fotos pre-procesadas sin fondo de alpuerta_assets_clean/
- Sombra elipsoidal (no calcada del alpha)
"""
from http.server import BaseHTTPRequestHandler
import json, base64, urllib.request, io, random, os, time, re
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import textwrap

CLOUDINARY_CLOUD  = os.environ.get("CLOUDINARY_CLOUD", "dx4wlvbxt")
CLOUDINARY_PRESET = os.environ.get("CLOUDINARY_UPLOAD_PRESET", "alpuerta_test")

ASSETS_DIR  = os.path.join(os.path.dirname(__file__), "..", "assets")
OUTFIT_FONT = os.path.join(ASSETS_DIR, "Outfit.ttf")
LOGO_FILE   = os.path.join(ASSETS_DIR, "logo.png")

ASSETS_MEDALLAS = [f"medalla_{str(i).zfill(2)}" for i in range(1, 23)]
ASSETS_TROFEOS  = [f"trofeo_{str(i).zfill(2)}"  for i in range(1, 19)]

TAG_MAP = {
    "1": "medalla", "2": "medalla", "3": "trofeo",
    "4": "trofeo",  "5": "medalla", "6": "trofeo", "7": "medalla"
}

EMOJI_PATTERN = re.compile(
    "[" "\U0001F600-\U0001F64F" "\U0001F300-\U0001F5FF" "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF" "\U00002500-\U00002BEF" "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251" "\U0001F926-\U0001F937" "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F" "\U0001FA70-\U0001FAFF" "\U00010000-\U0010FFFF"
    "\u2640-\u2642" "\u2600-\u2B55" "\u200d" "\u23cf" "\u23e9" "\u231a"
    "\ufe0f" "\u3030" "]+", flags=re.UNICODE)


def strip_emojis(text):
    if not text:
        return text
    cleaned = EMOJI_PATTERN.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([.,!?])", r"\1", cleaned)
    return cleaned


def get_asset(tipo, asset_id=None):
    if asset_id:
        return asset_id
    pool = ASSETS_MEDALLAS if TAG_MAP.get(str(tipo), "medalla") == "medalla" else ASSETS_TROFEOS
    return random.choice(pool)


def analizar_producto(img_rgba):
    """Analiza el producto y retorna tono y luminosidad."""
    arr = np.array(img_rgba)
    alpha = arr[:, :, 3]
    mask = alpha > 200
    if not mask.any():
        return {"tono": "neutral", "luminosidad": "medium"}
    pixels = arr[mask][:, :3].astype(float)
    lum = pixels.mean()
    rb_diff = pixels[:, 0].mean() - pixels[:, 2].mean()
    if rb_diff > 22:
        tono = "warm"
    elif rb_diff < -15:
        tono = "cool"
    else:
        tono = "neutral"
    if lum > 170:
        luminosidad = "light"
    elif lum > 100:
        luminosidad = "medium"
    else:
        luminosidad = "dark"
    return {"tono": tono, "luminosidad": luminosidad}


def elegir_estilo(a):
    """Selecciona el fondo que mas contrasta con el producto."""
    if a["tono"] == "warm":
        return "dark_cool"
    if a["tono"] == "cool":
        return "light_cream" if a["luminosidad"] != "dark" else "dark_warm"
    return "neutral_gray"


def fondo_dark_cool(size, cx, cy):
    """Fondo oscuro azul-grafito con halo blanco-cyan. Contrasta dorados."""
    pixels = np.zeros((size, size, 3), dtype=np.uint8)
    yy, xx = np.indices((size, size))
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    factor = np.clip(1 - dist / (size * 0.70), 0, 1) ** 1.8
    center = np.array([60, 70, 85]); edge = np.array([8, 10, 18])
    for c in range(3):
        pixels[:, :, c] = (center[c] * factor + edge[c] * (1 - factor)).astype(np.uint8)
    canvas = Image.fromarray(pixels).convert("RGBA")
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    for r, a in [(480, 18), (380, 35), (280, 60), (180, 100), (100, 140)]:
        hd.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(220, 230, 255, a))
    return Image.alpha_composite(canvas, halo.filter(ImageFilter.GaussianBlur(radius=55)))


def fondo_dark_warm(size, cx, cy):
    """Fondo oscuro warm con halo dorado. Para productos cool oscuros."""
    pixels = np.zeros((size, size, 3), dtype=np.uint8)
    yy, xx = np.indices((size, size))
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    factor = np.clip(1 - dist / (size * 0.70), 0, 1) ** 1.8
    center = np.array([72, 58, 42]); edge = np.array([10, 9, 12])
    for c in range(3):
        pixels[:, :, c] = (center[c] * factor + edge[c] * (1 - factor)).astype(np.uint8)
    canvas = Image.fromarray(pixels).convert("RGBA")
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    for r, a in [(480, 20), (380, 40), (280, 70), (180, 120), (100, 160)]:
        hd.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(244, 196, 48, a))
    return Image.alpha_composite(canvas, halo.filter(ImageFilter.GaussianBlur(radius=55)))


def fondo_light_cream(size, cx, cy):
    """Fondo crema claro con halo dorado. Para productos cool claros."""
    pixels = np.zeros((size, size, 3), dtype=np.uint8)
    yy, xx = np.indices((size, size))
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    factor = np.clip(1 - dist / (size * 0.65), 0, 1) ** 1.5
    center = np.array([252, 247, 235]); edge = np.array([218, 210, 195])
    for c in range(3):
        pixels[:, :, c] = (center[c] * factor + edge[c] * (1 - factor)).astype(np.uint8)
    canvas = Image.fromarray(pixels).convert("RGBA")
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    for r, a in [(420, 30), (320, 55), (220, 80), (130, 110)]:
        hd.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(244, 196, 48, a))
    return Image.alpha_composite(canvas, halo.filter(ImageFilter.GaussianBlur(radius=50)))


def fondo_neutral_gray(size, cx, cy):
    """Fondo gris neutral. Para productos multicolores o ambiguos."""
    pixels = np.zeros((size, size, 3), dtype=np.uint8)
    yy, xx = np.indices((size, size))
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    factor = np.clip(1 - dist / (size * 0.70), 0, 1) ** 1.6
    center = np.array([210, 210, 215]); edge = np.array([75, 75, 85])
    for c in range(3):
        pixels[:, :, c] = (center[c] * factor + edge[c] * (1 - factor)).astype(np.uint8)
    canvas = Image.fromarray(pixels).convert("RGBA")
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    for r, a in [(420, 25), (320, 45), (220, 70), (130, 100)]:
        hd.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(255, 255, 255, a))
    return Image.alpha_composite(canvas, halo.filter(ImageFilter.GaussianBlur(radius=55)))


def aplicar_spotlight(canvas, cx, cy, size, dark=True):
    spot = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    spd = ImageDraw.Draw(spot)
    color = (255, 240, 200, 50) if dark else (255, 255, 255, 70)
    spd.ellipse([cx - 350, cy - 280, cx + 350, cy + 280], fill=color)
    return Image.alpha_composite(canvas, spot.filter(ImageFilter.GaussianBlur(radius=70)))


def mejoras_producto(img_rgba):
    """Mejoras catalog premium preservando alpha."""
    alpha = img_rgba.split()[3]
    rgb = Image.new("RGB", img_rgba.size, (0, 0, 0))
    rgb.paste(img_rgba, mask=alpha)
    rgb = ImageEnhance.Brightness(rgb).enhance(1.12)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.40)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=2))
    rgb = ImageEnhance.Color(rgb).enhance(1.30)
    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def sombra_elipsoidal(canvas_size, producto_size, producto_pos, dark=True):
    """Sombra elipsoidal limpia debajo del producto (no calcada del alpha)."""
    pw, ph = producto_size
    px, py = producto_pos
    sx = px + pw // 2
    sy = py + int(ph * 0.92)
    ew = int(pw * 0.85)
    eh = int(pw * 0.18)
    sombra = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sombra)
    alpha = 220 if dark else 130
    for scale, a in [(1.3, alpha // 4), (1.0, alpha // 2), (0.7, alpha)]:
        rw, rh = int(ew * scale), int(eh * scale)
        sd.ellipse([sx - rw, sy - rh, sx + rw, sy + rh], fill=(0, 0, 0, a))
    return sombra.filter(ImageFilter.GaussianBlur(radius=35))


def componer_studio(producto_rgba, size=1080):
    """Compone producto con fondo dinamico segun analisis."""
    analisis = analizar_producto(producto_rgba)
    estilo = elegir_estilo(analisis)

    producto = mejoras_producto(producto_rgba)
    cy, cx = size // 2 - 60, size // 2
    fondos = {
        "dark_cool": (fondo_dark_cool, True),
        "dark_warm": (fondo_dark_warm, True),
        "light_cream": (fondo_light_cream, False),
        "neutral_gray": (fondo_neutral_gray, False),
    }
    fondo_fn, is_dark = fondos[estilo]
    canvas = fondo_fn(size, cx, cy)
    canvas = aplicar_spotlight(canvas, cx, cy, size, dark=is_dark)

    pw, ph = producto.size
    target = int(size * 0.88)
    scale = min(target / pw, target / ph)
    producto_r = producto.resize((int(pw * scale), int(ph * scale)), Image.LANCZOS)
    px = (size - producto_r.width) // 2
    py = (size - producto_r.height) // 2

    sombra = sombra_elipsoidal((size, size), producto_r.size, (px, py), dark=is_dark)
    canvas = Image.alpha_composite(canvas, sombra)
    canvas.paste(producto_r, (px, py), producto_r)
    return canvas.convert("RGB"), estilo


def aplicar_template(photo, copy_text, cta_text):
    copy_text = strip_emojis(copy_text)
    cta_text  = strip_emojis(cta_text)
    canvas = Image.new("RGB", (1080, 1350), (255, 255, 255))
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 1080, 1080, 1083], fill=(244, 196, 48))
    font_copy = ImageFont.truetype(OUTFIT_FONT, 27)
    font_cta  = ImageFont.truetype(OUTFIT_FONT, 23)
    logo = Image.open(LOGO_FILE).convert("RGBA")
    la = np.array(logo)
    la[(la[:,:,0] > 240) & (la[:,:,1] > 240) & (la[:,:,2] > 240), 3] = 0
    logo = Image.fromarray(la).resize((105, 105), Image.LANCZOS)
    FT, FH = 1083, 267
    lines = textwrap.wrap(copy_text, width=48)
    total = len(lines) * 36 + 14 + 30
    y = FT + (FH - total) // 2
    for line in lines:
        draw.text((50, y), line, fill=(26, 26, 26), font=font_copy)
        y += 36
    draw.text((50, y + 14), cta_text, fill=(196, 154, 26), font=font_cta)
    canvas.paste(logo, (1080 - 105 - 35, FT + (FH // 2) - 52), logo)
    return canvas


def subir_a_cloudinary(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    b64 = base64.b64encode(buf.getvalue()).decode()
    public_id = f"alpuerta_posts/post_{int(time.time())}"
    payload = json.dumps({
        "upload_preset": CLOUDINARY_PRESET,
        "public_id": public_id,
        "tags": "alpuerta_post,generado",
        "file": f"data:image/jpeg;base64,{b64}"
    }).encode()
    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD}/image/upload",
        data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["secure_url"]


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            tipo = str(body.get("tipo", "2"))
            copy_txt = body.get("copy", "")
            cta_txt  = body.get("cta", "")
            asset_id = body.get("asset_id", None)
            asset = get_asset(tipo, asset_id)

            url = (f"https://res.cloudinary.com/{CLOUDINARY_CLOUD}"
                   f"/image/upload/alpuerta_assets_clean/{asset}.png")
            with urllib.request.urlopen(url, timeout=30) as r:
                producto_rgba = Image.open(io.BytesIO(r.read())).convert("RGBA")

            foto_studio, estilo = componer_studio(producto_rgba)
            post = aplicar_template(foto_studio, copy_txt, cta_txt)
            img_url = subir_a_cloudinary(post)
            self._respond(200, {"image_url": img_url, "asset_used": asset, "estilo": estilo})
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def do_GET(self):
        self._respond(200, {"status": "ok", "service": "Alpuerta Image Generator"})

    def _respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)
