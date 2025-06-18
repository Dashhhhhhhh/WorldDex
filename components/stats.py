# stats.py
"""
Statistics System for World-Dex
──────────────────────────────
Tracks and displays user statistics including discovery progress,
quest completion, and achievement metrics.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timedelta

class StatsSystem:
    """Manages user statistics and achievements"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.stats_file = data_dir / "user_stats.json"
        self.stats = self.load_stats()
    
    def load_stats(self) -> Dict:
        """Load user statistics from file"""
        default_stats = {
            "objects_discovered": 0,
            "categories_explored": [],
            "total_quest_points": 0,
            "quests_completed": 0,
            "first_discovery_date": None,
            "last_activity_date": None,
            "discovery_streak": 0,
            "achievements": [],
            "category_progress": {}
        }
        
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    loaded_stats = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    default_stats.update(loaded_stats)
                    return default_stats
            except (json.JSONDecodeError, TypeError) as e:
                print(f"[Stats] Error loading stats: {e}")
        
        return default_stats
    
    def save_stats(self):
        """Save statistics to file"""
        try:
            self.stats["last_activity_date"] = datetime.now().isoformat()
            with open(self.stats_file, 'w') as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            print(f"[Stats] Error saving stats: {e}")
    
    def record_discovery(self, object_name: str, category_id: str):
        """Record a new object discovery"""
        self.stats["objects_discovered"] += 1
        
        # Track category exploration
        if category_id not in self.stats["categories_explored"]:
            self.stats["categories_explored"].append(category_id)
        
        # Update category progress
        if category_id not in self.stats["category_progress"]:
            self.stats["category_progress"][category_id] = {
                "discovered": [],
                "first_discovery": datetime.now().isoformat()
            }
        
        if object_name not in self.stats["category_progress"][category_id]["discovered"]:
            self.stats["category_progress"][category_id]["discovered"].append(object_name)
        
        # Set first discovery date
        if not self.stats["first_discovery_date"]:
            self.stats["first_discovery_date"] = datetime.now().isoformat()
        
        # Update discovery streak (simplified - daily streak)
        today = datetime.now().date().isoformat()
        if self.stats.get("last_discovery_date") != today:
            self.stats["discovery_streak"] += 1
            self.stats["last_discovery_date"] = today
        
        self.check_achievements(category_id)
        self.save_stats()
    
    def record_quest_completion(self, quest_points: int):
        """Record quest completion"""
        self.stats["quests_completed"] += 1
        self.stats["total_quest_points"] += quest_points
        self.save_stats()
    
    def check_achievements(self, category_id: str = None):
        """Check and award achievements"""
        achievements = []
        
        # Discovery milestones
        discovery_milestones = [1, 5, 10, 25, 50, 100]
        for milestone in discovery_milestones:
            achievement_id = f"discover_{milestone}"
            if (self.stats["objects_discovered"] >= milestone and 
                achievement_id not in self.stats["achievements"]):
                achievements.append({
                    "id": achievement_id,
                    "title": f"Explorer {milestone}",
                    "description": f"Discovered {milestone} objects",
                    "earned_date": datetime.now().isoformat()
                })
                self.stats["achievements"].append(achievement_id)
        
        # Category achievements
        if len(self.stats["categories_explored"]) >= 3:
            achievement_id = "multi_category"
            if achievement_id not in self.stats["achievements"]:
                achievements.append({
                    "id": achievement_id,
                    "title": "Diverse Explorer",
                    "description": "Explored 3+ different categories",
                    "earned_date": datetime.now().isoformat()
                })
                self.stats["achievements"].append(achievement_id)
        
        # Quest achievements
        quest_milestones = [1, 5, 10, 25]
        for milestone in quest_milestones:
            achievement_id = f"quest_{milestone}"
            if (self.stats["quests_completed"] >= milestone and 
                achievement_id not in self.stats["achievements"]):
                achievements.append({
                    "id": achievement_id,
                    "title": f"Questmaster {milestone}",
                    "description": f"Completed {milestone} quests",
                    "earned_date": datetime.now().isoformat()
                })
                self.stats["achievements"].append(achievement_id)
        
        # Streak achievements
        if self.stats["discovery_streak"] >= 7:
            achievement_id = "week_streak"
            if achievement_id not in self.stats["achievements"]:
                achievements.append({
                    "id": achievement_id,
                    "title": "Consistent Explorer",
                    "description": "7-day discovery streak",
                    "earned_date": datetime.now().isoformat()
                })
                self.stats["achievements"].append(achievement_id)
        
        return achievements
    
    def get_category_completion(self, all_categories: List[Dict], all_objects: List[Dict]) -> Dict:
        """Get completion percentage for each category"""
        completion = {}
        
        for category in all_categories:
            cat_id = category["id"]
            total_objects = len([obj for obj in all_objects if obj.get("category_id") == cat_id])
            
            if cat_id in self.stats["category_progress"]:
                discovered = len(self.stats["category_progress"][cat_id]["discovered"])
            else:
                discovered = 0
            
            completion[cat_id] = {
                "name": category["name"],
                "discovered": discovered,
                "total": total_objects,
                "percentage": (discovered / max(total_objects, 1)) * 100
            }
        
        return completion
    
    def get_summary_stats(self) -> Dict:
        """Get summary statistics for display"""
        return {
            "objects_discovered": self.stats["objects_discovered"],
            "categories_explored": len(self.stats["categories_explored"]),
            "total_quest_points": self.stats["total_quest_points"],
            "quests_completed": self.stats["quests_completed"],
            "achievements_earned": len(self.stats["achievements"]),
            "discovery_streak": self.stats["discovery_streak"],
            "total_achievements": 15  # Approximate total possible achievements
        }
    
    def get_recent_achievements(self, limit: int = 5) -> List[Dict]:
        """Get recently earned achievements"""
        # This would need achievement details stored with dates
        # For now, return basic info
        recent = []
        achievement_titles = {
            "discover_1": "First Discovery",
            "discover_5": "Explorer 5",
            "discover_10": "Explorer 10",
            "multi_category": "Diverse Explorer",
            "quest_1": "First Quest",
            "week_streak": "Consistent Explorer"
        }
        
        for achievement_id in self.stats["achievements"][-limit:]:
            if achievement_id in achievement_titles:
                recent.append({
                    "id": achievement_id,
                    "title": achievement_titles[achievement_id]
                })
        
        return recent
    
    def reset_stats(self):
        """Reset all statistics (for testing/demo purposes)"""
        self.stats = {
            "objects_discovered": 0,
            "categories_explored": [],
            "total_quest_points": 0,
            "quests_completed": 0,
            "first_discovery_date": None,
            "last_activity_date": None,
            "discovery_streak": 0,
            "achievements": [],
            "category_progress": {}
        }
        self.save_stats()
