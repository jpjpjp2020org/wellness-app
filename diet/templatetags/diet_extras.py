from django import template
from django.template.defaultfilters import stringfilter
import json

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using bracket notation"""
    try:
        return dictionary.get(key, 0)  # Return 0 if key doesn't exist
    except (AttributeError, KeyError, TypeError):
        return 0  # Return 0 for any errors

@register.filter
def multiply(value, arg):
    """Multiply the value by the argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def divide(value, arg):
    """Divide the value by the argument"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def subtract(value, arg):
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def percentage_of(value, total):
    try:
        return (float(value) / float(total)) * 100
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def calculate_daily_totals(day_meals):
    totals = {
        'calories': 0,
        'protein': 0,
        'carbs': 0,
        'fats': 0
    }
    
    if not day_meals:
        return totals
        
    for meal_type in ['breakfast', 'lunch', 'dinner', 'snack']:
        meal = day_meals.get(meal_type)
        if meal and meal.get('macros'):
            macros = meal['macros']
            servings = meal.get('recommended_servings') or 1
            portion_multiplier = meal.get('portion_multiplier', 1.0)
            
            try:
                servings = float(servings)
                if servings <= 0:
                    servings = 1
            except Exception:
                servings = 1
                
            try:
                portion_multiplier = float(portion_multiplier)
                if portion_multiplier <= 0:
                    portion_multiplier = 1.0
            except Exception:
                portion_multiplier = 1.0
            
            # Calculate adjusted nutrition: (base nutrition / servings) * portion_multiplier
            adjusted_calories = (float(macros.get('calories', 0)) / servings) * portion_multiplier
            adjusted_protein = (float(macros.get('protein', 0)) / servings) * portion_multiplier
            adjusted_carbs = (float(macros.get('carbs', 0)) / servings) * portion_multiplier
            adjusted_fats = (float(macros.get('fat', 0)) / servings) * portion_multiplier
            
            totals['calories'] += adjusted_calories
            totals['protein'] += adjusted_protein
            totals['carbs'] += adjusted_carbs
            totals['fats'] += adjusted_fats
    return totals 