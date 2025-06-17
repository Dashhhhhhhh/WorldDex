#!/usr/bin/env python3
"""
WorldDex Category Generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Procedurally generates category JSON files for the WorldDex system.

Each category file contains:
- name: Display name of the category
- description: Brief description of the category
- objects: Array of objects in this category
  - id: Unique identifier (category_###)
  - name: Object name
  - fingerprint: Simple 5-element array for similarity matching
  - thumbnail_url: Example image URL
  - date_first_seen: ISO timestamp
  - facts: Array of facts about the object
"""

import json
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Category templates for procedural generation
CATEGORY_TEMPLATES = {
    "plants": {
        "name": "Plants",
        "description": "Living organisms that produce their own food through photosynthesis",
        "objects": [
            {"name": "Fern", "facts": ["Ancient plant group", "Reproduces via spores", "Thrives in moist environments"]},
            {"name": "Moss", "facts": ["Non-vascular plant", "Grows in dense mats", "Absorbs water through leaves"]},
            {"name": "Cactus", "facts": ["Succulent plant", "Stores water in stems", "Adapted to arid conditions"]},
            {"name": "Orchid", "facts": ["Diverse flowering plant family", "Complex flower structures", "Many are epiphytes"]},
        ]
    },
    "fungi": {
        "name": "Fungi",
        "description": "Organisms that decompose organic matter and form networks",
        "objects": [
            {"name": "Mushroom", "facts": ["Fruiting body of fungi", "Contains spores", "Important decomposer"]},
            {"name": "Lichen", "facts": ["Symbiotic organism", "Fungi and algae partnership", "Pioneer species"]},
            {"name": "Mold", "facts": ["Multicellular fungi", "Grows on organic matter", "Important in decomposition"]},
            {"name": "Yeast", "facts": ["Single-celled fungi", "Used in baking and brewing", "Ferments sugars"]},
        ]
    },
    "marine_life": {
        "name": "Marine Life",
        "description": "Organisms that live in saltwater environments",
        "objects": [
            {"name": "Jellyfish", "facts": ["Cnidarian with no brain", "95% water", "Ancient ocean dweller"]},
            {"name": "Coral", "facts": ["Colonial marine organism", "Builds calcium carbonate structures", "Symbiotic with algae"]},
            {"name": "Starfish", "facts": ["Echinoderm with radial symmetry", "Can regenerate lost limbs", "Marine predator"]},
            {"name": "Sea Anemone", "facts": ["Cnidarian polyp", "Sessile marine animal", "Stinging tentacles"]},
        ]
    },
    "reptiles": {
        "name": "Reptiles",
        "description": "Cold-blooded vertebrates with scaled skin",
        "objects": [
            {"name": "Lizard", "facts": ["Scaled reptile", "Can shed tail when threatened", "Basks in sun for warmth"]},
            {"name": "Snake", "facts": ["Legless reptile", "Flexible jaw structure", "Sheds skin as it grows"]},
            {"name": "Turtle", "facts": ["Reptile with protective shell", "Can live over 100 years", "Lays eggs on land"]},
            {"name": "Gecko", "facts": ["Small lizard", "Excellent climbers", "Many species are nocturnal"]},
        ]
    },
    "amphibians": {
        "name": "Amphibians",
        "description": "Vertebrates that live both in water and on land",
        "objects": [
            {"name": "Frog", "facts": ["Tailless amphibian", "Undergoes metamorphosis", "Breathes through skin"]},
            {"name": "Salamander", "facts": ["Tailed amphibian", "Can regenerate limbs", "Moist skin"]},
            {"name": "Toad", "facts": ["Warty-skinned amphibian", "Dry skin compared to frogs", "Terrestrial lifestyle"]},
            {"name": "Newt", "facts": ["Semi-aquatic salamander", "Smooth skin", "Complex life cycle"]},
        ]
    },
    "mammals": {
        "name": "Mammals",
        "description": "Warm-blooded vertebrates with hair or fur",
        "objects": [
            {"name": "Squirrel", "facts": ["Rodent with bushy tail", "Hoards nuts for winter", "Excellent climber"]},
            {"name": "Rabbit", "facts": ["Lagomorph with long ears", "Herbivorous diet", "Rapid reproduction"]},
            {"name": "Bat", "facts": ["Flying mammal", "Uses echolocation", "Nocturnal lifestyle"]},
            {"name": "Deer", "facts": ["Hoofed mammal", "Males have antlers", "Herbivorous grazer"]},
        ]
    },
    "crystals": {
        "name": "Crystals",
        "description": "Solid materials with ordered atomic structure",
        "objects": [
            {"name": "Amethyst", "facts": ["Purple variety of quartz", "Semi-precious gemstone", "Formed in geodes"]},
            {"name": "Diamond", "facts": ["Hardest natural material", "Made of carbon atoms", "Precious gemstone"]},
            {"name": "Ruby", "facts": ["Red variety of corundum", "Very hard mineral", "Precious gemstone"]},
            {"name": "Emerald", "facts": ["Green variety of beryl", "Precious gemstone", "Often has inclusions"]},
        ]
    },
    "weather": {
        "name": "Weather Phenomena",
        "description": "Atmospheric conditions and events",
        "objects": [
            {"name": "Lightning", "facts": ["Electrical discharge", "Extremely hot plasma", "Follows conductive paths"]},
            {"name": "Rainbow", "facts": ["Optical phenomenon", "Caused by light refraction", "Appears after rain"]},
            {"name": "Tornado", "facts": ["Rotating column of air", "Forms during thunderstorms", "Can be extremely destructive"]},
            {"name": "Aurora", "facts": ["Light display in polar regions", "Caused by solar particles", "Creates colorful curtains"]},
        ]
    }
}

def generate_object_data(template_obj: Dict[str, Any], category_id: str, index: int) -> Dict[str, Any]:
    """Generate a complete object entry from a template"""
    
    # Generate a unique ID
    obj_id = f"{category_id}_{index:03d}"
    
    # Generate simple 5-element fingerprint (consistent with flowers.json/birds.json format)
    # Use deterministic seed based on object name for consistency
    seed = abs(hash(template_obj['name'] + category_id)) % (2**31)
    random.seed(seed)
    fingerprint = [round(random.uniform(0, 1), 3) for _ in range(5)]
    
    # Generate random date within the last 30 days
    base_date = datetime.now() - timedelta(days=random.randint(0, 30))
    date_str = base_date.isoformat()
    
    # Build facts with discovery date
    facts = [f"{template_obj['name']} was first scanned on {base_date.strftime('%B %d %Y')}."]
    facts.extend(template_obj.get('facts', []))
    
    return {
        "id": obj_id,
        "name": template_obj['name'],
        "fingerprint": fingerprint,
        "thumbnail_url": f"https://example.com/{template_obj['name'].lower().replace(' ', '_')}.jpg",
        "date_first_seen": date_str,
        "facts": facts
    }

def generate_category_file(category_id: str, template: Dict[str, Any], output_dir: Path):
    """Generate a complete category JSON file"""
    
    # Generate objects from template
    objects = []
    for i, obj_template in enumerate(template['objects']):
        obj_data = generate_object_data(obj_template, category_id, i + 1)
        objects.append(obj_data)
    
    # Add some random variations
    num_variants = random.randint(1, 3)
    for i in range(num_variants):
        base_obj = random.choice(template['objects'])
        variant_name = f"{base_obj['name']} Variant {i+1}"
        variant_template = {
            "name": variant_name,
            "facts": [f"Variant of {base_obj['name']}", "Slightly different characteristics"] + base_obj['facts'][:2]
        }
        variant_data = generate_object_data(variant_template, category_id, len(objects) + 1)
        objects.append(variant_data)
    
    # Create category file
    category_data = {
        "name": template['name'],
        "description": template['description'],
        "objects": objects
    }
    
    # Write to file
    output_file = output_dir / f"{category_id}.json"
    with output_file.open('w') as f:
        json.dump(category_data, f, indent=2)
    
    print(f"✅ Generated {category_id}.json with {len(objects)} objects")

def main():
    """Generate all category files"""
    print("🌍 WorldDex Category Generator")
    print("=" * 35)
    
    # Create data directory if it doesn't exist
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    # Clean up old generated files (keep manually created ones)
    generated_files = [
        "plants.json", "fungi.json", "marine_life.json", "reptiles.json",
        "amphibians.json", "mammals.json", "crystals.json", "weather.json"
    ]
    
    for filename in generated_files:
        file_path = data_dir / filename
        if file_path.exists():
            file_path.unlink()
            print(f"🗑️  Removed old {filename}")
    
    # Generate new category files
    print("\n🔄 Generating new categories...")
    for category_id, template in CATEGORY_TEMPLATES.items():
        generate_category_file(category_id, template, data_dir)
    
    print(f"\n🎉 Generated {len(CATEGORY_TEMPLATES)} category files!")
    print(f"📁 Files saved to: {data_dir.absolute()}")
    
    # List all category files
    print(f"\n📋 Available categories:")
    for json_file in sorted(data_dir.glob("*.json")):
        try:
            with json_file.open() as f:
                data = json.load(f)
            name = data.get('name', json_file.stem)
            obj_count = len(data.get('objects', []))
            print(f"   • {name} ({obj_count} objects)")
        except Exception as e:
            print(f"   • {json_file.stem} (error: {e})")
    
    print(f"\n🖥️  To test the display:")
    print(f"   python tools/led_display.py")

if __name__ == "__main__":
    main()
