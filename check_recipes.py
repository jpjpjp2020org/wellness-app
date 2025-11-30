#!/usr/bin/env python
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'well.settings')
django.setup()

from diet.models import BulkRecipe

# Check what we have
recipe = BulkRecipe.objects.first()
if recipe:
    print("=== RECIPE STRUCTURE ===")
    print(f"Name: {recipe.meal_name}")
    print(f"Category: {recipe.category}")
    print(f"Area: {recipe.area}")
    print(f"Ingredients count: {len(recipe.get_ingredients_list())}")
    print(f"First 3 ingredients: {recipe.get_ingredients_list()[:3]}")
    print(f"Instructions length: {len(recipe.instructions)}")
    print(f"Raw data keys: {list(recipe.raw_mealdb_data.keys())[:10]}")
    
    print("\n=== SAMPLE INGREDIENTS ===")
    for i, ing in enumerate(recipe.get_ingredients_list()[:5]):
        print(f"{i+1}. {ing['measure']} {ing['ingredient']}")
    
    print(f"\n=== TOTAL RECIPES: {BulkRecipe.objects.count()} ===")
else:
    print("No recipes found in database") 