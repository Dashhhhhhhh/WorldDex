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
import os, sys, time, json, textwrap, contextlib, platform, threading
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
BORDER   = 8
MARGIN   = 4
LINE_GAP = 3
FONT_SZ  = int(os.getenv("FONT_SIZE", "16"))
TITLE_FONT_SZ = int(os.getenv("TITLE_FONT_SIZE", "20"))

# Modern color palette
COLORS = {
    'bg': (18, 18, 18),           # Dark background
    'surface': (32, 32, 32),      # Card/surface background
    'primary': (102, 187, 255),   # Bright blue
    'secondary': (153, 153, 153), # Light gray
    'accent': (255, 107, 107),    # Coral red
    'success': (67, 217, 107),    # Green
    'warning': (255, 183, 77),    # Orange
    'text': (255, 255, 255),      # White text
    'text_dim': (170, 170, 170),  # Dimmed text
    'selected': (255, 255, 255),  # Selected text
    'selected_bg': (102, 187, 255), # Selected background
}

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
            print(f"[World-Dex] WARNING: Skipping {json_file}: {e}")

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
def load_font(size=None):
    if size is None:
        size = FONT_SZ
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
    ):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

FONT = load_font()
TITLE_FONT = load_font(TITLE_FONT_SZ)
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
                if event.key == pygame.K_r:                     return "refresh"
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
        self.scroll_offset = 0       # offset for scrolling lists
        self.cat:  List[Dict] = []
        self.obj:  List[Dict] = []
        self.objs_by_cat = {}
        self.active_cat_id: str | None = None
        self.quest_system = QuestSystem(DATA_DIR)
        self.stats_system = StatsSystem(DATA_DIR)
        self.current_quest = None    # Currently selected quest
        self.quest_list_type = "active"  # "active" or "completed"
        
        # Threading support for non-blocking data loading
        self._loading = False
        self._loading_lock = threading.Lock()
        
        self.load_data()
        # Generate initial quests if none exist - quest system now auto-maintains 3 quests
        # No manual generation needed as the QuestSystem automatically maintains exactly 3 active quests
    
    def load_data(self):
        data = load_catalog()
        self.cat = data["categories"]
        self.obj = data["objects"]
        self.objs_by_cat = build_lookup(self.cat, self.obj)
    
    def get_main_menu_items(self):
        """Get main menu options"""
        return [
            {"id": "catalog", "name": "Catalog"},
            {"id": "quests", "name": "Quests"},
            {"id": "stats", "name": "Stats"}
        ]
    
    def get_quest_menu_items(self):
        """Get quest menu options"""
        active_quests = self.quest_system.get_active_quests()
        completed_quests = self.quest_system.get_completed_quests()
        
        items = []
        items.append({"id": "active", "name": f"Active ({len(active_quests)})"})
        items.append({"id": "completed", "name": f"Completed ({len(completed_quests)})"})
        # Removed "New Quests" button - quests are automatically managed
        return items
    
    def get_current_quest_list(self):
        """Get the current list of quests to display"""
        if self.quest_list_type == "active":
            return self.quest_system.get_active_quests()
        elif self.quest_list_type == "completed":
            return self.quest_system.get_completed_quests()
        return []

    def get_max_visible_items(self):
        """Calculate maximum number of items that can be displayed on screen"""
        # Header takes up space (title + subtitle + separator)
        header_height = TITLE_FONT.getbbox("Test")[3] + LINE_H + MARGIN * 4
        available_height = HEIGHT - header_height - BORDER * 2
        item_height = LINE_H + MARGIN * 2 + MARGIN  # Item height plus spacing
        return max(1, available_height // item_height)
    
    def update_scroll_offset(self, list_length):
        """Update scroll offset to ensure selected item is visible"""
        if list_length == 0:
            self.scroll_offset = 0
            return
            
        max_visible = self.get_max_visible_items()
        
        # If all items fit on screen, no scrolling needed
        if list_length <= max_visible:
            self.scroll_offset = 0
            return
        
        # Ensure selected item is visible
        if self.sel_idx < self.scroll_offset:
            # Selected item is above visible area, scroll up
            self.scroll_offset = self.sel_idx
        elif self.sel_idx >= self.scroll_offset + max_visible:
            # Selected item is below visible area, scroll down
            self.scroll_offset = self.sel_idx - max_visible + 1
          # Clamp scroll offset to valid range
        self.scroll_offset = max(0, min(self.scroll_offset, list_length - max_visible))
    
    def get_visible_items(self, items_list):
        """Get the subset of items that should be visible on screen"""
        if not items_list:
            return [], 0
        
        max_visible = self.get_max_visible_items()
        start_idx = self.scroll_offset
        end_idx = min(start_idx + max_visible, len(items_list))
        return items_list[start_idx:end_idx], start_idx

    # ── Rendering helpers ────────────────────────────────────────────
    def draw_card(self, draw, x, y, width, height, color=None):
        """Draw a modern card with subtle shadow"""
        if color is None:
            color = COLORS['surface']
        # Shadow
        draw.rectangle((x+1, y+1, x+width+1, y+height+1), fill=(0, 0, 0, 50))
        # Card
        draw.rectangle((x, y, x+width, y+height), fill=color)
    
    def draw_header(self, draw, title, subtitle=None):
        """Draw a modern header with title and optional subtitle"""
        y = BORDER
        # Title
        draw.text((BORDER, y), title, fill=COLORS['primary'], font=TITLE_FONT)
        y += TITLE_FONT.getbbox(title)[3] + MARGIN
        
        # Subtitle
        if subtitle:
            draw.text((BORDER, y), subtitle, fill=COLORS['text_dim'], font=FONT)
            y += LINE_H
        
        # Separator line
        draw.line((BORDER, y + MARGIN, WIDTH - BORDER, y + MARGIN), fill=COLORS['secondary'], width=1)
        return y + MARGIN * 2
    
    def draw_list_item(self, draw, x, y, text, selected=False, icon=None, secondary_text=None):
        """Draw a modern list item with optional icon and secondary text"""
        item_height = LINE_H + MARGIN * 2
        
        # Background for selected item
        if selected:
            self.draw_card(draw, x, y, WIDTH - x * 2, item_height, COLORS['selected_bg'])
        
        text_x = x + MARGIN
        text_y = y + MARGIN
        
        # Icon
        if icon:
            draw.text((text_x, text_y), icon, fill=COLORS['accent'], font=FONT)
            text_x += FONT.getbbox(icon)[2] + MARGIN
        
        # Main text
        text_color = COLORS['selected'] if selected else COLORS['text']
        draw.text((text_x, text_y), text, fill=text_color, font=FONT)
        
        # Secondary text (right-aligned)
        if secondary_text:
            sec_width = FONT.getbbox(secondary_text)[2]
            sec_x = WIDTH - BORDER - sec_width
            sec_color = COLORS['selected'] if selected else COLORS['text_dim']
            draw.text((sec_x, text_y), secondary_text, fill=sec_color, font=FONT)
        
        return y + item_height + MARGIN
    
    def draw_progress_bar(self, draw, x, y, width, progress, total, color=None):
        """Draw a modern progress bar"""
        if color is None:
            color = COLORS['primary']
        
        height = 4
        # Background
        draw.rectangle((x, y, x + width, y + height), fill=COLORS['surface'])
        # Progress
        if total > 0:
            progress_width = int(width * progress / total)
            draw.rectangle((x, y, x + progress_width, y + height), fill=color)
        
        return y + height + MARGIN
    
    def draw_badge(self, draw, x, y, text, color=None):
        """Draw a small badge with text"""
        if color is None:
            color = COLORS['accent']
        
        text_width = FONT.getbbox(text)[2]
        badge_width = text_width + MARGIN * 2
        badge_height = LINE_H
        
        # Badge background
        draw.rectangle((x, y, x + badge_width, y + badge_height), fill=color)
          # Badge text
        draw.text((x + MARGIN, y + 2), text, fill=COLORS['text'], font=FONT)
        
        return x + badge_width + MARGIN

    def draw_scroll_indicator(self, draw, total_items, visible_count, start_idx):
        """Draw a scroll indicator on the right side of the screen"""
        if total_items <= visible_count:
            return  # No scrolling needed
        
        # Scroll bar dimensions
        bar_width = 3
        bar_x = WIDTH - BORDER - bar_width
        bar_y = 60  # Start below header
        bar_height = HEIGHT - bar_y - BORDER
        
        # Background track
        draw.rectangle((bar_x, bar_y, bar_x + bar_width, bar_y + bar_height), 
                      fill=COLORS['surface'])
        
        # Calculate scroll thumb position and size
        thumb_height = max(10, int(bar_height * visible_count / total_items))
        thumb_y = bar_y + int(bar_height * start_idx / total_items)
        
        # Ensure thumb doesn't go out of bounds
        if thumb_y + thumb_height > bar_y + bar_height:
            thumb_y = bar_y + bar_height - thumb_height
        
        # Draw scroll thumb
        draw.rectangle((bar_x, thumb_y, bar_x + bar_width, thumb_y + thumb_height), 
                      fill=COLORS['primary'])
        
        # Optional: Show current position text
        position_text = f"{start_idx + 1}-{min(start_idx + visible_count, total_items)} of {total_items}"
        text_width = FONT.getbbox(position_text)[2]
        text_x = WIDTH - BORDER - text_width
        text_y = HEIGHT - BORDER - LINE_H
        draw.text((text_x, text_y), position_text, fill=COLORS['text_dim'], font=FONT)

    def render(self):
        # Check for refresh signal from main.py before rendering
        if self._check_refresh_signal():
            self.load_data_async()  # Use async loading to avoid blocking GUI
            
        with canvas() as draw:
            # Modern dark background
            draw.rectangle((0, 0, WIDTH, HEIGHT), fill=COLORS['bg'])
            
            # Show loading indicator if data is being refreshed
            with self._loading_lock:
                is_loading = self._loading
            if is_loading:
                loading_text = "Refreshing data..."
                text_width = FONT.getbbox(loading_text)[2]
                text_x = WIDTH - BORDER - text_width
                text_y = HEIGHT - BORDER - LINE_H
                draw.text((text_x, text_y), loading_text, fill=COLORS['primary'], font=FONT)
            
            if self.state == STATE_MAIN_MENU:
                y = self.draw_header(draw, "WorldDex", "Your field companion")
                
                menu_items = self.get_main_menu_items()
                for i, item in enumerate(menu_items):
                    y = self.draw_list_item(draw, BORDER, y, item["name"], i == self.sel_idx, None)

            elif self.state == STATE_CAT:
                y = self.draw_header(draw, "Categories", f"{len(self.cat)} categories")
                
                # Update scroll and get visible items
                self.update_scroll_offset(len(self.cat))
                visible_cats, start_idx = self.get_visible_items(self.cat)
                
                for i, cat in enumerate(visible_cats):
                    actual_idx = start_idx + i
                    count = len(self.objs_by_cat.get(cat["id"], []))
                    secondary = f"{count} items" if count != 1 else "1 item"
                    y = self.draw_list_item(draw, BORDER, y, cat["name"], actual_idx == self.sel_idx, 
                                          None, secondary)
                
                # Draw scroll indicator if needed
                if len(self.cat) > self.get_max_visible_items():
                    self.draw_scroll_indicator(draw, len(self.cat), len(visible_cats), start_idx)

            elif self.state == STATE_OBJ:
                cat_name = next((c["name"] for c in self.cat if c["id"] == self.active_cat_id), "Unknown")
                objs = self.objs_by_cat.get(self.active_cat_id, [])
                y = self.draw_header(draw, cat_name, f"{len(objs)} objects")
                
                # Update scroll and get visible items
                self.update_scroll_offset(len(objs))
                visible_objs, start_idx = self.get_visible_items(objs)
                
                for i, obj in enumerate(visible_objs):
                    actual_idx = start_idx + i
                    y = self.draw_list_item(draw, BORDER, y, obj["name"], actual_idx == self.sel_idx, None)
                
                # Draw scroll indicator if needed
                if len(objs) > self.get_max_visible_items():
                    self.draw_scroll_indicator(draw, len(objs), len(visible_objs), start_idx)

            elif self.state == STATE_DESC:
                obj = self.get_current_obj()
                if obj:
                    y = self.draw_header(draw, obj['name'], "Details")
                    
                    # Description in a card
                    description = obj.get("description") or obj.get("facts") or "(no description available)"
                    if isinstance(description, list):
                        description = "\n".join(description[:3])
                    
                    # Word wrap for description
                    wrapper = textwrap.TextWrapper(width=28)
                    lines = wrapper.wrap(description)
                    
                    card_height = len(lines) * LINE_H + MARGIN * 2
                    self.draw_card(draw, BORDER, y, WIDTH - BORDER * 2, card_height)
                    
                    desc_y = y + MARGIN
                    for line in lines:
                        if desc_y > HEIGHT - LINE_H * 2:
                            break
                        draw.text((BORDER + MARGIN, desc_y), line, fill=COLORS['text'], font=FONT)
                        desc_y += LINE_H

            elif self.state == STATE_QUEST_MENU:
                quest_menu_items = self.get_quest_menu_items()
                stats = self.quest_system.get_user_stats()
                
                y = self.draw_header(draw, "Quests", f"{stats['total_points']} points earned")
                
                for i, item in enumerate(quest_menu_items):
                    y = self.draw_list_item(draw, BORDER, y, item["name"], i == self.sel_idx, None)

            elif self.state == STATE_QUEST_LIST:
                quest_list = self.get_current_quest_list()
                title = f"{self.quest_list_type.title()} Quests"
                y = self.draw_header(draw, title, f"{len(quest_list)} quests")
                
                # Update scroll and get visible items
                self.update_scroll_offset(len(quest_list))
                visible_quests, start_idx = self.get_visible_items(quest_list)
                
                for i, quest in enumerate(visible_quests):
                    actual_idx = start_idx + i
                    progress_text = f"{quest.progress}/{quest.target_count}"
                    y = self.draw_list_item(draw, BORDER, y, quest.title, actual_idx == self.sel_idx, 
                                          None, progress_text)
                
                # Draw scroll indicator if needed
                if len(quest_list) > self.get_max_visible_items():
                    self.draw_scroll_indicator(draw, len(quest_list), len(visible_quests), start_idx)

            elif self.state == STATE_QUEST_DETAIL:
                if self.current_quest:
                    quest = self.current_quest
                    y = self.draw_header(draw, quest.title, f"{quest.reward_points} points")
                    
                    # Quest description card
                    wrapper = textwrap.TextWrapper(width=26)
                    desc_lines = wrapper.wrap(quest.description)
                    card_height = len(desc_lines) * LINE_H + MARGIN * 3
                    
                    self.draw_card(draw, BORDER, y, WIDTH - BORDER * 2, card_height)
                    
                    desc_y = y + MARGIN
                    for line in desc_lines:
                        if desc_y > HEIGHT - LINE_H * 4:
                            break
                        draw.text((BORDER + MARGIN, desc_y), line, fill=COLORS['text'], font=FONT)
                        desc_y += LINE_H
                    
                    y = desc_y + MARGIN * 2
                    
                    # Progress bar
                    if not quest.completed:
                        draw.text((BORDER, y), "Progress:", fill=COLORS['text_dim'], font=FONT)
                        y += LINE_H
                        y = self.draw_progress_bar(draw, BORDER, y, WIDTH - BORDER * 2, 
                                                 quest.progress, quest.target_count)

            elif self.state == STATE_STATS:
                stats = self.stats_system.stats
                y = self.draw_header(draw, "Statistics", "Your progress")
                
                # Stats cards
                stats_data = [
                    ("Objects", str(stats['objects_discovered']), COLORS['primary']),
                    ("Categories", str(len(stats['categories_explored'])), COLORS['success']),
                    ("Quests", str(stats['quests_completed']), COLORS['warning']),
                    ("Points", str(stats['total_quest_points']), COLORS['accent'])
                ]
                
                # Draw stats in a 2x2 grid
                card_width = (WIDTH - BORDER * 3 - MARGIN) // 2
                card_height = LINE_H * 2 + MARGIN * 2
                
                for i, (label, value, color) in enumerate(stats_data):
                    x = BORDER + (i % 2) * (card_width + MARGIN)
                    card_y = y + (i // 2) * (card_height + MARGIN)
                    
                    self.draw_card(draw, x, card_y, card_width, card_height, COLORS['surface'])
                    
                    # Value (large)
                    value_font = load_font(24)
                    draw.text((x + MARGIN, card_y + MARGIN), value, fill=color, font=value_font)
                    
                    # Label (small)
                    draw.text((x + MARGIN, card_y + MARGIN + 26), label,                             fill=COLORS['text_dim'], font=FONT)

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
                    status = "DONE" if quest.completed else f"{quest.progress}/{quest.target_count}"
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
                        progress_text += " DONE"
                    self.write_line(draw, y, progress_text)
                      # Show reward
                    y += LINE_H
                    self.write_line(draw, y, f"Reward: {quest.reward_points} pts")

            elif self.state == STATE_STATS:
                # Display user statistics
                stats = self.stats_system.stats
                
                self.write_line(draw, y, "Your Statistics", True)
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
        """Get the currently selected object in the active category"""
        if self.active_cat_id is None:
            return None
        objs = self.objs_by_cat.get(self.active_cat_id, [])
        if not objs or self.sel_idx >= len(objs):
            return None
        return objs[self.sel_idx]

    # ── Input handling ───────────────────────────────────────────────
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
                        self.scroll_offset = 0
                    elif selected["id"] == "quests":
                        self.state = STATE_QUEST_MENU
                        self.sel_idx = 0
                        self.scroll_offset = 0
                    elif selected["id"] == "stats":
                        # Show stats screen
                        self.state = STATE_STATS
                        self.sel_idx = 0
                        self.scroll_offset = 0
            
            elif self.state == STATE_CAT and self.cat and self.sel_idx < len(self.cat):
                self.active_cat_id = self.cat[self.sel_idx]["id"]
                self.sel_idx = 0
                self.scroll_offset = 0
                self.state = STATE_OBJ
            
            elif self.state == STATE_OBJ:                # Update quest progress when viewing an object
                objs = self.objs_by_cat.get(self.active_cat_id, [])
                if self.sel_idx < len(objs):
                    obj = objs[self.sel_idx]
                    # Update progress asynchronously to avoid GUI lag
                    self.async_update_progress(obj["name"], self.active_cat_id)
                self.state = STATE_DESC
            
            elif self.state == STATE_QUEST_MENU:
                quest_menu_items = self.get_quest_menu_items()
                if self.sel_idx < len(quest_menu_items):
                    selected = quest_menu_items[self.sel_idx]
                    # Removed generate button handling - quests are automatically managed
                    if selected["id"] in ["active", "completed"]:
                        self.quest_list_type = selected["id"]  # Set the quest list type
                        self.state = STATE_QUEST_LIST  # Go to quest list, not directly to detail
                        self.sel_idx = 0
                        self.scroll_offset = 0
            
            elif self.state == STATE_QUEST_LIST:
                # Select a quest from the list to view details
                quest_list = self.get_current_quest_list()
                if self.sel_idx < len(quest_list):
                    self.current_quest = quest_list[self.sel_idx]
                    self.state = STATE_QUEST_DETAIL
                    self.sel_idx = 0
        
        elif key == "back":
            if self.state == STATE_DESC:
                self.state = STATE_OBJ
            elif self.state == STATE_OBJ:
                self.state = STATE_CAT
                self.scroll_offset = 0
            elif self.state == STATE_CAT:
                self.state = STATE_MAIN_MENU
                self.sel_idx = 0
                self.scroll_offset = 0
            elif self.state == STATE_QUEST_DETAIL:
                self.state = STATE_QUEST_LIST  # Go back to quest list instead of quest menu
                self.current_quest = None
                self.sel_idx = 0
                self.scroll_offset = 0
            elif self.state == STATE_QUEST_LIST:
                self.state = STATE_QUEST_MENU  # Go back to quest menu
                self.sel_idx = 0
                self.scroll_offset = 0
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
        elif self.state == STATE_QUEST_LIST:
            return self.get_current_quest_list()
        elif self.state == STATE_STATS:
            return []  # Stats screen doesn't have a list
        return []

    def _check_refresh_signal(self):
        """Check if main.py has created a refresh signal"""
        signal_file = DATA_DIR / ".refresh_signal"
        if signal_file.exists():
            try:
                signal_file.unlink()  # Remove the signal file
                return True
            except OSError:
                pass  # File might be in use, try again next time
        return False

    def _background_load_data(self):
        """Load data in background thread to avoid blocking GUI"""
        try:
            # Load catalog data
            data = load_catalog()
            
            # Load quest and stats data
            self.quest_system.load_quests()
            self.quest_system.load_progress() 
            self.stats_system.load_stats()
            
            # Update UI data atomically
            with self._loading_lock:
                self.cat = data["categories"]
                self.obj = data["objects"]
                self.objs_by_cat = build_lookup(self.cat, self.obj)
                self._loading = False
                
        except Exception as e:
            print(f"[WorldDex] Error loading data in background: {e}")
            with self._loading_lock:
                self._loading = False
    
    def load_data_async(self):
        """Trigger background data loading if not already loading"""
        with self._loading_lock:
            if not self._loading:
                self._loading = True
                thread = threading.Thread(target=self._background_load_data, daemon=True)
                thread.start()
    
    def async_update_progress(self, obj_name, category_id):
        """Asynchronously update quest progress and stats to avoid GUI lag"""
        def update_in_background():
            try:
                self.quest_system.update_quest_progress(obj_name, category_id)
                self.stats_system.record_discovery(obj_name, category_id)
            except Exception as e:
                print(f"[Display] Error updating progress in background: {e}")
        
        # Start background thread for progress update
        thread = threading.Thread(target=update_in_background, daemon=True)
        thread.start()

# ─── Main loop ───────────────────────────────────────────────────────────
def main():
    ui = WorldDexUI()
    
    # Refresh all data at startup
    ui.load_data()
    ui.quest_system.load_quests()
    ui.quest_system.load_progress()
    ui.stats_system.load_stats()
    ui._check_refresh_signal()  # Clear any leftover refresh signals
    
    while True:
        ui.render()
        key = get_key()
        ui.handle_key(key)
        time.sleep(0.05)

if __name__ == "__main__":
    try:
        main()
    finally:
        if HW_BUTTONS:
            GPIO.cleanup()
