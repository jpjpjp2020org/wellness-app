import os
import json
import math
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from .models import BulkRecipe

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_embedding(text: str) -> List[float]:
    """Generate embedding for text using OpenAI's text-embedding-ada-002"""
    try:
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return []

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(a * a for a in vec2))
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)

def generate_recipe_embedding(recipe: BulkRecipe) -> List[float]:
    """Generate embedding for a recipe based on name, ingredients, and instructions"""
    # Combine recipe text for embedding
    recipe_text = f"{recipe.meal_name} "
    
    # Add ingredients
    ingredients = recipe.get_ingredients_list()
    for ing in ingredients:
        recipe_text += f"{ing['ingredient']} {ing['measure']} "
    
    # Add instructions (first 500 chars to keep it manageable)
    if recipe.instructions:
        recipe_text += recipe.instructions[:500]
    
    # Add category and area
    if recipe.category:
        recipe_text += f" {recipe.category}"
    if recipe.area:
        recipe_text += f" {recipe.area}"
    
    return generate_embedding(recipe_text)

def search_similar_recipes(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Search for similar recipes using vector similarity"""
    # Generate embedding for query
    query_embedding = generate_embedding(query)
    if not query_embedding:
        return []
    
    # Get all recipes with embeddings
    recipes = BulkRecipe.objects.filter(embedding__isnull=False).exclude(embedding={})
    
    similarities = []
    for recipe in recipes:
        if recipe.embedding:
            similarity = cosine_similarity(query_embedding, recipe.embedding)
            similarities.append({
                'recipe': recipe,
                'similarity': similarity
            })
    
    # Sort by similarity and return top_k
    similarities.sort(key=lambda x: x['similarity'], reverse=True)
    
    results = []
    for item in similarities[:top_k]:
        recipe = item['recipe']
        results.append({
            'id': recipe.id,
            'meal_name': recipe.meal_name,
            'category': recipe.category,
            'area': recipe.area,
            'meal_thumb': recipe.meal_thumb,
            'similarity_score': round(item['similarity'], 3),
            'ingredients': recipe.get_ingredients_list(),
            'instructions': recipe.get_instructions_steps()
        })
    
    return results

# Function calling for nutritional calculations
def calculate_recipe_nutrition(ingredients: List[Dict[str, str]]) -> Dict[str, Any]:
    """Calculate nutrition for a recipe based on ingredients"""
    # This is a simplified calculation - in production you'd use a proper nutrition database
    total_calories = 0
    total_protein = 0
    total_carbs = 0
    total_fat = 0
    
    # Simple ingredient nutrition mapping (very basic)
    nutrition_map = {
        'chicken': {'calories': 165, 'protein': 31, 'carbs': 0, 'fat': 3.6},
        'beef': {'calories': 250, 'protein': 26, 'carbs': 0, 'fat': 15},
        'rice': {'calories': 130, 'protein': 2.7, 'carbs': 28, 'fat': 0.3},
        'pasta': {'calories': 131, 'protein': 5, 'carbs': 25, 'fat': 1.1},
        'tomato': {'calories': 18, 'protein': 0.9, 'carbs': 3.9, 'fat': 0.2},
        'onion': {'calories': 40, 'protein': 1.1, 'carbs': 9.3, 'fat': 0.1},
        'garlic': {'calories': 149, 'protein': 6.4, 'carbs': 33, 'fat': 0.5},
        'olive oil': {'calories': 884, 'protein': 0, 'carbs': 0, 'fat': 100},
        'butter': {'calories': 717, 'protein': 0.9, 'carbs': 0.1, 'fat': 81},
        'egg': {'calories': 155, 'protein': 13, 'carbs': 1.1, 'fat': 11},
        'milk': {'calories': 42, 'protein': 3.4, 'carbs': 5, 'fat': 1},
        'cheese': {'calories': 402, 'protein': 25, 'carbs': 1.3, 'fat': 33},
        'bread': {'calories': 265, 'protein': 9, 'carbs': 49, 'fat': 3.2},
        'potato': {'calories': 77, 'protein': 2, 'carbs': 17, 'fat': 0.1},
        'carrot': {'calories': 41, 'protein': 0.9, 'carbs': 10, 'fat': 0.2},
        'spinach': {'calories': 23, 'protein': 2.9, 'carbs': 3.6, 'fat': 0.4},
        'salmon': {'calories': 208, 'protein': 25, 'carbs': 0, 'fat': 12},
        'tuna': {'calories': 144, 'protein': 30, 'carbs': 0, 'fat': 1},
        'shrimp': {'calories': 99, 'protein': 24, 'carbs': 0.2, 'fat': 0.3},
        'lentil': {'calories': 116, 'protein': 9, 'carbs': 20, 'fat': 0.4},
    }
    
    for ingredient in ingredients:
        ing_name = ingredient['ingredient'].lower()
        # Find matching ingredient in nutrition map
        for key, nutrition in nutrition_map.items():
            if key in ing_name:
                # Estimate quantity (very rough - assume 100g per ingredient)
                quantity_multiplier = 1.0
                if ingredient.get('measure'):
                    measure = ingredient['measure'].lower()
                    if 'g' in measure or 'gram' in measure:
                        try:
                            # Extract number from measure like "200g" -> 200
                            import re
                            numbers = re.findall(r'\d+', measure)
                            if numbers:
                                quantity_multiplier = float(numbers[0]) / 100.0
                        except:
                            pass
                
                total_calories += nutrition['calories'] * quantity_multiplier
                total_protein += nutrition['protein'] * quantity_multiplier
                total_carbs += nutrition['carbs'] * quantity_multiplier
                total_fat += nutrition['fat'] * quantity_multiplier
                break
    
    return {
        'calories': round(total_calories),
        'protein': round(total_protein, 1),
        'carbs': round(total_carbs, 1),
        'fat': round(total_fat, 1)
    }

def generate_rag_recipe_recommendations(user_preferences: Dict[str, Any], num_recommendations: int = 5) -> List[Dict[str, Any]]:
    """Generate personalized recipe recommendations using RAG"""
    
    # Build query based on user preferences
    query_parts = []
    
    if user_preferences.get('dietary_tags'):
        query_parts.extend(user_preferences['dietary_tags'])
    
    if user_preferences.get('preferred_cuisines'):
        query_parts.extend(user_preferences['preferred_cuisines'])
    
    if user_preferences.get('favorite_foods'):
        query_parts.extend(user_preferences['favorite_foods'])
    
    # Create query string
    query = " ".join(query_parts) if query_parts else "healthy dinner recipe"
    
    # Get similar recipes
    similar_recipes = search_similar_recipes(query, top_k=num_recommendations * 2)
    
    # Filter based on dietary restrictions
    filtered_recipes = []
    for recipe in similar_recipes:
        # Simple filtering logic
        if user_preferences.get('allergies'):
            allergies = [a.lower() for a in user_preferences['allergies']]
            ingredients_text = " ".join([ing['ingredient'].lower() for ing in recipe['ingredients']])
            
            # Skip if contains allergens
            if any(allergen in ingredients_text for allergen in allergies):
                continue
        
        # Calculate nutrition for the recipe
        nutrition = calculate_recipe_nutrition(recipe['ingredients'])
        recipe['nutrition'] = nutrition
        
        filtered_recipes.append(recipe)
        
        if len(filtered_recipes) >= num_recommendations:
            break
    
    return filtered_recipes

def update_recipe_embeddings():
    """Update embeddings for all BulkRecipe entries"""
    recipes = BulkRecipe.objects.all()
    updated_count = 0
    
    for recipe in recipes:
        try:
            # Generate embedding
            embedding = generate_recipe_embedding(recipe)
            if embedding:
                recipe.embedding = embedding
                recipe.save()
                updated_count += 1
                print(f"Updated embedding for: {recipe.meal_name}")
        except Exception as e:
            print(f"Error updating embedding for {recipe.meal_name}: {e}")
    
    print(f"Updated embeddings for {updated_count} recipes")
    return updated_count 