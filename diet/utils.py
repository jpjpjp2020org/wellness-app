from collections import defaultdict
import re
from typing import Dict, List, Tuple, Any

# Common ingredient categories for basic matching
INGREDIENT_CATEGORIES = {
    'dairy': ['milk', 'cheese', 'yogurt', 'cream', 'butter'],
    'produce': ['apple', 'banana', 'carrot', 'lettuce', 'tomato', 'onion', 'garlic'],
    'meat': ['chicken', 'beef', 'pork', 'lamb', 'turkey'],
    'pantry': ['flour', 'sugar', 'salt', 'oil', 'vinegar', 'rice', 'pasta'],
    'spices': ['pepper', 'cumin', 'paprika', 'cinnamon', 'oregano']
}

def normalize_ingredient(ingredient: str) -> str:
    """Normalize ingredient name for matching."""
    # Convert to lowercase and remove common prefixes/suffixes
    normalized = ingredient.lower().strip()
    # Remove common words that don't affect matching
    normalized = re.sub(r'\b(fresh|dried|ground|powdered|whole|sliced|chopped)\b', '', normalized)
    # Remove extra whitespace
    normalized = ' '.join(normalized.split())
    return normalized

def parse_measure(measure: str) -> Tuple[float, str]:
    """Parse measurement string into amount and unit."""
    try:
        # Split into amount and unit
        parts = measure.strip().split()
        if not parts:
            return 1.0, ''
            
        # Try to convert first part to float
        amount = float(parts[0])
        # Rest is the unit
        unit = ' '.join(parts[1:]) if len(parts) > 1 else ''
        return amount, unit
    except (ValueError, IndexError):
        # If parsing fails, return default values
        return 1.0, measure

def categorize_ingredient(ingredient: str) -> str:
    """Categorize ingredient into basic food groups."""
    normalized = normalize_ingredient(ingredient)
    
    for category, keywords in INGREDIENT_CATEGORIES.items():
        if any(keyword in normalized for keyword in keywords):
            return category
    return 'other'

def aggregate_ingredients(meal_ingredients: Dict[str, List[Dict[str, str]]], meal_counts: Dict[str, int]) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate ingredients from multiple meals, taking into account how many times each meal appears.
    Returns a dictionary of normalized ingredients with their total amounts and categories.
    """
    # Initialize aggregation structure
    ingredient_totals = defaultdict(lambda: {
        'amount': 0.0,
        'unit': '',
        'category': '',
        'original_names': set(),
        'meals': set()
    })
    
    # First pass: Simple matching and aggregation
    for meal_name, ingredients in meal_ingredients.items():
        # Get the number of times this meal appears in the plan
        meal_count = meal_counts.get(meal_name, 1)
        
        for ing in ingredients:
            # Normalize the ingredient name
            normalized_name = normalize_ingredient(ing['ingredient'])
            # Parse the measure
            amount, unit = parse_measure(ing['measure'])
            
            # Multiply amount by meal count
            total_amount = amount * meal_count
            
            # Update the totals
            ingredient_totals[normalized_name]['amount'] += total_amount
            ingredient_totals[normalized_name]['unit'] = unit or ingredient_totals[normalized_name]['unit']
            ingredient_totals[normalized_name]['category'] = categorize_ingredient(ing['ingredient'])
            ingredient_totals[normalized_name]['original_names'].add(ing['ingredient'])
            ingredient_totals[normalized_name]['meals'].add(meal_name)
    
    # Convert sets to lists for JSON serialization
    for ing_data in ingredient_totals.values():
        ing_data['original_names'] = list(ing_data['original_names'])
        ing_data['meals'] = list(ing_data['meals'])
    
    return dict(ingredient_totals) 