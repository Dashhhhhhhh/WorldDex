# quest_system.py
"""
Quest System for World-Dex
──────────────────────────
Generates dynamic quests based on the catalogued objects, encouraging exploration
and discovery of new items in different categories.

Quest Types:
1. Discovery Quests - Find X items in category Y
2. Collection Quests - Collect all items from a specific category
3. Explorer Quests - Discover items in multiple categories
4. Knowledge Quests - Learn about specific objects
"""

from __future__ import annotations
import json
import random
import time
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

# Add parent directory to path to import OpenAI client
sys.path.append(str(Path(__file__).parent.parent))

try:
    from openai import OpenAI
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    OpenAI = None
    print("[Quest] Warning: OpenAI not available for LLM quest generation")

@dataclass
class Quest:
    """Represents a single quest"""
    id: str
    title: str
    description: str
    type: str  # "discovery", "collection", "explorer", "knowledge"
    target_category: Optional[str] = None
    target_count: int = 1
    target_items: List[str] = None
    progress: int = 0
    completed: bool = False
    created_at: str = ""
    completed_at: Optional[str] = None
    reward_points: int = 10
    
    def __post_init__(self):
        if self.target_items is None:
            self.target_items = []
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

class QuestSystem:
    """Manages quest generation, progress tracking, and completion"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.quest_file = data_dir / "quests.json"
        self.progress_file = data_dir / "quest_progress.json"
        self.quests: List[Quest] = []
        self.user_progress: Dict = {"completed_quests": [], "total_points": 0}
        self.load_quests()
        self.load_progress()
        self.client = self._setup_openai_client()
        
        # Clean up old/duplicate quests and ensure we have exactly 3 active quests
        self._cleanup_duplicate_quests()
        self._maintain_quest_count()
    
    def _setup_openai_client(self):
        """Setup OpenAI client for LLM quest generation"""
        if not OpenAI:
            return None
            
        try:
            # Case-insensitive env lookup
            def env(name: str) -> str | None:
                return os.getenv(name) or os.getenv(name.lower())
            
            openai_key = env("OPENAI_API_KEY")
            openai_base = env("OPENAI_API_BASE") or "https://api.openai.com/v1"
            deepseek_key = env("DEEPSEEK_API_KEY")  
            deepseek_base = env("DEEPSEEK_API_BASE") or "https://api.deepseek.com/v1"
            
            if openai_key:
                return OpenAI(api_key=openai_key, base_url=openai_base)
            elif deepseek_key:
                return OpenAI(api_key=deepseek_key, base_url=deepseek_base)
            else:
                print("[Quest] No API keys found for LLM quest generation")
                return None
        except Exception as e:
            print(f"[Quest] Error setting up OpenAI client: {e}")
            return None
    
    def load_quests(self):
        """Load existing quests from file"""
        if self.quest_file.exists():
            try:
                with open(self.quest_file, 'r') as f:
                    quest_data = json.load(f)
                    self.quests = [Quest(**q) for q in quest_data]
            except (json.JSONDecodeError, TypeError) as e:
                print(f"[Quest] Error loading quests: {e}")
                self.quests = []
    
    def save_quests(self):
        """Save quests to file"""
        try:
            quest_data = [asdict(q) for q in self.quests]
            with open(self.quest_file, 'w') as f:
                json.dump(quest_data, f, indent=2)
        except Exception as e:
            print(f"[Quest] Error saving quests: {e}")
    
    def load_progress(self):
        """Load user progress from file"""
        if self.progress_file.exists():
            try:
                with open(self.progress_file, 'r') as f:
                    self.user_progress = json.load(f)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"[Quest] Error loading progress: {e}")
    
    def save_progress(self):
        """Save user progress to file"""
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(self.user_progress, f, indent=2)
        except Exception as e:
            print(f"[Quest] Error saving progress: {e}")
    
    def generate_discovery_quest(self, categories: List[Dict], objects: List[Dict]) -> Quest:
        """Generate a quest to discover items in a category"""
        if not categories:
            return None
            
        category = random.choice(categories)
        cat_objects = [obj for obj in objects if obj.get("category_id") == category["id"]]
        
        # Vary the target count based on category size
        max_target = min(len(cat_objects), 5)
        target_count = random.randint(1, max(1, max_target))
        
        quest_id = f"discovery_{category['id']}_{int(time.time())}"
        
        return Quest(
            id=quest_id,
            title=f"Explore {category['name']}",
            description=f"Discover {target_count} different {category['name'].lower()} in your area",
            type="discovery",
            target_category=category["id"],
            target_count=target_count,
            reward_points=target_count * 5
        )
    
    def generate_collection_quest(self, categories: List[Dict], objects: List[Dict]) -> Quest:
        """Generate a quest to collect all items from a category"""
        if not categories:
            return None
            
        # Prefer smaller categories for collection quests
        small_categories = [cat for cat in categories 
                           if len([obj for obj in objects if obj.get("category_id") == cat["id"]]) <= 3]
        
        if small_categories:
            category = random.choice(small_categories)
        else:
            category = random.choice(categories)
        
        cat_objects = [obj for obj in objects if obj.get("category_id") == category["id"]]
        
        quest_id = f"collection_{category['id']}_{int(time.time())}"
        
        return Quest(
            id=quest_id,
            title=f"Master of {category['name']}",
            description=f"Complete your {category['name'].lower()} collection by finding all known species",
            type="collection",
            target_category=category["id"],
            target_count=len(cat_objects),
            target_items=[obj["name"] for obj in cat_objects],
            reward_points=len(cat_objects) * 10
        )
    
    def generate_explorer_quest(self, categories: List[Dict]) -> Quest:
        """Generate a quest to explore multiple categories"""
        if len(categories) < 2:
            return None
            
        target_categories = random.sample(categories, min(3, len(categories)))
        
        quest_id = f"explorer_{int(time.time())}"
        
        return Quest(
            id=quest_id,
            title="World Explorer",
            description=f"Discover at least one item from each: {', '.join([cat['name'] for cat in target_categories])}",
            type="explorer",
            target_count=len(target_categories),
            target_items=[cat["id"] for cat in target_categories],
            reward_points=len(target_categories) * 15
        )
    
    def generate_knowledge_quest(self, objects: List[Dict]) -> Quest:
        """Generate a quest to learn about specific objects"""
        if not objects:
            return None
            
        # Pick objects with good descriptions
        detailed_objects = [obj for obj in objects 
                           if obj.get("description") and len(obj["description"]) > 50]
        
        if detailed_objects:
            target_obj = random.choice(detailed_objects)
        else:
            target_obj = random.choice(objects)
        
        quest_id = f"knowledge_{target_obj['name'].replace(' ', '_')}_{int(time.time())}"
        
        return Quest(
            id=quest_id,
            title=f"Study the {target_obj['name']}",
            description=f"Learn about the {target_obj['name']} by viewing its detailed information",            type="knowledge",
            target_items=[target_obj["name"]],
            target_count=1,
            reward_points=5
        )
    
    def generate_daily_quests(self, categories: List[Dict], objects: List[Dict], count: int = 3) -> List[Quest]:
        """Generate a set of daily quests"""
        if not categories or not objects:
            return []
        
        new_quests = []
        quest_generators = [
            self.generate_discovery_quest,
            self.generate_collection_quest,
            self.generate_explorer_quest,
            self.generate_knowledge_quest,
        ]
        
        for _ in range(count):
            generator = random.choice(quest_generators)
            try:
                if generator == self.generate_explorer_quest:
                    quest = generator(categories)
                elif generator == self.generate_knowledge_quest:
                    quest = generator(objects)
                else:
                    quest = generator(categories, objects)
                
                if quest and not any(q.id == quest.id for q in self.quests):
                    new_quests.append(quest)
            except Exception as e:
                print(f"[Quest] Error generating quest: {e}")
                continue
        
        return new_quests
    
    def generate_llm_quest(self, categories: List[Dict], objects: List[Dict]) -> Optional[Quest]:
        """Generate a quest using LLM"""
        if not self.client:
            print("[Quest] LLM client not available, falling back to template quest")
            return self.generate_fallback_quest(categories, objects)
        
        try:
            # Get context about available categories and objects
            category_names = [cat["name"] for cat in categories]
            object_samples = [obj["name"] for obj in objects[:10]]  # First 10 objects as examples
            
            system_prompt = """You are a quest generator for World-Dex, a nature discovery app. 
Generate engaging quests that encourage users to explore and discover objects in the natural world.

Quest types available:
- Discovery: Find X items in a category
- Collection: Collect all items from a category  
- Explorer: Discover items across multiple categories
- Knowledge: Learn about specific objects

Respond with a JSON object containing:
{
  "title": "Quest title",
  "description": "Quest description", 
  "type": "discovery|collection|explorer|knowledge",
  "target_category": "category_id or null",
  "target_count": number,
  "target_items": ["item1", "item2"] or [],
  "reward_points": number
}

Make quests fun, educational, and achievable. Points should be 5-20 based on difficulty."""

            user_prompt = f"""Generate a quest based on these available categories: {', '.join(category_names)}
Example objects in the catalog: {', '.join(object_samples)}

Create an engaging quest that will motivate users to explore nature and discover new objects."""

            response = self.client.chat.completions.create(
                model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )
            
            quest_data = json.loads(response.choices[0].message.content.strip())
            
            # Create quest object
            quest_id = f"llm_{quest_data['type']}_{int(time.time())}"
            quest = Quest(
                id=quest_id,
                title=quest_data["title"],
                description=quest_data["description"],
                type=quest_data["type"],
                target_category=quest_data.get("target_category"),
                target_count=quest_data.get("target_count", 1),
                target_items=quest_data.get("target_items", []),
                reward_points=quest_data.get("reward_points", 10)
            )
            
            print(f"[Quest] Generated LLM quest: {quest.title}")
            return quest
            
        except Exception as e:
            print(f"[Quest] Error generating LLM quest: {e}")
            return self.generate_fallback_quest(categories, objects)
    
    def generate_fallback_quest(self, categories: List[Dict], objects: List[Dict]) -> Optional[Quest]:
        """Generate a fallback quest when LLM is not available"""
        if not categories:
            return None
            
        # Simple fallback - always generate a discovery quest
        category = random.choice(categories)
        target_count = random.randint(1, 3)
        
        quest_id = f"fallback_discovery_{category['id']}_{int(time.time())}"
        
        return Quest(
            id=quest_id,
            title=f"Discover {category['name']}",
            description=f"Find {target_count} different {category['name'].lower()} in your area",
            type="discovery", 
            target_category=category["id"],
            target_count=target_count,            reward_points=target_count * 5
        )
    
    def _cleanup_duplicate_quests(self):
        """Remove duplicate or excessive quests"""
        # Remove duplicate quests (same id)
        seen_ids = set()
        unique_quests = []
        
        for quest in self.quests:
            if quest.id not in seen_ids:
                unique_quests.append(quest)
                seen_ids.add(quest.id)
        
        self.quests = unique_quests
        
        # If there are too many active quests, mark the oldest as completed  
        active_quests = self.get_active_quests()
        if len(active_quests) > 3:
            active_quests.sort(key=lambda q: q.created_at)
            excess_quests = active_quests[3:]  # Remove all but the newest 3
            
            for quest in excess_quests:
                quest.completed = True
                quest.completed_at = datetime.now().isoformat()
                print(f"[Quest] Cleaned up old quest: {quest.title}")
        
        self.save_quests()
    
    def _maintain_quest_count(self):
        """Ensure there are always exactly 3 active quests"""
        active_quests = self.get_active_quests()
        target_count = 3
        
        # If we have more than target_count active quests, remove the oldest ones
        if len(active_quests) > target_count:
            # Sort by creation time and keep the newest ones
            active_quests.sort(key=lambda q: q.created_at, reverse=True)
            quests_to_remove = active_quests[target_count:]
            
            for quest in quests_to_remove:
                quest.completed = True
                quest.completed_at = datetime.now().isoformat()
                print(f"[Quest] Removed old quest: {quest.title}")
            
            self.save_quests()
            active_quests = self.get_active_quests()
        
        # If we have fewer than target_count active quests, add new ones
        if len(active_quests) < target_count:
            # Load categories and objects for quest generation
            categories = self._load_categories()
            objects = self._load_objects()
            
            quests_needed = target_count - len(active_quests)
            
            for _ in range(quests_needed):
                # Try to generate an LLM quest first, fall back to template if needed
                new_quest = self.generate_llm_quest(categories, objects)
                if new_quest:
                    self.quests.append(new_quest)
                    print(f"[Quest] Added new quest: {new_quest.title}")
            
            if quests_needed > 0:
                self.save_quests()
    
    def _load_categories(self) -> List[Dict]:
        """Load all categories from data files"""
        categories = []
        try:
            for json_file in self.data_dir.glob("*.json"):
                if json_file.name in ["quests.json", "quest_progress.json", "user_stats.json"]:
                    continue
                
                category_id = json_file.stem
                category_name = category_id.replace("_", " ").title()
                categories.append({
                    "id": category_id,
                    "name": category_name
                })
        except Exception as e:
            print(f"[Quest] Error loading categories: {e}")
        
        return categories
    
    def _load_objects(self) -> List[Dict]:
        """Load all objects from data files"""
        objects = []
        try:
            for json_file in self.data_dir.glob("*.json"):
                if json_file.name in ["quests.json", "quest_progress.json", "user_stats.json"]:
                    continue
                
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    category_id = json_file.stem
                    
                    for item in data:
                        if isinstance(item, dict):
                            objects.append({
                                "name": item["name"],
                                "description": item.get("description", ""),
                                "category_id": category_id
                            })
                        elif isinstance(item, str):                            objects.append({
                                "name": item,
                                "description": "",
                                "category_id": category_id
                            })
        except Exception as e:
            print(f"[Quest] Error loading objects: {e}")
        
        return objects
    
    def update_quest_progress(self, new_object_name: str, category_id: str):
        """Update quest progress when a new object is discovered"""
        updated_quests = []
        
        for quest in self.quests:
            if quest.completed:
                continue
                
            if quest.type == "discovery" and quest.target_category == category_id:
                quest.progress = min(quest.progress + 1, quest.target_count)
                if quest.progress >= quest.target_count:
                    self.complete_quest(quest)
                updated_quests.append(quest)
            
            elif quest.type == "collection" and quest.target_category == category_id:
                if new_object_name in quest.target_items:
                    quest.progress = min(quest.progress + 1, quest.target_count)
                    if quest.progress >= quest.target_count:
                        self.complete_quest(quest)
                updated_quests.append(quest)
            
            elif quest.type == "explorer" and category_id in quest.target_items:
                # Mark this category as discovered
                if category_id not in getattr(quest, 'discovered_categories', []):
                    if not hasattr(quest, 'discovered_categories'):
                        quest.discovered_categories = []
                    quest.discovered_categories.append(category_id)
                    quest.progress = len(quest.discovered_categories)
                    if quest.progress >= quest.target_count:
                        self.complete_quest(quest)
                updated_quests.append(quest)
            
            elif quest.type == "knowledge" and new_object_name in quest.target_items:
                quest.progress = 1
                self.complete_quest(quest)
                updated_quests.append(quest)
        
        if updated_quests:
            self.save_quests()
            self.save_progress()
    
    def complete_quest(self, quest: Quest):
        """Mark a quest as completed and award points"""
        quest.completed = True
        quest.completed_at = datetime.now().isoformat()
        
        self.user_progress["completed_quests"].append(quest.id)
        self.user_progress["total_points"] += quest.reward_points
        
        print(f"[Quest] Quest completed: {quest.title} (+{quest.reward_points} points!)")
        
        # Automatically generate a new quest to maintain 3 active quests
        self._maintain_quest_count()
    
    def get_active_quests(self) -> List[Quest]:
        """Get all active (non-completed) quests"""
        return [q for q in self.quests if not q.completed]
    
    def get_completed_quests(self) -> List[Quest]:
        """Get all completed quests"""
        return [q for q in self.quests if q.completed]
    
    def add_quests(self, new_quests: List[Quest]):
        """Add new quests to the system"""
        self.quests.extend(new_quests)
        self.save_quests()
    
    def cleanup_old_quests(self, max_age_days: int = 7):
        """Remove old completed quests"""
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        self.quests = [q for q in self.quests 
                      if not q.completed or 
                      (q.completed_at and datetime.fromisoformat(q.completed_at) > cutoff_date)]
        
        self.save_quests()
    
    def get_user_stats(self) -> Dict:
        """Get user statistics"""
        active_quests = self.get_active_quests()
        completed_quests = self.get_completed_quests()
        
        return {
            "total_points": self.user_progress.get("total_points", 0),
            "active_quests": len(active_quests),
            "completed_quests": len(completed_quests),
            "completion_rate": len(completed_quests) / max(len(self.quests), 1) * 100 if self.quests else 0
        }
