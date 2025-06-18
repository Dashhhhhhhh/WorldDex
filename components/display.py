# world_dex_display.py
"""
World-Dex handheld UI for a 240 × 240 ST7789 IPS display
────────────────────────────────────────────────────────
• **No command-line arguments needed** – the script boots straight into a
  mini-World-Dex UI:

      1. Category list     (e.g. "Trees", "Minerals")
      2. Object list       (items you have scanned in that category)
      3. Detail sheet      (facts for a single object; scrolls if long)

• Works **both** with real SPI hardware (ST7789) **and** on any desktop via a
  Pygame emulator (default when run on Windows/macOS or when the env-var
  `USE_EMULATOR=1`).

• Reads your catalog from individual category JSON files in the data directory
  (e.g., `DATA_DIR/trees.json`, `DATA_DIR/minerals.json`) – the exact same
  files that **main.py** (TinyDB) writes.

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
"""

from __future__ import annotations
import os, sys, time, json, textwrap, contextlib, platform
from pathlib import Path
from typing import List, Dict

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# ─── Config / env ─────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# Smart data directory resolution
import os
current_dir = os.getcwd()
env_data_dir = os.getenv("DATA_DIR", "./data")

# If we're in components directory and env says "./data", adjust to "../data"
if current_dir.endswith("components") and env_data_dir == "./data":
    DATA_DIR = Path("../data")
else:
    DATA_DIR = Path(env_data_dir)

USE_EMU  = os.getenv("USE_EMULATOR") == "1" or platform.system() in {"Windows", "Darwin"}

WIDTH, HEIGHT = 240, 240
BORDER   = 6
LINE_GAP = 2
FONT_SZ  = int(os.getenv("FONT_SIZE", "18"))

# ─── Read catalog straight from TinyDB-style JSON files ──────────────────
def load_catalog() -> Dict:
    """
    Load every category JSON file in DATA_DIR and return:

        {
          "categories": [ {id, name}, … ],
          "objects":    [ {name, facts, category_id, …}, … ]
        }    • Supports the **TinyDB** schema produced by main.py:
        {"objects": {"1": {...}, "2": {...}}}

    • Also supports the original flat list schema:
        {"objects": [{...}, {...}]}    • Also supports direct list format:
        [{...}, {...}]
    """
    categories, all_objects = [], []

    if not DATA_DIR.exists():
        return {"categories": [], "objects": []}

    # Exclude quest and stats files from catalog loading
    excluded_files = {"quests.json", "quest_progress.json", "user_stats.json"}
    
    for json_file in DATA_DIR.glob("*.json"):
        if json_file.name in excluded_files:
            continue
        cat_id   = json_file.stem                    # e.g. "trees"
        cat_name = cat_id.replace("_", " ").title()  # "Trees"

        try:
            with json_file.open() as fp:
                raw = json.load(fp)

            # Handle different data formats:
            # TinyDB table            → dict with objects property: {"objects": {"1": {...}, "2": {...}}}
            # Hand-made / legacy file → dict with objects list: {"objects": [{...}, {...}]}
            # Direct list file        → list directly: [{...}, {...}]
            if isinstance(raw, list):
                # Direct list format
                objects_iter = raw
            elif isinstance(raw, dict) and "objects" in raw:
                # Dict with objects property
                objects_data = raw["objects"]
                objects_iter = (
                    objects_data.values()
                    if isinstance(objects_data, dict)
                    else objects_data if isinstance(objects_data, list)
                    else []
                )
            else:
                # Unknown format, skip
                objects_iter = []

            categories.append({"id": cat_id, "name": cat_name})

            for obj in objects_iter:
                if not isinstance(obj, dict) or "name" not in obj:
                    continue
                o = obj.copy()
                o["category_id"] = cat_id
                all_objects.append(o)

        except (json.JSONDecodeError, OSError) as e:
            print(f"[World-Dex] ⚠️  Skipping {json_file}: {e}")

    categories.sort(key=lambda c: c["name"].lower())
    all_objects.sort(key=lambda o: o["name"].lower())
    return {"categories": categories, "objects": all_objects}

# ─── Index objects by category for quick lookup ──────────────────────────
def build_lookup(cat: List[Dict], objs: List[Dict]):
    by_cat: Dict[str, List[Dict]] = {c["id"]: [] for c in cat}
    for o in objs:
        by_cat.setdefault(o["category_id"], []).append(o)
    for k in by_cat:
        by_cat[k].sort(key=lambda x: x["name"].lower())
    return by_cat

# ─── Display backend (hardware or emulator) ──────────────────────────────
def init_display():
    """Return (device, draw_ctx) where draw_ctx yields a Pillow draw."""
    if USE_EMU:
        from luma.emulator.device import pygame as emu
        dev = emu(width=WIDTH, height=HEIGHT)

        @contextlib.contextmanager
        def _ctx():
            img = Image.new("RGB", (WIDTH, HEIGHT), "black")
            yield ImageDraw.Draw(img)
            dev.display(img)

        return dev, _ctx

    # ── Real SPI hardware ───────────────────────────────────────────────
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

# ─── Font (cross-platform) ───────────────────────────────────────────────
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

# ─── Input handling (GPIO or Pygame) ─────────────────────────────────────
try:
    import RPi.GPIO as GPIO
    HW_BUTTONS = True and not USE_EMU
except (RuntimeError, ModuleNotFoundError):
    HW_BUTTONS = False

BTN_UP, BTN_DN, BTN_OK, BTN_BACK = (5, 6, 13, 19)

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
                if event.key == pygame.K_UP:                    return "up"
                if event.key == pygame.K_DOWN:                  return "down"
                if event.key in (pygame.K_RETURN, pygame.K_SPACE): return "ok"
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE): return "back"
    return None

# ─── UI states ───────────────────────────────────────────────────────────
STATE_MAIN_MENU, STATE_CAT, STATE_OBJ, STATE_DESC, STATE_QUEST_MENU, STATE_QUEST_LIST, STATE_QUEST_DETAIL, STATE_STATS = range(8)

# Import quest system and stats
try:
    from .quest_system import QuestSystem
    from .stats import StatsSystem
except ImportError:
    # Running as script, use absolute import
    from quest_system import QuestSystem
    from stats import StatsSystem

class WorldDexUI:
    def __init__(self):
        self.state = STATE_MAIN_MENU  # Start with main menu
        self.sel_idx = 0             # highlighted index in current list
        self.cat:  List[Dict] = []
        self.obj:  List[Dict] = []
        self.objs_by_cat = {}
        self.active_cat_id: str | None = None
        self.quest_system = QuestSystem(DATA_DIR)
        self.stats_system = StatsSystem(DATA_DIR)
        self.current_quest = None    # Currently selected quest
        self.quest_list_type = "active"  # "active" or "completed"
        self.load_data()
        self.last_refresh = time.time()
        
        # Generate initial quests if none exist
        if not self.quest_system.get_active_quests():
            self.generate_daily_quests()

    def load_data(self):
        data = load_catalog()
        self.cat = data["categories"]
        self.obj = data["objects"]
        self.objs_by_cat = build_lookup(self.cat, self.obj)

    def generate_daily_quests(self):
        """Generate new daily quests"""
        new_quests = self.quest_system.generate_daily_quests(self.cat, self.obj)
        if new_quests:
            self.quest_system.add_quests(new_quests)

    def get_main_menu_items(self):
        """Get main menu options"""
        return [
            {"id": "catalog", "name": "📚 Catalog"},
            {"id": "quests", "name": "⚔️ Quests"},
            {"id": "stats", "name": "📊 Stats"}
        ]

    def get_quest_menu_items(self):
        """Get quest menu options"""
        active_quests = self.quest_system.get_active_quests()
        completed_quests = self.quest_system.get_completed_quests()
        
        items = []
        items.append({"id": "active", "name": f"Active ({len(active_quests)})"})
        items.append({"id": "completed", "name": f"Completed ({len(completed_quests)})"})
        items.append({"id": "generate", "name": "🔄 New Quests"})
        return items

    def get_current_quest_list(self):
        """Get the current list of quests to display"""
        menu_items = self.get_quest_menu_items()
        
        if self.sel_idx < len(menu_items):
            selected_item = menu_items[self.sel_idx]
            if selected_item["id"] == "active":
                return self.quest_system.get_active_quests()
            elif selected_item["id"] == "completed":
                return self.quest_system.get_completed_quests()
        return []

    # ── Rendering helpers ────────────────────────────────────────────
    def write_line(self, draw, y, txt, highlight=False):
        fill = (0, 255, 0) if highlight else (255, 255, 255)
        draw.text((BORDER, y), txt, font=FONT, fill=fill)

    def render(self):
        with canvas() as draw:
            draw.rectangle((0, 0, WIDTH, HEIGHT), fill="black")
            draw.text((BORDER, 2), "World-Dex", fill=(255, 0, 0), font=FONT)
            y = BORDER + LINE_H

            if self.state == STATE_MAIN_MENU:
                menu_items = self.get_main_menu_items()
                for i, item in enumerate(menu_items):
                    self.write_line(draw, y, item["name"], i == self.sel_idx)
                    y += LINE_H

            elif self.state == STATE_CAT:
                for i, cat in enumerate(self.cat):
                    self.write_line(draw, y, cat["name"], i == self.sel_idx)
                    y += LINE_H

            elif self.state == STATE_OBJ:
                objs = self.objs_by_cat.get(self.active_cat_id, [])
                for i, o in enumerate(objs):
                    self.write_line(draw, y, o["name"], i == self.sel_idx)
                    y += LINE_H

            elif self.state == STATE_DESC:
                obj = self.get_current_obj()
                if obj:
                    # Try different field names for the description/facts
                    description = obj.get("description") or obj.get("facts") or "(no description available)"
                    if isinstance(description, list):
                        # If facts is a list, join the first few items
                        description = "\n".join(description[:3])
                    wrapper = textwrap.TextWrapper(width=30)
                    lines = wrapper.wrap(f"{obj['name']}: {description}")
                else:
                    lines = ["(no data)"]
                
                for ln in lines:
                    if y > HEIGHT - LINE_H:
                        break
                    self.write_line(draw, y, ln)
                    y += LINE_H

            elif self.state == STATE_QUEST_MENU:
                quest_menu_items = self.get_quest_menu_items()
                for i, item in enumerate(quest_menu_items):
                    self.write_line(draw, y, item["name"], i == self.sel_idx)
                    y += LINE_H
                
                # Show user stats at the bottom
                stats = self.quest_system.get_user_stats()
                stats_y = HEIGHT - LINE_H * 2
                self.write_line(draw, stats_y, f"Points: {stats['total_points']}")

            elif self.state == STATE_QUEST_LIST:
                # Show list of quests (active or completed)
                quest_list = self.get_current_quest_list()
                title = f"{self.quest_list_type.title()} Quests ({len(quest_list)})"
                self.write_line(draw, y, title, True)
                y += LINE_H * 2
                
                for i, quest in enumerate(quest_list):
                    status = "✓" if quest.completed else f"{quest.progress}/{quest.target_count}"
                    quest_text = f"{quest.title} [{status}]"
                    self.write_line(draw, y, quest_text, i == self.sel_idx)
                    y += LINE_H
                    if y > HEIGHT - LINE_H:
                        break

            elif self.state == STATE_QUEST_DETAIL:
                if self.current_quest:
                    quest = self.current_quest
                    # Show quest title
                    self.write_line(draw, y, quest.title, True)
                    y += LINE_H * 2
                    
                    # Show quest description (wrapped)
                    wrapper = textwrap.TextWrapper(width=28)
                    desc_lines = wrapper.wrap(quest.description)
                    for line in desc_lines:
                        if y > HEIGHT - LINE_H * 3:
                            break
                        self.write_line(draw, y, line)
                        y += LINE_H
                    
                    # Show progress
                    y += LINE_H
                    progress_text = f"Progress: {quest.progress}/{quest.target_count}"
                    if quest.completed:
                        progress_text += " ✓"
                    self.write_line(draw, y, progress_text)
                      # Show reward
                    y += LINE_H
                    self.write_line(draw, y, f"Reward: {quest.reward_points} pts")

            elif self.state == STATE_STATS:
                # Display user statistics
                stats = self.stats_system.stats
                
                self.write_line(draw, y, "📊 Your Statistics", True)
                y += LINE_H * 2
                
                # Basic stats
                self.write_line(draw, y, f"Objects Found: {stats['objects_discovered']}")
                y += LINE_H
                
                self.write_line(draw, y, f"Categories: {len(stats['categories_explored'])}")
                y += LINE_H
                
                self.write_line(draw, y, f"Quests Done: {stats['quests_completed']}")
                y += LINE_H
                
                self.write_line(draw, y, f"Quest Points: {stats['total_quest_points']}")
                y += LINE_H
                
                self.write_line(draw, y, f"Discovery Streak: {stats['discovery_streak']}")
                y += LINE_H * 2
                
                # Recent achievements
                if stats['achievements']:
                    self.write_line(draw, y, "Recent Achievements:")
                    y += LINE_H
                    # Show last 2 achievements if any
                    recent_achievements = stats['achievements'][-2:]
                    for achievement_id in recent_achievements:
                        # Format achievement name
                        name = achievement_id.replace('_', ' ').title()
                        self.write_line(draw, y, f"• {name}")
                        y += LINE_H
                        if y > HEIGHT - LINE_H:
                            break
                obj = self.get_current_obj()
                if obj:
                    # Try different field names for the description/facts
                    description = obj.get("description") or obj.get("facts") or "(no description available)"
                    if isinstance(description, list):
                        # If facts is a list, join the first few items
                        description = "\n".join(description[:3])
                    wrapper = textwrap.TextWrapper(width=30)
                    lines = wrapper.wrap(f"{obj['name']}: {description}")
                else:
                    lines = ["(no data)"]
                
                for ln in lines:
                    if y > HEIGHT - LINE_H:
                        break
                    self.write_line(draw, y, ln)
                    y += LINE_H

    # ── Helpers ─────────────────────────────────────────────────────
    def get_current_obj(self):
        if self.active_cat_id is None:
            return None
        objs = self.objs_by_cat.get(self.active_cat_id, [])
        if not objs:
            return None
        return objs[self.sel_idx]    # ── Input handling ───────────────────────────────────────────────
    def handle_key(self, key):
        if key is None:
            return

        if key in {"up", "down"}:
            max_idx = len(self.current_list()) - 1
            if max_idx < 0:
                return
            self.sel_idx = (self.sel_idx + (-1 if key == "up" else 1)) % (max_idx + 1)

        elif key == "ok":
            if self.state == STATE_MAIN_MENU:
                menu_items = self.get_main_menu_items()
                if self.sel_idx < len(menu_items):
                    selected = menu_items[self.sel_idx]
                    if selected["id"] == "catalog":
                        self.state = STATE_CAT
                        self.sel_idx = 0
                    elif selected["id"] == "quests":
                        self.state = STATE_QUEST_MENU
                        self.sel_idx = 0
                    elif selected["id"] == "stats":
                        # Show stats screen
                        self.state = STATE_STATS
                        self.sel_idx = 0

            elif self.state == STATE_CAT and self.cat and self.sel_idx < len(self.cat):
                self.active_cat_id = self.cat[self.sel_idx]["id"]
                self.sel_idx = 0
                self.state = STATE_OBJ

            elif self.state == STATE_OBJ:
                # Update quest progress when viewing an object
                objs = self.objs_by_cat.get(self.active_cat_id, [])
                if self.sel_idx < len(objs):
                    obj = objs[self.sel_idx]
                    self.quest_system.update_quest_progress(obj["name"], self.active_cat_id)                    # Record discovery for stats
                    self.stats_system.record_discovery(obj["name"], self.active_cat_id)
                self.state = STATE_DESC

            elif self.state == STATE_QUEST_MENU:
                quest_menu_items = self.get_quest_menu_items()
                if self.sel_idx < len(quest_menu_items):
                    selected = quest_menu_items[self.sel_idx]
                    if selected["id"] == "generate":
                        self.generate_daily_quests()
                    elif selected["id"] in ["active", "completed"]:
                        quests = self.get_current_quest_list()
                        if quests:
                            self.current_quest = quests[0]
                            self.state = STATE_QUEST_DETAIL
                            self.sel_idx = 0

        elif key == "back":
            if self.state == STATE_DESC:
                self.state = STATE_OBJ
            elif self.state == STATE_OBJ:
                self.state = STATE_CAT
            elif self.state == STATE_CAT:
                self.state = STATE_MAIN_MENU
                self.sel_idx = 0
            elif self.state == STATE_QUEST_DETAIL:
                self.state = STATE_QUEST_MENU
                self.current_quest = None
                self.sel_idx = 0
            elif self.state == STATE_QUEST_MENU:
                self.state = STATE_MAIN_MENU
                self.sel_idx = 0
            elif self.state == STATE_STATS:
                self.state = STATE_MAIN_MENU
                self.sel_idx = 0

        elif key == "refresh":
            self.load_data()

    def current_list(self):
        if self.state == STATE_MAIN_MENU:
            return self.get_main_menu_items()
        elif self.state == STATE_CAT:
            return self.cat
        elif self.state == STATE_OBJ:
            return self.objs_by_cat.get(self.active_cat_id, [])
        elif self.state == STATE_QUEST_MENU:
            return self.get_quest_menu_items()
        elif self.state == STATE_QUEST_DETAIL:
            return self.get_current_quest_list()
        elif self.state == STATE_STATS:
            return []  # Stats screen doesn't have a list
        return []

# ─── Main loop ───────────────────────────────────────────────────────────
def main():
    ui = WorldDexUI()
    while True:
        ui.render()
        key = get_key()
        ui.handle_key(key)

        # auto-refresh catalog every 30 s
        if time.time() - ui.last_refresh > 30:
            ui.load_data()
            ui.last_refresh = time.time()

        time.sleep(0.05)

if __name__ == "__main__":
    try:
        main()
    finally:
        if HW_BUTTONS:
            GPIO.cleanup()
