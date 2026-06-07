"""
Alpuerta Premiaciones — Image Generator API
POST /api/generate
Body: { "tipo": "2", "copy": "...", "cta": "...", "asset_id": "medalla_01" (opcional) }
Returns: { "image_url": "https://..." }
"""
from http.server import BaseHTTPRequestHandler
import json, base64, urllib.request, io, random, os, time, re
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from scipy.ndimage import gaussian_filter
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
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002500-\U00002BEF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F926-\U0001F937"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00010000-\U0010FFFF"
    "\u2640-\u2642"
    "\u2600-\u2B55"
    "\u200d"
    "\u23cf"
    "\u23e9"
    "\u231a"
    "\ufe0f"
    "\u3030"
    "]+", flags=re.UNICODE)


def strip_emojis(text):
    """Remueve emojis del texto y limpia espacios extra. La fuente Outfit no
    soporta emojis, por lo que se renderizan como cuadritos en la imagen.
    Los emojis se mantienen en el caption de Facebook (que usa otro flujo)."""
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
 
 
def editar_foto(img):
    """
    Edicion fotografica profesional.
    - Detecta el producto y recorta SOLO su bounding box real con 8% de padding.
    - Encaja la imagen completa (fit) en 1080x1080 sin cortar, con relleno
      blanco si las proporciones no son cuadradas.
    - Limpia fondo gris/blanco a blanco puro.
    - Mejora contraste, nitidez, saturacion y brillo.
    """
    w, h = img.size
    arr = np.array(img)
    gray = np.mean(arr, axis=2)

    product_mask = gray < 200
    rows = np.any(product_mask, axis=1)
    cols = np.any(product_mask, axis=0)

    if rows.any() and cols.any():
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
        pad_v = int((rmax - rmin) * 0.08)
        pad_h = int((cmax - cmin) * 0.08)
        rmin = max(0, rmin - pad_v)
        rmax = min(h, rmax + pad_v)
        cmin = max(0, cmin - pad_h)
        cmax = min(w, cmax + pad_h)
        img = img.crop((cmin, rmin, cmax, rmax))

    arr = np.array(img).astype(float)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    lum   = (r + g + b) / 3
    max_c = np.maximum(np.maximum(r, g), b)
    min_c = np.minimum(np.minimum(r, g), b)
    with np.errstate(divide="ignore", invalid="ignore"):
        sat = np.where(max_c > 0, (max_c - min_c) / max_c, 0)
 
    fondo = gaussian_filter(((lum > 200) & (sat < 0.15)).astype(float), sigma=2)
    fondo = np.clip(fondo, 0, 1)
    for ch in range(3):
        arr[:,:,ch] = arr[:,:,ch] * (1 - fondo) + 255 * fondo
    img = Image.fromarray(arr.astype(np.uint8))
 
    img = ImageEnhance.Contrast(img).enhance(1.35)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=80, threshold=2))
    img = ImageEnhance.Color(img).enhance(1.25)
    img = ImageEnhance.Brightness(img).enhance(1.08)

    w2, h2 = img.size
    scale = min(1080 / w2, 1080 / h2)
    new_w = int(w2 * scale)
    new_h = int(h2 * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (1080, 1080), (255, 255, 255))
    canvas.paste(img, ((1080 - new_w) // 2, (1080 - new_h) // 2))
    return canvas
 
 
def aplicar_template(photo, copy_text, cta_text):
    """
    Compone la imagen final 1080x1350 con template de marca Alpuerta.
    Los emojis se limpian del texto que va en la imagen porque la fuente
    Outfit no los soporta. Los emojis se mantienen en el caption de Facebook.
    """
    copy_text = strip_emojis(copy_text)
    cta_text  = strip_emojis(cta_text)

    canvas = Image.new("RGB", (1080, 1350), (255, 255, 255))
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)
 
    draw.rectangle([0, 1080, 1080, 1083], fill=(244, 196, 48))
 
    font_copy = ImageFont.truetype(OUTFIT_FONT, 27)
    font_cta  = ImageFont.truetype(OUTFIT_FONT, 23)
 
    logo = Image.open(LOGO_FILE).convert("RGBA")
    la   = np.array(logo)
    la[(la[:,:,0] > 240) & (la[:,:,1] > 240) & (la[:,:,2] > 240), 3] = 0
    logo = Image.fromarray(la).resize((105, 105), Image.LANCZOS)
 
    FRANJA_TOP = 1083
    FRANJA_H   = 267
    LOGO_X     = 1080 - 105 - 35
    LOGO_Y     = FRANJA_TOP + (FRANJA_H // 2) - 52
 
    lines   = textwrap.wrap(copy_text, width=48)
    total_h = len(lines) * 36 + 14 + 30
    y       = FRANJA_TOP + (FRANJA_H - total_h) // 2
 
    for line in lines:
        draw.text((50, y), line, fill=(26, 26, 26), font=font_copy)
        y += 36
 
    draw.text((50, y + 14), cta_text, fill=(196, 154, 26), font=font_cta)
    canvas.paste(logo, (LOGO_X, LOGO_Y), logo)
 
    return canvas
 
 
def subir_a_cloudinary(img):
    """Sube la imagen final a Cloudinary y devuelve la URL publica."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    b64 = base64.b64encode(buf.getvalue()).decode()
 
    public_id = f"alpuerta_posts/post_{int(time.time())}"
    payload   = json.dumps({
        "upload_preset": CLOUDINARY_PRESET,
        "public_id":     public_id,
        "tags":          "alpuerta_post,generado",
        "file":          f"data:image/jpeg;base64,{b64}"
    }).encode()
 
    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD}/image/upload",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["secure_url"]
 
 
class handler(BaseHTTPRequestHandler):
 
    def do_POST(self):
        try:
            length   = int(self.headers.get("Content-Length", 0))
            body     = json.loads(self.rfile.read(length))
            tipo     = str(body.get("tipo", "2"))
            copy_txt = body.get("copy", "")
            cta_txt  = body.get("cta", "")
            asset_id = body.get("asset_id", None)
 
            asset = get_asset(tipo, asset_id)
 
            url = (f"https://res.cloudinary.com/{CLOUDINARY_CLOUD}"
                   f"/image/upload/alpuerta_assets/{asset}.jpg")
            with urllib.request.urlopen(url, timeout=30) as r:
                foto = Image.open(io.BytesIO(r.read())).convert("RGB")
 
            foto_ed = editar_foto(foto)
            post    = aplicar_template(foto_ed, copy_txt, cta_txt)
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
