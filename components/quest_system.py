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
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

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
            description=f"Learn about the {target_obj['name']} by viewing its detailed information",
            type="knowledge",
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
