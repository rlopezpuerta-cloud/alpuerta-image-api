"""
Alpuerta Premiaciones — Image Generator API (estilo Studio Catalog).
Usa fotos pre-procesadas sin fondo (alpuerta_assets_clean/) y aplica:
- Fondo oscuro warm con halo dorado central + spotlight cenital
- Producto con mejoras premium (brillo, contraste, saturacion, nitidez)
- Sombra realista
- Sin particulas
- Franja inferior con copy/cta/logo de marca (emojis stripeados)
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


def mejoras_producto_premium(img_rgba):
    """Mejoras catalog premium preservando canal alpha."""
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


def crear_sombra(producto, blur=32, alpha=180):
    sa = np.array(producto)[:, :, 3]
    sh = np.zeros((*sa.shape, 4), dtype=np.uint8)
    sh[:, :, 3] = (sa > 50) * alpha
    return Image.fromarray(sh).filter(ImageFilter.GaussianBlur(radius=blur))


def estilo_studio_catalog(producto_rgba, size=1080):
    """Compone producto sobre fondo studio dark."""
    producto = mejoras_producto_premium(producto_rgba)

    # Fondo oscuro warm con gradiente radial
    pixels = np.zeros((size, size, 3), dtype=np.uint8)
    cy, cx = size // 2 - 60, size // 2
    yy, xx = np.indices((size, size))
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    factor = np.clip(1 - dist / (size * 0.70), 0, 1) ** 1.8
    center = np.array([72, 58, 42])
    edge   = np.array([10, 9, 12])
    for c in range(3):
        pixels[:, :, c] = (center[c] * factor + edge[c] * (1 - factor)).astype(np.uint8)
    canvas = Image.fromarray(pixels).convert("RGBA")

    # Halo dorado central
    halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hcy, hcx = size // 2, size // 2
    for r, alpha in [(480, 20), (380, 40), (280, 70), (180, 120), (100, 160)]:
        hd.ellipse([hcx - r, hcy - r, hcx + r, hcy + r], fill=(244, 196, 48, alpha))
    halo = halo.filter(ImageFilter.GaussianBlur(radius=55))
    canvas = Image.alpha_composite(canvas, halo)

    # Spotlight cenital sutil
    spot = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    spd = ImageDraw.Draw(spot)
    spd.ellipse([cx - 350, cy - 280, cx + 350, cy + 280], fill=(255, 240, 200, 50))
    spot = spot.filter(ImageFilter.GaussianBlur(radius=70))
    canvas = Image.alpha_composite(canvas, spot)

    # Producto centrado + sombra
    pw, ph = producto.size
    target = int(size * 0.78)
    scale = min(target / pw, target / ph)
    producto_r = producto.resize((int(pw * scale), int(ph * scale)), Image.LANCZOS)
    sombra = crear_sombra(producto_r, blur=32, alpha=180)
    px = (size - producto_r.width) // 2
    py = (size - producto_r.height) // 2

    canvas.paste(sombra, (px + 20, py + 40), sombra)
    canvas.paste(producto_r, (px, py), producto_r)
    return canvas.convert("RGB")


def aplicar_template(photo, copy_text, cta_text):
    """Composicion final 1080x1350 con franja inferior de marca."""
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

    FRANJA_TOP = 1083
    FRANJA_H   = 267
    LOGO_X     = 1080 - 105 - 35
    LOGO_Y     = FRANJA_TOP + (FRANJA_H // 2) - 52

    lines = textwrap.wrap(copy_text, width=48)
    total_h = len(lines) * 36 + 14 + 30
    y = FRANJA_TOP + (FRANJA_H - total_h) // 2
    for line in lines:
        draw.text((50, y), line, fill=(26, 26, 26), font=font_copy)
        y += 36
    draw.text((50, y + 14), cta_text, fill=(196, 154, 26), font=font_cta)
    canvas.paste(logo, (LOGO_X, LOGO_Y), logo)
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

            # Cargar PNG pre-procesado con alpha (sin fondo)
            url = (f"https://res.cloudinary.com/{CLOUDINARY_CLOUD}"
                   f"/image/upload/alpuerta_assets_clean/{asset}.png")
            with urllib.request.urlopen(url, timeout=30) as r:
                producto_rgba = Image.open(io.BytesIO(r.read())).convert("RGBA")

            foto_studio = estilo_studio_catalog(producto_rgba)
            post = aplicar_template(foto_studio, copy_txt, cta_txt)
            img_url = subir_a_cloudinary(post)

            self._respond(200, {"image_url": img_url, "asset_used": asset})

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
