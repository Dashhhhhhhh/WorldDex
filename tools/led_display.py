# world_dex_display.py
"""
World‑Dex handheld UI for a 240 × 240 ST7789 IPS display
────────────────────────────────────────────────────────
• **No command‑line arguments needed** – the script boots straight into a
  mini‑WorldDex UI:

      1. Category list     (e.g. "Trees", "Minerals")
      2. Object list       (items you have scanned in that category)
      3. Detail sheet      (facts for a single object; scrolls if long)

• Works **both** with real SPI hardware (ST7789) **and** on any desktop via a
  Pygame emulator (default when run on Windows/macOS or when the env‑var
  `USE_EMULATOR=1`).

• Reads your catalog from individual category JSON files in the data directory
  (e.g., `DATA_DIR/trees.json`, `DATA_DIR/minerals.json`), with each file
  containing objects for that specific category.

• Controls
  ─────────
  ┌───────────────┬──────────────┐
  │ Pi GPIO pin   │ Emulator key │
  ├───────────────┼──────────────┤
  │ 5   (◎ Up)    │ ↑ arrow      │
  │ 6   (◎ Down)  │ ↓ arrow      │
  │ 13  (◎ Select)│ Enter/Space  │
  │ 19  (◎ Back)  │ Esc/Backspace│
  └───────────────┴──────────────┘

Install
───────
```bash
pip install pillow python-dotenv tinydb requests
pip install luma.lcd luma.emulator pygame  # display + emulator
```

Env‑vars (`.env`)
─────────────────
```
DATA_DIR=./data
USE_EMULATOR=1           # 1 = always Pygame, 0 = auto‑detect
SPI_SPEED_HZ=40000000    # if you *are* on hardware (must be in whitelist)
FONT_SIZE=18
```

Run
───
```bash
python world_dex_display.py   # desktop → opens window
sudo   python world_dex_display.py   # on Pi with ST7789
```
"""

from __future__ import annotations
import os, sys, time, json, textwrap, contextlib, platform
from pathlib import Path
from typing import List, Dict

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# ─── Config / env ─────────────────────────────────────────────────────────
load_dotenv()
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
USE_EMU  = os.getenv("USE_EMULATOR") == "1" or platform.system() in {"Windows", "Darwin"}

WIDTH, HEIGHT = 240, 240
BORDER   = 6
LINE_GAP = 2
FONT_SZ  = int(os.getenv("FONT_SIZE", "18"))

# ─── tiny helper to read catalog from category files ─────────────────────
def load_catalog() -> Dict:
    """Load catalog from individual category JSON files"""
    categories = []
    all_objects = []
    
    # Scan data directory for category JSON files
    if not DATA_DIR.exists():
        return {"categories": [], "objects": []}
    
    for json_file in DATA_DIR.glob("*.json"):
        category_name = json_file.stem  # filename without extension
        
        try:
            with json_file.open() as fp:
                category_data = json.load(fp)
            
            # Create category entry
            category = {
                "id": category_name,
                "name": category_data.get("name", category_name.replace("_", " ").title())
            }
            categories.append(category)
            
            # Add objects from this category
            objects = category_data.get("objects", [])
            for obj in objects:
                obj["category_id"] = category_name  # Ensure category_id matches
                all_objects.append(obj)
                
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not load {json_file}: {e}")
            continue
    
    return {
        "categories": sorted(categories, key=lambda c: c["name"].lower()),
        "objects": all_objects
    }

# Index objects by category_id for quick lookup

def build_lookup(cat: List[Dict], objs: List[Dict]):
    objs_by_cat: Dict[str,List[Dict]] = {c["id"]: [] for c in cat}
    for o in objs:
        objs_by_cat.setdefault(o["category_id"], []).append(o)
    # sort alphabetically
    for k in objs_by_cat:
        objs_by_cat[k].sort(key=lambda x:x["name"].lower())
    return objs_by_cat

# ─── display backend detection ───────────────────────────────────────────

def init_display():
    """Return (device, draw_ctx) where draw_ctx yields a Pillow draw"""
    if USE_EMU:
        from luma.emulator.device import pygame as emu
        dev = emu(width=WIDTH, height=HEIGHT)
        
        @contextlib.contextmanager
        def _ctx():
            img = Image.new("RGB", (WIDTH, HEIGHT), "black")
            yield ImageDraw.Draw(img)
            dev.display(img)
        return dev, _ctx
    # ── real SPI ──────────────────────────────
    from luma.core.interface.serial import spi
    from luma.lcd.device import st7789
    speed = int(os.getenv("SPI_SPEED_HZ", "40000000"))
    serial = spi(port=0, device=0, gpio_DC=25, gpio_RST=24, bus_speed_hz=speed)
    dev = st7789(serial, width=WIDTH, height=HEIGHT, rotate=180)
    
    @contextlib.contextmanager
    def _ctx():
        img = Image.new("RGB", (WIDTH, HEIGHT), "black")
        yield ImageDraw.Draw(img)
        dev.display(img)
    return dev, _ctx

device, canvas = init_display()

# ─── font (cross‑platform) ───────────────────────────────────────────────

def load_font():
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, FONT_SZ)
    return ImageFont.load_default()

FONT = load_font()
ASC, DSC = FONT.getmetrics()
LINE_H = ASC + DSC + LINE_GAP

# ─── Input handling ──────────────────────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    HW_BUTTONS = True and not USE_EMU
except (RuntimeError, ModuleNotFoundError):
    HW_BUTTONS = False

BTN_UP, BTN_DN, BTN_OK, BTN_BACK = (5,6,13,19)

if HW_BUTTONS:
    GPIO.setmode(GPIO.BCM)
    for pin in (BTN_UP, BTN_DN, BTN_OK, BTN_BACK):
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def get_key():
    """Return logical key string from either GPIO or Pygame."""
    if HW_BUTTONS:
        if not GPIO.input(BTN_UP):   return "up"
        if not GPIO.input(BTN_DN):   return "down"
        if not GPIO.input(BTN_OK):   return "ok"
        if not GPIO.input(BTN_BACK): return "back"
    else:
        import pygame
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:    return "up"
                if event.key == pygame.K_DOWN:  return "down"
                if event.key in (pygame.K_RETURN, pygame.K_SPACE): return "ok"
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE): return "back"
    return None

# ─── UI states ───────────────────────────────────────────────────────────
STATE_CAT, STATE_OBJ, STATE_DESC = range(3)

class WorldDexUI:
    def __init__(self):
        self.state = STATE_CAT
        self.sel_idx = 0      # highlighted index in current list
        self.cat:list = []
        self.obj:list = []
        self.objs_by_cat = {}
        self.active_cat_id:str|None = None
        self.load_data()
        self.last_refresh = time.time()

    def load_data(self):
        data = load_catalog()
        self.cat = sorted(data["categories"], key=lambda c:c["name"].lower())
        self.obj = data["objects"]
        self.objs_by_cat = build_lookup(self.cat, self.obj)    # ── rendering helpers ───────────────────
    def write_line(self, draw, y, txt, highlight=False):
        fill = (0,255,0) if highlight else (255,255,255)
        draw.text((BORDER,y), txt, font=FONT, fill=fill)
    
    def render(self):
        with canvas() as draw:
            draw.rectangle((0,0,WIDTH,HEIGHT), fill="black")
            draw.text((BORDER,2), "World‑Dex", fill=(255,0,0), font=FONT)
            y = BORDER + LINE_H
            if self.state == STATE_CAT:
                for i,cat in enumerate(self.cat):
                    self.write_line(draw, y, cat["name"], i==self.sel_idx)
                    y += LINE_H
            elif self.state == STATE_OBJ:
                objs = self.objs_by_cat.get(self.active_cat_id, [])
                for i,o in enumerate(objs):
                    self.write_line(draw, y, o["name"], i==self.sel_idx)
                    y += LINE_H
            else:  # DESCRIPTION
                obj = self.get_current_obj()
                facts = "\n".join(obj.get("facts", [])[:3]) if obj else "(no data)"
                wrapper = textwrap.TextWrapper(width=30)
                lines = wrapper.wrap(f"{obj['name'] if obj else ''}: {facts}")
                for ln in lines:
                    if y>HEIGHT-LINE_H: break
                    self.write_line(draw, y, ln)
                    y += LINE_H

    # ── helpers ─────────────────────────────
    def get_current_obj(self):
        if self.active_cat_id is None: return None
        objs = self.objs_by_cat.get(self.active_cat_id, [])
        if not objs: return None
        return objs[self.sel_idx]

    # ── input handling ──────────────────────
    def handle_key(self, key):
        if key is None: return
        if key in {"up","down"}:
            max_idx = len(self.current_list())-1
            if max_idx<0: return
            self.sel_idx = (self.sel_idx + (-1 if key=="up" else 1))% (max_idx+1)
        elif key=="ok":
            if self.state==STATE_CAT and self.cat:
                self.active_cat_id = self.cat[self.sel_idx]["id"]
                self.sel_idx = 0
                self.state = STATE_OBJ
            elif self.state==STATE_OBJ:
                self.state = STATE_DESC
            elif self.state==STATE_DESC:
                pass  # maybe later expand
        elif key=="back":
            if self.state==STATE_DESC:
                self.state = STATE_OBJ
            elif self.state==STATE_OBJ:
                self.state = STATE_CAT
            else:
                pass
        elif key=="refresh":
            self.load_data()

    def current_list(self):
        if self.state==STATE_CAT: return self.cat
        if self.state==STATE_OBJ: return self.objs_by_cat.get(self.active_cat_id, [])
        return []

# ─── main loop ───────────────────────────────────────────────────────────

def main():
    ui = WorldDexUI()
    while True:
        ui.render()
        key = get_key()
        ui.handle_key(key)
        # auto‑refresh catalog every 30 s
        if time.time() - ui.last_refresh > 30:
            ui.load_data(); ui.last_refresh=time.time()
        time.sleep(0.05)

if __name__ == "__main__":
    try:
        main()
    finally:
        if HW_BUTTONS:
            GPIO.cleanup()
