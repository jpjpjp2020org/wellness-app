from django.shortcuts import render, redirect
from .models import Ingredient, Recipe, RecipeIngredient, UserMealPlan, UserDietaryPreferences, UserSavedMeal, PlannedMeal, BulkRecipe, MealPlanVersion, NutritionAdherenceSnapshot, ShoppingListVersion
from health.models import HealthProfile
from django.contrib.auth.decorators import login_required
from datetime import date, timedelta, datetime
from collections import defaultdict
from .forms import PreferenceStepForm
from . import ai
from django.db import transaction
from django.http import JsonResponse, HttpResponseRedirect
from decouple import config
import json
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from .usda_client import USDAClient
import requests
from django.contrib import messages
from .utils import aggregate_ingredients
from django.urls import reverse
import threading
from django.views.decorators.csrf import csrf_exempt
import random
from django.utils import timezone
import uuid

# USDA FoodData Central API configuration
USDA_API_KEY = config('USDA_API_KEY')
USDA_API_BASE_URL = 'https://api.nal.usda.gov/fdc/v1'

# NB UserMealPlan.plan_json to be clean and hierarchical, NB - pretty much restructuring and repurposing most of infra
# NB the 3step form will generate structured snapshot of diet - the actual food recommendations will come after that, when sending the structured data back - avoids garbage in - garbage out scenario

@login_required
def diet_entry(request):
    user = request.user
    prefs, _ = UserDietaryPreferences.objects.get_or_create(user=user)
    context = {
        "prefs": prefs,
        "current_step": request.session.get("diet_step", 1)
    }

    # Load health data from Project 1
    try:
        hp = HealthProfile.objects.get(user=user)
        context["health_goals"] = hp.assessment_data
    except HealthProfile.DoesNotExist:
        context["health_goals"] = {}

    if request.method == "POST":
        form = PreferenceStepForm(request.POST)
        if form.is_valid():
            user_input = form.cleaned_data["user_input"]
            step = int(request.POST.get("step", 1))
            
            try:
                with transaction.atomic():
                    if step == 1:
                        result = ai.process_dietary_restrictions(user_input)
                        prefs.dietary_tags = result["dietary_tags"]
                        prefs.allergies = result["allergies"]
                        prefs.dislikes = result["dislikes"]
                        request.session["diet_step"] = 2
                        context["current_step"] = 2
                        
                    elif step == 2:
                        result = ai.process_cuisine_preferences(user_input)
                        prefs.preferred_cuisines = result["preferred_cuisines"]
                        request.session["diet_step"] = 3
                        context["current_step"] = 3
                        
                    elif step == 3:
                        result = ai.process_meal_timing(user_input)
                        prefs.meals_per_day = result["meals_per_day"]
                        prefs.preferred_meal_times = result["meal_times"]
                        request.session.pop("diet_step", None)
                        context["current_step"] = "complete"

                    prefs.save()
                    context["message"] = "Step {} completed successfully.".format(step)
                    
                    if context["current_step"] == "complete":
                        context["ready_for_planning"] = True
                        
            except Exception as e:
                context["error"] = f"Error processing step {step}: {str(e)}"
                context["current_step"] = step

    context["form"] = PreferenceStepForm()
    return render(request, "diet/diet_entry.html", context)

@login_required
def reset_preferences(request):
    """Allow users to restart the preference collection process."""
    if request.method == "POST":
        request.session["diet_step"] = 1
        UserDietaryPreferences.objects.filter(user=request.user).delete()
    return redirect("diet:diet_entry")

@login_required
def meal_planning(request):
    """Basic meal planning view to test the flow."""
    user = request.user
    try:
        prefs = UserDietaryPreferences.objects.get(user=user)
        health_profile = HealthProfile.objects.get(user=user)
        
        # Generate meal planning analysis if not already done
        if not prefs.meal_planning_analysis:
            analysis = ai.process_meal_planning_analysis(
                health_data=health_profile.assessment_data,
                diet_prefs={
                    'dietary_tags': prefs.dietary_tags,
                    'allergies': prefs.allergies,
                    'preferred_cuisines': prefs.preferred_cuisines,
                    'meals_per_day': prefs.meals_per_day
                }
            )
            prefs.meal_planning_analysis = analysis
            
            # Generate meal baseline using the analysis
            baseline = ai.generate_meal_baseline(
                analysis_result=analysis,
                diet_prefs={
                    'dietary_tags': prefs.dietary_tags,
                    'preferred_cuisines': prefs.preferred_cuisines,
                    'meals_per_day': prefs.meals_per_day
                }
            )
            prefs.meal_baseline = baseline
            prefs.save()

    except (UserDietaryPreferences.DoesNotExist, HealthProfile.DoesNotExist):
        return redirect("diet:diet_entry")

    context = {
        "prefs": prefs,
        "health_goals": health_profile.assessment_data if health_profile else {},
        "debug_info": {
            "dietary_tags": prefs.dietary_tags,
            "allergies": prefs.allergies,
            "dislikes": prefs.dislikes,
            "recommended_cuisines": prefs.preferred_cuisines,
            "meals_per_day": prefs.meals_per_day,
            "meal_times": prefs.preferred_meal_times
        },
        "meal_analysis": prefs.meal_planning_analysis,
        "meal_baseline": prefs.meal_baseline
    }
    
    return render(request, "diet/meal_planning.html", context)

@login_required
def specific_meals(request):
    """View for specific meal planning and food search."""
    user = request.user
    try:
        prefs = UserDietaryPreferences.objects.get(user=user)
        health_profile = HealthProfile.objects.get(user=user)
    except (UserDietaryPreferences.DoesNotExist, HealthProfile.DoesNotExist):
        return redirect("diet:diet_entry")

    context = {
        "prefs": prefs,
        "health_goals": health_profile.assessment_data if health_profile else {},
        "debug_info": {
            "dietary_tags": prefs.dietary_tags,
            "allergies": prefs.allergies,
            "dislikes": prefs.dislikes,
            "recommended_cuisines": prefs.preferred_cuisines,
            "meals_per_day": prefs.meals_per_day,
            "meal_times": prefs.preferred_meal_times
        },
        "meal_analysis": prefs.meal_planning_analysis,
        "meal_baseline": prefs.meal_baseline
    }
    
    return render(request, "diet/specific_meals.html", context)

@login_required
def test_usda_api(request):
    """
    Test endpoint to verify USDA API connectivity
    """
    client = USDAClient()
    
    connection_ok = client.test_connection()
    
    if connection_ok:
        results = client.search_foods('apple', page_size=5)
        if results and 'foods' in results:
            foods = results['foods']
            return JsonResponse({
                'status': 'success',
                'message': 'API connection successful',
                'sample_results': foods
            })
    
    return JsonResponse({
        'status': 'error',
        'message': 'Failed to connect to USDA API'
    }, status=500)

@login_required
@require_http_methods(["GET"])
def search_food(request):
    """
    Endpoint for searching foods using USDA API
    """
    query = request.GET.get('query', '')
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('pageSize', 25))
    fdc_id = request.GET.get('fdcId')  # get detailed info for a specific food

    if not query and not fdc_id:
        return JsonResponse({
            'status': 'error',
            'message': 'Search query or fdcId is required'
        }, status=400)

    try:
        client = USDAClient()
        
        # ff fdcId is provided, get detailed information - getting pretty much all there is atm - will clean up later
        if fdc_id:
            result = client.get_food_details(fdc_id)
            if result:
                # detailed nutrient information
                nutrients = {}
                if 'foodNutrients' in result:
                    for nutrient in result['foodNutrients']:
                        name = nutrient.get('nutrient', {}).get('name', '').lower()
                        amount = nutrient.get('amount', 0)
                        unit = nutrient.get('nutrient', {}).get('unitName', '')
                        
                        # Categorizde nutrients - needed for meal prep macros etc
                        if any(x in name for x in ['protein', 'carbohydrate', 'fat', 'energy']):
                            category = 'macros'
                        elif any(x in name for x in ['vitamin', 'folate', 'niacin', 'thiamin', 'riboflavin']):
                            category = 'vitamins'
                        elif any(x in name for x in ['iron', 'calcium', 'magnesium', 'zinc', 'potassium']):
                            category = 'minerals'
                        else:
                            category = 'other'
                            
                        if category not in nutrients:
                            nutrients[category] = []
                            
                        nutrients[category].append({
                            'name': name.title(),
                            'amount': amount,
                            'unit': unit
                        })

                return JsonResponse({
                    'status': 'success',
                    'food': {
                        'fdcId': result.get('fdcId'),
                        'description': result.get('description', '').title(),
                        'brandOwner': result.get('brandOwner', 'Generic'),
                        'ingredients': result.get('ingredients'),
                        'servingSize': result.get('servingSize'),
                        'servingSizeUnit': result.get('servingSizeUnit'),
                        'dataType': result.get('dataType'),
                        'nutrients': nutrients
                    }
                })
        
        results = client.search_foods(query, page=page, page_size=page_size)
        
        if results and 'foods' in results:
            processed_foods = []
            for food in results['foods']:
                processed_food = {
                    'fdcId': food.get('fdcId'),
                    'description': food.get('description', '').title(),
                    'brandOwner': food.get('brandOwner', 'Generic'),
                    'servingSize': food.get('servingSize'),
                    'servingSizeUnit': food.get('servingSizeUnit'),
                    'nutrients': {}
                }
                
                if 'foodNutrients' in food:
                    for nutrient in food['foodNutrients']:
                        name = nutrient.get('nutrientName', '').lower()
                        amount = nutrient.get('value', 0)
                        unit = nutrient.get('unitName', '')
                        
                        if 'protein' in name:
                            processed_food['nutrients']['protein'] = {'amount': amount, 'unit': unit}
                        elif 'carbohydrate' in name:
                            processed_food['nutrients']['carbs'] = {'amount': amount, 'unit': unit}
                        elif 'fat' in name:
                            processed_food['nutrients']['fat'] = {'amount': amount, 'unit': unit}
                        elif 'energy' in name and 'kcal' in unit.lower():
                            processed_food['nutrients']['calories'] = {'amount': amount, 'unit': unit}
                
                processed_foods.append(processed_food)

            return JsonResponse({
                'status': 'success',
                'foods': processed_foods,
                'totalHits': results.get('totalHits', 0),
                'currentPage': page,
                'pageSize': page_size
            })
        
        return JsonResponse({
            'status': 'error',
            'message': 'No results found'
        }, status=404)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error searching foods: {str(e)}'
        }, status=500)


# Duplicating search with mealDB because it is more direct for finding atcual recipes - can now feed this via USDA for macros and also use AI to operate from recipe -> macro -> meal plan
# Later might unify under 1 search but UX not really in focus here before functionality is done.
@login_required
@require_http_methods(["GET"])
def search_recipe(request):
    """Search recipes using TheMealDB API"""
    query = request.GET.get('query', '')
    
    if not query:
        return JsonResponse({
            'status': 'error',
            'message': 'No search query provided'
        }, status=400)
    
    try:
        # Using the free API key '1' as mentioned in TheMealDB docs
        url = f'https://www.themealdb.com/api/json/v1/1/search.php?s={query}'
        response = requests.get(url)
        data = response.json()
        
        if not data.get('meals'):
            return JsonResponse({
                'status': 'error',
                'message': 'No recipes found'
            }, status=404)
        
        # Process and simplify the meal data
        recipes = []
        for meal in data['meals']:
            # Get ingredients and measurements (TheMealDB has ingredients1-20)
            ingredients = []
            for i in range(1, 21):
                ingredient = meal.get(f'strIngredient{i}')
                measure = meal.get(f'strMeasure{i}')
                if ingredient and ingredient.strip():
                    ingredients.append({
                        'ingredient': ingredient.strip(),
                        'measure': measure.strip() if measure else ''
                    })
            
            recipe = {
                'id': meal['idMeal'],
                'name': meal['strMeal'],
                'category': meal['strCategory'],
                'area': meal['strArea'],  # cuisine type
                'instructions': meal['strInstructions'],
                'image': meal['strMealThumb'],
                'ingredients': ingredients,
                'youtube': meal.get('strYoutube', ''),
                'source': meal.get('strSource', '')
            }
            recipes.append(recipe)
        
        return JsonResponse({
            'status': 'success',
            'recipes': recipes
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error searching recipes: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["GET"])
def get_recipe_details(request):
    """Get detailed recipe information by ID"""
    recipe_id = request.GET.get('id')
    
    if not recipe_id:
        return JsonResponse({
            'status': 'error',
            'message': 'No recipe ID provided'
        }, status=400)
    
    try:
        url = f'https://www.themealdb.com/api/json/v1/1/lookup.php?i={recipe_id}'
        response = requests.get(url)
        data = response.json()
        
        if not data.get('meals'):
            return JsonResponse({
                'status': 'error',
                'message': 'Recipe not found'
            }, status=404)
        
        meal = data['meals'][0]
        
        # Get all ingredients and measurements
        ingredients = []
        for i in range(1, 21):
            ingredient = meal.get(f'strIngredient{i}')
            measure = meal.get(f'strMeasure{i}')
            if ingredient and ingredient.strip():
                ingredients.append({
                    'ingredient': ingredient.strip(),
                    'measure': measure.strip() if measure else ''
                })
        
        # Format instructions into steps
        instructions = meal['strInstructions'].split('\r\n')
        instructions = [step.strip() for step in instructions if step.strip()]
        
        recipe = {
            'id': meal['idMeal'],
            'name': meal['strMeal'],
            'category': meal['strCategory'],
            'area': meal['strArea'],
            'instructions': instructions,
            'ingredients': ingredients,
            'image': meal['strMealThumb'],
            'youtube': meal.get('strYoutube', ''),
            'source': meal.get('strSource', '')
        }
        
        return JsonResponse({
            'status': 'success',
            'recipe': recipe
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error fetching recipe details: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def save_meal(request):
    """Save a meal from MealDB search results"""
    meal_id = request.POST.get('meal_id')
    
    if not meal_id:
        return JsonResponse({'status': 'error', 'message': 'No meal ID provided'})
    
    try:
        # Check if already saved
        if UserSavedMeal.objects.filter(user=request.user, mealdb_id=meal_id).exists():
            return JsonResponse({'status': 'info', 'message': 'Meal already saved!'})
        
        # Fetch detailed meal data from MealDB
        url = f'https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal_id}'
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('meals'):
            return JsonResponse({'status': 'error', 'message': 'Meal not found'})
        
        meal_data = data['meals'][0]
        
        # Create saved meal
        saved_meal = UserSavedMeal.objects.create(
            user=request.user,
            mealdb_id=meal_data['idMeal'],
            meal_name=meal_data['strMeal'],
            category=meal_data.get('strCategory', ''),
            area=meal_data.get('strArea', ''),
            instructions=meal_data.get('strInstructions', ''),
            meal_thumb=meal_data.get('strMealThumb', ''),
            youtube_link=meal_data.get('strYoutube', ''),
            source_link=meal_data.get('strSource', ''),
            raw_mealdb_data=meal_data
        )
        
        # Step 1: Generate macros using AI
        try:
            macros = ai.get_meal_macros(meal_data)
            if macros and 'error' not in macros:
                saved_meal.macros_json = macros
                # Save prep_time_min if present
                if 'prep_time_min' in macros:
                    saved_meal.prep_time_min = macros['prep_time_min']
                saved_meal.save()
        except Exception as e:
            print(f"Could not get macros for {saved_meal.meal_name} during MealDB save: {e}")
        
        # Step 2: Get recommended servings if macros were successfully fetched
        if saved_meal.macros_json:
            try:
                servings = ai.get_recommended_servings(saved_meal)
                if servings:
                    saved_meal.recommended_servings = servings
            except Exception as e:
                print(f"Could not get servings for {saved_meal.meal_name}: {e}")

        # Save the meal, with or without AI data
        saved_meal.save()

        return JsonResponse({'status': 'success', 'message': 'Meal saved successfully!'})

    except requests.exceptions.RequestException as e:
        return JsonResponse({'status': 'error', 'message': f'Network error: {str(e)}'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Error saving meal: {str(e)}'})

@require_http_methods(["POST"])
def get_meal_macros(request, meal_id):
    """
    On-demand AI call to get macros and recommended servings for a saved meal.
    """
    try:
        meal = UserSavedMeal.objects.get(id=meal_id, user=request.user)

        # Step 1: Get macros if they don't exist
        if not meal.macros_json:
            ingredients_list = meal.get_ingredients_list()
            # Pass meal name with the key 'strMeal' to match the AI function's expectation
            meal_data = {"strMeal": meal.meal_name, "ingredients": ingredients_list}
            macros = ai.get_meal_macros(meal_data)
            
            if macros and "error" not in macros:
                meal.macros_json = macros
                if 'prep_time_min' in macros:
                    meal.prep_time_min = macros['prep_time_min']
                meal.save()
            else:
                # Even if it fails, we return an error but maybe the servings can still be calculated
                # if there was a partial failure. For now, we return.
                 return JsonResponse({"status": "error", "message": "Failed to get macros from AI."})

        # Step 2: Get recommended servings if they don't exist
        if not meal.recommended_servings:
            servings = ai.get_recommended_servings(meal)
            meal.recommended_servings = servings
            meal.save()

        return JsonResponse({
            "status": "success", 
            "macros": meal.macros_json,
            "servings": meal.recommended_servings
        })

    except UserSavedMeal.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Meal not found."}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@login_required
def my_saved_meals(request):
    """View for displaying user's saved meals and planned meals for the rolling 7-day window."""
    user = request.user
    saved_meals = UserSavedMeal.objects.filter(user=user).order_by('-saved_at')
    total_count = saved_meals.count()

    # Get user's dietary preferences for meal analysis
    try:
        prefs = UserDietaryPreferences.objects.get(user=user)
        meal_analysis = prefs.meal_planning_analysis
        print('DEBUG allergies:', prefs.allergies)
        print('DEBUG dislikes:', prefs.dislikes)
    except UserDietaryPreferences.DoesNotExist:
        meal_analysis = None
        prefs = None

    # Generate next 7 days for meal planning
    today = date.today()
    week_days = []
    week_dates = []
    for i in range(7):
        day = today + timedelta(days=i+1)  # Start from tomorrow
        week_days.append({
            'date': day,
            'formatted_date': day.strftime('%Y-%m-%d')
        })
        week_dates.append(day)

    # Fetch planned meals for the rolling window
    planned_meals_qs = PlannedMeal.objects.filter(
        user=user,
        planned_date__in=week_dates
    )
    planned_meals = {}
    for pm in planned_meals_qs:
        date_key = pm.planned_date.strftime('%Y-%m-%d')
        slot_key = pm.meal_type
        if date_key not in planned_meals:
            planned_meals[date_key] = {}
        planned_meals[date_key][slot_key] = {
            'meal_name': None,
            'meal_thumb': None,
            'id': pm.id,
            'macros': None,
            'recommended_servings': None,
        }
        # Try to get meal info from plan_json if available
        if pm.plan_json and 'meals' in pm.plan_json and pm.plan_json['meals']:
            meal = pm.plan_json['meals'][0]
            planned_meals[date_key][slot_key]['meal_name'] = meal.get('meal_name')
            planned_meals[date_key][slot_key]['meal_thumb'] = meal.get('meal_thumb')
            planned_meals[date_key][slot_key]['saved_meal_id'] = meal.get('saved_meal_id')
            planned_meals[date_key][slot_key]['portion_multiplier'] = meal.get('portion_multiplier', 1.0)
            
            # Get macros and servings from the saved meal if available
            if 'saved_meal_id' in meal:
                try:
                    saved_meal = UserSavedMeal.objects.get(id=meal['saved_meal_id'])
                    planned_meals[date_key][slot_key]['macros'] = saved_meal.macros_json
                    planned_meals[date_key][slot_key]['recommended_servings'] = saved_meal.recommended_servings
                    
                    # Calculate adjusted nutrition based on portion multiplier
                    portion_multiplier = meal.get('portion_multiplier', 1.0)
                    if saved_meal.macros_json and saved_meal.recommended_servings:
                        servings = float(saved_meal.recommended_servings)
                        portion_multiplier = float(portion_multiplier)
                        
                        adjusted_nutrition = {
                            'calories': (saved_meal.macros_json.get('calories', 0) / servings) * portion_multiplier,
                            'protein': (saved_meal.macros_json.get('protein', 0) / servings) * portion_multiplier,
                            'carbs': (saved_meal.macros_json.get('carbs', 0) / servings) * portion_multiplier,
                            'fat': (saved_meal.macros_json.get('fat', 0) / servings) * portion_multiplier
                        }
                        planned_meals[date_key][slot_key]['adjusted_nutrition'] = adjusted_nutrition
                        
                except UserSavedMeal.DoesNotExist:
                    pass

    meal_slots = ["breakfast", "lunch", "dinner", "snack"]

    # Calculate nutrition adherence ratio for the 7-day plan
    adherence_ratio = 1.0
    debug_total_calories = None
    debug_week_target = None
    debug_diff = None
    if meal_analysis and week_days:
        daily_target = meal_analysis.get('daily_calories', 2000)
        week_target = daily_target * 7
        total_calories = 0
        days_with_data = 0
        missing_days = 0
        for day in week_days:
            date_key = day['formatted_date']
            day_meals = planned_meals.get(date_key, {})
            day_total = 0
            for slot in meal_slots:
                meal = day_meals.get(slot)
                if meal and meal.get('macros') and meal.get('recommended_servings'):
                    macros = meal['macros']
                    servings = meal['recommended_servings']
                    portion = float(meal.get('portion_multiplier', 1.0))
                    day_total += (macros.get('calories', 0) / servings) * portion
            if day_total > 0:
                total_calories += day_total
                days_with_data += 1
            else:
                missing_days += 1
        diff = abs(total_calories - week_target)
        debug_total_calories = int(total_calories)
        debug_week_target = int(week_target)
        debug_diff = int(diff)
        # Ratio logic
        if missing_days > 0:
            adherence_ratio = 0.6  # Strong penalty for missing days
        elif diff <= 200 * 7:  # within 200 kcal per day
            adherence_ratio = 1.2
        elif diff <= 400 * 7:  # within 400 kcal per day
            adherence_ratio = 1.0
        elif diff <= 800 * 7:  # within 800 kcal per day
            adherence_ratio = 0.8
        else:
            adherence_ratio = 0.6
        NutritionAdherenceSnapshot.objects.update_or_create(
            user=user,
            defaults={"adherence_ratio": adherence_ratio}
        )
    # Calculate adjusted wellness score if available
    base_score = None
    adjusted_score = None
    try:
        hp = HealthProfile.objects.get(user=user)
        base_score = hp.wellness_score()
        adjusted_score = int(round(base_score * adherence_ratio))
    except Exception:
        pass
    context = {
        'saved_meals': saved_meals,
        'total_count': total_count,
        'week_days': week_days,
        'planned_meals': planned_meals,
        'meal_slots': meal_slots,
        'meal_analysis': meal_analysis,
        'prefs': prefs,
        'adherence_ratio': adherence_ratio,
        'base_wellness_score': base_score,
        'adjusted_wellness_score': adjusted_score,
        'debug_total_calories': debug_total_calories,
        'debug_week_target': debug_week_target,
        'debug_diff': debug_diff,
    }
    
    return render(request, 'diet/my_saved_meals.html', context)

@login_required
@require_http_methods(["POST"])
def add_meal_to_plan(request):
    """Add a saved meal to the meal plan."""
    try:
        data = json.loads(request.body)
        meal_id = data.get('meal_id')
        planned_date = data.get('date')
        meal_type = data.get('meal_type')
        
        if not all([meal_id, planned_date, meal_type]):
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required fields'
            }, status=400)
            
        # Get the saved meal
        saved_meal = UserSavedMeal.objects.get(id=meal_id, user=request.user)
        
        # Create or get the planned meal for this date and type
        planned_meal, created = PlannedMeal.objects.get_or_create(
            user=request.user,
            planned_date=planned_date,
            meal_type=meal_type,
            defaults={'notes': ''}
        )
        
        # Add the meal to the plan
        plan_data = planned_meal.plan_json or {}
        if 'meals' not in plan_data:
            plan_data['meals'] = []
            
        # Check if we're replacing an existing meal
        existing_meal_index = next(
            (i for i, m in enumerate(plan_data['meals']) 
             if m.get('saved_meal_id') == meal_id),
            -1
        )
        
        meal_data = {
            'saved_meal_id': meal_id,
            'meal_name': saved_meal.meal_name,
            'meal_thumb': saved_meal.meal_thumb,
            'added_at': datetime.now().isoformat()
        }
        
        if existing_meal_index >= 0:
            plan_data['meals'][existing_meal_index] = meal_data
        else:
            plan_data['meals'].append(meal_data)
            
        planned_meal.plan_json = plan_data
        planned_meal.save()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Meal added to plan successfully',
            'data': {
                'meal_id': meal_id,
                'date': planned_date,
                'meal_type': meal_type,
                'meal_name': saved_meal.meal_name,
                'meal_thumb': saved_meal.meal_thumb
            }
        })
        
    except UserSavedMeal.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Saved meal not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error adding meal to plan: {str(e)}'
        }, status=500)

@login_required
def shopping_list(request):
    """Generate a shopping list from planned meals."""
    # Get planned meals for next 7 days
    start_date = date.today() + timedelta(days=1)
    end_date = start_date + timedelta(days=6)
    
    # Get all planned meals in the date range
    planned_meals = PlannedMeal.objects.filter(
        user=request.user,
        planned_date__range=[start_date, end_date]
    ).select_related('user')
    
    # Group by meal name and count occurrences
    meal_counts = defaultdict(int)
    meal_ingredients = defaultdict(list)
    
    for planned_meal in planned_meals:
        # Get meal info from plan_json
        if planned_meal.plan_json and 'meals' in planned_meal.plan_json:
            for meal_data in planned_meal.plan_json['meals']:
                if 'saved_meal_id' in meal_data:
                    try:
                        saved_meal = UserSavedMeal.objects.get(
                            id=meal_data['saved_meal_id'],
                            user=request.user
                        )
                        meal_counts[saved_meal.meal_name] += 1
                        
                        # Only add ingredients if we haven't seen this meal before
                        if saved_meal.meal_name not in meal_ingredients:
                            meal_ingredients[saved_meal.meal_name] = saved_meal.get_ingredients_list()
                    except UserSavedMeal.DoesNotExist:
                        continue
    
    # Convert defaultdicts to regular dicts for the aggregation function
    meal_counts_dict = dict(meal_counts)
    meal_ingredients_dict = dict(meal_ingredients)
    
    # Aggregate ingredients, taking into account meal counts
    aggregated_ingredients = aggregate_ingredients(meal_ingredients_dict, meal_counts_dict)
    
    # Group ingredients by category for display
    categorized_ingredients = defaultdict(list)
    for ing_name, ing_data in aggregated_ingredients.items():
        categorized_ingredients[ing_data['category']].append({
            'name': ing_name,
            'amount': ing_data['amount'],
            'unit': ing_data['unit'],
            'original_names': ing_data['original_names'],
            'meals': ing_data['meals']
        })
    
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'meal_counts': meal_counts_dict,
        'meal_ingredients': meal_ingredients_dict,
        'categorized_ingredients': dict(categorized_ingredients),
        'debug_data': {
            'aggregated_ingredients': aggregated_ingredients,
            'meal_counts': meal_counts_dict,
            'meal_ingredients': meal_ingredients_dict
        }
    }
    
    return render(request, 'diet/shopping_list.html', context)

@login_required
def rag_recipe_search(request):
    """
    RAG-based recipe search using bulk recipes with vector similarity
    This satisfies the RAG requirement while keeping existing flows intact
    """
    query = request.GET.get('query', '')
    category = request.GET.get('category', '')
    area = request.GET.get('area', '')
    dietary_filter = request.GET.get('dietary', '')
    use_vector_search = request.GET.get('vector', 'true').lower() == 'true'
    
    # Get all bulk recipes
    recipes = BulkRecipe.objects.all()
    
    # Apply filters
    if category:
        recipes = recipes.filter(category__icontains=category)
    if area:
        recipes = recipes.filter(area__icontains=area)
    if dietary_filter:
        # SQLite-compatible filtering - search in ingredients_text instead of JSON
        recipes = recipes.filter(ingredients_text__icontains=dietary_filter.lower())
    
    # Search logic
    if query:
        if use_vector_search:
            # Use vector similarity search
            from .rag_utils import search_similar_recipes
            similar_recipes = search_similar_recipes(query, top_k=20)
            
            # Convert to queryset for consistent filtering
            recipe_ids = [r['id'] for r in similar_recipes]
            recipes = recipes.filter(id__in=recipe_ids)
            
            # Add similarity scores to context
            similarity_scores = {r['id']: r['similarity_score'] for r in similar_recipes}
        else:
            # Fallback to text search
            recipes = recipes.filter(
                models.Q(meal_name__icontains=query) |
                models.Q(ingredients_text__icontains=query) |
                models.Q(instructions__icontains=query)
            )
            similarity_scores = {}
    else:
        similarity_scores = {}
    
    # Limit results
    recipes = recipes[:50]  # Show top 50 results
    
    # Get available categories and areas for filtering
    categories = BulkRecipe.objects.values_list('category', flat=True).distinct()
    areas = BulkRecipe.objects.values_list('area', flat=True).distinct()
    
    # Count recipes with embeddings
    recipes_with_embeddings = BulkRecipe.objects.filter(embedding__isnull=False).exclude(embedding={}).count()
    total_recipes = BulkRecipe.objects.count()
    
    context = {
        'recipes': recipes,
        'query': query,
        'selected_category': category,
        'selected_area': area,
        'selected_dietary': dietary_filter,
        'use_vector_search': use_vector_search,
        'categories': categories,
        'areas': areas,
        'total_recipes': total_recipes,
        'recipes_with_embeddings': recipes_with_embeddings,
        'similarity_scores': similarity_scores,
        'rag_enabled': recipes_with_embeddings > 0,
    }
    
    return render(request, 'diet/rag_recipe_search.html', context)

@login_required
def rag_recipe_recommendations(request):
    """
    Generate personalized recipe recommendations using RAG
    This demonstrates the full RAG pipeline: database -> embedding -> retrieval -> augmentation -> generation
    """
    try:
        # Get user preferences
        from .models import UserDietaryPreferences
        prefs = UserDietaryPreferences.objects.get(user=request.user)
        
        # Build user preferences dict
        user_preferences = {
            'dietary_tags': prefs.dietary_tags or [],
            'allergies': prefs.allergies or [],
            'dislikes': prefs.dislikes or [],
            'preferred_cuisines': prefs.preferred_cuisines or [],
            'favorite_foods': [],  # Could be added to preferences later
        }
        
        # Generate RAG recommendations
        from .rag_utils import generate_rag_recipe_recommendations
        recommendations = generate_rag_recipe_recommendations(
            user_preferences=user_preferences,
            num_recommendations=10
        )
        
        context = {
            'recommendations': recommendations,
            'user_preferences': user_preferences,
            'rag_pipeline_info': {
                'database': 'BulkRecipe with 302+ recipes',
                'embedding': 'OpenAI text-embedding-ada-002',
                'retrieval': 'Cosine similarity search',
                'augmentation': 'User preferences filtering',
                'generation': 'Personalized recipe recommendations'
            }
        }
        
        return render(request, 'diet/rag_recommendations.html', context)
        
    except UserDietaryPreferences.DoesNotExist:
        messages.error(request, 'Please complete your dietary preferences first')
        return redirect('diet:diet_entry')
    except Exception as e:
        messages.error(request, f'Error generating recommendations: {str(e)}')
        return redirect('diet:rag_recipe_search')

@login_required
def rag_recipe_details(request, recipe_id):
    """View details of a single RAG recipe"""
    try:
        recipe = BulkRecipe.objects.get(id=recipe_id)
        context = {
            'recipe': recipe,
            'ingredients': recipe.get_ingredients_list(),
            'instructions': recipe.get_instructions_steps()
        }
        return render(request, "diet/rag_recipe_details.html", context)
    except BulkRecipe.DoesNotExist:
        messages.error(request, "Recipe not found in the RAG database.")
        return redirect("diet:rag_recipe_search")

@login_required
@require_http_methods(["POST"])
def save_rag_recipe(request, recipe_id):
    """Saves a recipe from the RAG database to the user's saved meals."""
    try:
        bulk_recipe = BulkRecipe.objects.get(id=recipe_id)

        # Check if already saved
        if UserSavedMeal.objects.filter(user=request.user, mealdb_id=bulk_recipe.mealdb_id).exists():
            return JsonResponse({"status": "exists", "message": "You have already saved this meal."})

        # Create the saved meal entry from the BulkRecipe
        saved_meal = UserSavedMeal.objects.create(
            user=request.user,
            mealdb_id=bulk_recipe.mealdb_id,
            meal_name=bulk_recipe.meal_name,
            category=bulk_recipe.category,
            area=bulk_recipe.area,
            instructions=bulk_recipe.instructions,
            meal_thumb=bulk_recipe.meal_thumb,
            youtube_link=bulk_recipe.youtube_link,
            source_link=bulk_recipe.source_link,
            raw_mealdb_data=bulk_recipe.raw_mealdb_data,
            source='rag'  # Mark as sourced from RAG
        )

        # Step 1: Get macros
        try:
            ingredients_list = saved_meal.get_ingredients_list()
            # Pass meal name with 'strMeal' to align with the AI function's expectation
            macros = ai.get_meal_macros({"strMeal": saved_meal.meal_name, "ingredients": ingredients_list})
            if macros and "error" not in macros:
                saved_meal.macros_json = macros
                if 'prep_time_min' in macros:
                    saved_meal.prep_time_min = macros['prep_time_min']
                saved_meal.save()
        except Exception as e:
            # Log this error but don't stop the process
            print(f"Could not get macros for {saved_meal.meal_name}: {e}")


        # Step 2: Get recommended servings (even if macros failed)
        if saved_meal.macros_json: # Can only calculate servings if we have calories
            try:
                servings = ai.get_recommended_servings(saved_meal)
                if servings:
                    saved_meal.recommended_servings = servings
                    saved_meal.save()
            except Exception as e:
                # Log this error as well, but don't crash the request
                print(f"Could not get servings for {saved_meal.meal_name}: {e}")

        # Respond with success regardless of AI failures, which can be fixed later
        return JsonResponse({
            "status": "success",
            "message": "Meal saved successfully! You can find it in 'My Saved Meals'.",
            "macros": saved_meal.macros_json,
            "servings": saved_meal.recommended_servings
        })

    except BulkRecipe.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Recipe not found."}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def delete_saved_meal(request, meal_id):
    """Deletes a user's saved meal and removes it from any planned days."""
    try:
        # Find the meal to delete
        meal_to_delete = UserSavedMeal.objects.get(id=meal_id, user=request.user)
        
        # Find and delete any planned meals that use this saved meal
        # This is done by checking the meal_id in the plan_json
        planned_meals_to_remove = PlannedMeal.objects.filter(user=request.user, plan_json__meal_id=meal_to_delete.id)
        planned_meals_to_remove.delete()
        
        # Delete the saved meal itself
        meal_to_delete.delete()
        
        return JsonResponse({"status": "success", "message": "Meal deleted successfully."})

    except UserSavedMeal.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Meal not found."}, status=404)
    except Exception as e:
        # Log the exception for debugging
        print(f"Error deleting meal {meal_id}: {str(e)}")
        return JsonResponse({"status": "error", "message": "An unexpected error occurred."}, status=500)

@login_required
@require_http_methods(["POST"])
def create_meal_plan_version(request):
    """
    Create a new version of the current meal plan
    Completely isolated from existing meal planning logic
    """
    try:
        data = json.loads(request.body)
        version_name = data.get('version_name', '')
        notes = data.get('notes', '')
        created_by_action = data.get('action', 'manual')
        
        user = request.user
        
        # Get current meal plan state (same logic as my_saved_meals view)
        today = date.today()
        week_dates = []
        for i in range(7):
            day = today + timedelta(days=i+1)
            week_dates.append(day)
        
        # Fetch planned meals for the rolling window
        planned_meals_qs = PlannedMeal.objects.filter(
            user=user,
            planned_date__in=week_dates
        )
        
        meal_plan_snapshot = {}
        for pm in planned_meals_qs:
            date_key = pm.planned_date.strftime('%Y-%m-%d')
            slot_key = pm.meal_type
            if date_key not in meal_plan_snapshot:
                meal_plan_snapshot[date_key] = {}
            meal_plan_snapshot[date_key][slot_key] = {
                'id': pm.id,
                'plan_json': pm.plan_json,
                'notes': pm.notes,
                'total_calories': pm.total_calories,
                'total_protein': pm.total_protein,
                'total_carbs': pm.total_carbs,
                'total_fat': pm.total_fat,
            }
        
        # Calculate daily totals snapshot
        daily_totals_snapshot = {}
        for day_date in week_dates:
            date_key = day_date.strftime('%Y-%m-%d')
            day_meals = meal_plan_snapshot.get(date_key, {})
            
            # Calculate totals for this day
            day_totals = {
                'calories': 0,
                'protein': 0,
                'carbs': 0,
                'fats': 0
            }
            
            for slot, meal_data in day_meals.items():
                if meal_data.get('plan_json') and 'meals' in meal_data['plan_json']:
                    for meal in meal_data['plan_json']['meals']:
                        if 'saved_meal_id' in meal:
                            try:
                                saved_meal = UserSavedMeal.objects.get(
                                    id=meal['saved_meal_id'],
                                    user=user
                                )
                                if saved_meal.macros_json and saved_meal.recommended_servings:
                                    servings = saved_meal.recommended_servings
                                    day_totals['calories'] += saved_meal.macros_json.get('calories', 0) / servings
                                    day_totals['protein'] += saved_meal.macros_json.get('protein', 0) / servings
                                    day_totals['carbs'] += saved_meal.macros_json.get('carbs', 0) / servings
                                    day_totals['fats'] += saved_meal.macros_json.get('fat', 0) / servings
                            except UserSavedMeal.DoesNotExist:
                                continue
            
            daily_totals_snapshot[date_key] = day_totals
        
        # Create the version
        version = MealPlanVersion.objects.create(
            user=user,
            version_name=version_name,
            notes=notes,
            created_by_action=created_by_action,
            meal_plan_snapshot=meal_plan_snapshot,
            daily_totals_snapshot=daily_totals_snapshot
        )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Meal plan version created successfully',
            'data': {
                'version_id': version.id,
                'version_name': version.version_name,
                'created_at': version.created_at.isoformat()
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error creating meal plan version: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["GET"])
def get_meal_plan_versions(request):
    """
    Get all meal plan versions for the current user
    """
    try:
        versions = MealPlanVersion.objects.filter(user=request.user)
        versions_data = []
        
        for version in versions:
            versions_data.append({
                'id': version.id,
                'version_name': version.version_name,
                'created_at': version.created_at.isoformat(),
                'created_by_action': version.created_by_action,
                'notes': version.notes,
                'meal_count': sum(len(day_meals) for day_meals in version.meal_plan_snapshot.values())
            })
        
        return JsonResponse({
            'status': 'success',
            'data': versions_data
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error fetching meal plan versions: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def restore_meal_plan_version(request, version_id):
    """
    Restore a meal plan version
    This will replace the current meal plan with the version data
    """
    try:
        version = MealPlanVersion.objects.get(id=version_id, user=request.user)
        
        # Delete current planned meals for the 7-day window
        today = date.today()
        week_dates = []
        for i in range(7):
            day = today + timedelta(days=i+1)
            week_dates.append(day)
        
        PlannedMeal.objects.filter(
            user=request.user,
            planned_date__in=week_dates
        ).delete()
        
        # Restore meals from the version
        restored_count = 0
        for date_key, day_meals in version.meal_plan_snapshot.items():
            for slot_key, meal_data in day_meals.items():
                if meal_data.get('plan_json'):
                    planned_meal = PlannedMeal.objects.create(
                        user=request.user,
                        planned_date=datetime.strptime(date_key, '%Y-%m-%d').date(),
                        meal_type=slot_key,
                        plan_json=meal_data['plan_json'],
                        notes=meal_data.get('notes', ''),
                        total_calories=meal_data.get('total_calories'),
                        total_protein=meal_data.get('total_protein'),
                        total_carbs=meal_data.get('total_carbs'),
                        total_fat=meal_data.get('total_fat')
                    )
                    restored_count += 1
        
        return JsonResponse({
            'status': 'success',
            'message': f'Meal plan restored from version "{version.version_name}"',
            'data': {
                'version_name': version.version_name,
                'restored_meals': restored_count
            }
        })
        
    except MealPlanVersion.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Version not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error restoring meal plan version: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def swap_meals(request):
    """Swap meals between different days and meal slots."""
    try:
        data = json.loads(request.body)
        source_date = data.get('source_date')
        source_meal_type = data.get('source_meal_type')
        target_date = data.get('target_date')
        target_meal_type = data.get('target_meal_type')
        
        if not all([source_date, source_meal_type, target_date, target_meal_type]):
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required fields for meal swap'
            }, status=400)
        
        # Get the planned meals for both slots
        source_planned = PlannedMeal.objects.filter(
            user=request.user,
            planned_date=source_date,
            meal_type=source_meal_type
        ).first()
        
        target_planned = PlannedMeal.objects.filter(
            user=request.user,
            planned_date=target_date,
            meal_type=target_meal_type
        ).first()
        
        # Extract meal data from both slots
        source_meals = source_planned.plan_json.get('meals', []) if source_planned and source_planned.plan_json else []
        target_meals = target_planned.plan_json.get('meals', []) if target_planned and target_planned.plan_json else []
        
        # Perform the swap
        with transaction.atomic():
            # Update source slot
            if source_planned:
                source_planned.plan_json = {'meals': target_meals}
                source_planned.save()
            elif target_meals:  # Create source slot if it doesn't exist but target has meals
                PlannedMeal.objects.create(
                    user=request.user,
                    planned_date=source_date,
                    meal_type=source_meal_type,
                    plan_json={'meals': target_meals}
                )
            
            # Update target slot
            if target_planned:
                target_planned.plan_json = {'meals': source_meals}
                target_planned.save()
            elif source_meals:  # Create target slot if it doesn't exist but source has meals
                PlannedMeal.objects.create(
                    user=request.user,
                    planned_date=target_date,
                    meal_type=target_meal_type,
                    plan_json={'meals': source_meals}
                )
        
        return JsonResponse({
            'status': 'success',
            'message': 'Meals swapped successfully',
            'data': {
                'source_date': source_date,
                'source_meal_type': source_meal_type,
                'target_date': target_date,
                'target_meal_type': target_meal_type,
                'source_meals_count': len(source_meals),
                'target_meals_count': len(target_meals)
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error swapping meals: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def remove_meal_from_plan(request):
    """Remove a meal from a specific day and meal slot."""
    try:
        data = json.loads(request.body)
        planned_date = data.get('date')
        meal_type = data.get('meal_type')
        meal_id = data.get('meal_id')  # Optional: remove specific meal, otherwise remove all
        
        if not all([planned_date, meal_type]):
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required fields'
            }, status=400)
        
        # Get the planned meal
        planned_meal = PlannedMeal.objects.filter(
            user=request.user,
            planned_date=planned_date,
            meal_type=meal_type
        ).first()
        
        if not planned_meal or not planned_meal.plan_json:
            return JsonResponse({
                'status': 'error',
                'message': 'No meal found in this slot'
            }, status=404)
        
        meals = planned_meal.plan_json.get('meals', [])
        
        if meal_id:
            # Remove specific meal
            meals = [m for m in meals if m.get('saved_meal_id') != meal_id]
        else:
            # Remove all meals from this slot
            meals = []
        
        if meals:
            planned_meal.plan_json = {'meals': meals}
            planned_meal.save()
        else:
            # Delete the planned meal record if no meals left
            planned_meal.delete()
        
        return JsonResponse({
            'status': 'success',
            'message': 'Meal removed from plan successfully',
            'data': {
                'date': planned_date,
                'meal_type': meal_type,
                'remaining_meals': len(meals)
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error removing meal: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def adjust_portion_size(request):
    """Adjust portion size of a planned meal with automatic nutritional recalculation."""
    try:
        data = json.loads(request.body)
        planned_date = data.get('date')
        meal_type = data.get('meal_type')
        meal_id = data.get('meal_id')
        portion_multiplier = data.get('portion_multiplier')
        
        if not all([planned_date, meal_type, meal_id, portion_multiplier]):
            return JsonResponse({
                'status': 'error',
                'message': 'Missing required fields for portion adjustment'
            }, status=400)
        
        # Validate portion multiplier
        try:
            portion_multiplier = float(portion_multiplier)
            if portion_multiplier <= 0:
                raise ValueError("Portion multiplier must be positive")
        except (ValueError, TypeError):
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid portion multiplier value'
            }, status=400)
        
        # Get the planned meal
        planned_meal = PlannedMeal.objects.filter(
            user=request.user,
            planned_date=planned_date,
            meal_type=meal_type
        ).first()
        
        if not planned_meal or not planned_meal.plan_json:
            return JsonResponse({
                'status': 'error',
                'message': 'No meal plan found for this slot'
            }, status=404)
        
        meals = planned_meal.plan_json.get('meals', [])
        
        # Find and update the specific meal
        meal_found = False
        for meal in meals:
            if meal.get('saved_meal_id') == meal_id:
                meal['portion_multiplier'] = portion_multiplier
                meal_found = True
                break
        
        if not meal_found:
            return JsonResponse({
                'status': 'error',
                'message': 'Meal not found in this slot'
            }, status=404)
        
        # Save the updated plan
        planned_meal.plan_json = {'meals': meals}
        planned_meal.save()
        
        # Get the saved meal to calculate adjusted nutrition
        try:
            saved_meal = UserSavedMeal.objects.get(id=meal_id, user=request.user)
            adjusted_nutrition = {}
            
            if saved_meal.macros_json:
                adjusted_nutrition = {
                    'calories': saved_meal.macros_json.get('calories', 0) * portion_multiplier,
                    'protein': saved_meal.macros_json.get('protein', 0) * portion_multiplier,
                    'carbs': saved_meal.macros_json.get('carbs', 0) * portion_multiplier,
                    'fat': saved_meal.macros_json.get('fat', 0) * portion_multiplier
                }
            
            return JsonResponse({
                'status': 'success',
                'message': 'Portion size adjusted successfully',
                'data': {
                    'date': planned_date,
                    'meal_type': meal_type,
                    'meal_id': meal_id,
                    'portion_multiplier': portion_multiplier,
                    'adjusted_nutrition': adjusted_nutrition,
                    'meal_name': saved_meal.meal_name
                }
            })
            
        except UserSavedMeal.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Saved meal not found'
            }, status=404)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Error adjusting portion size: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def add_custom_meal(request):
    """
    Step 1 of 2 for adding a custom meal.
    Takes raw form data, calls AI to get structured ingredient choices,
    and returns them to the user for confirmation.
    """
    try:
        data = json.loads(request.body)
        ingredients_text = data.get('ingredients')

        if not ingredients_text:
            return JsonResponse({'status': 'error', 'message': 'Ingredients text is required.'}, status=400)

        # Use the new AI function to get structured choices
        ingredient_choices = ai.get_structured_ingredients_from_text(ingredients_text)

        if not ingredient_choices:
            return JsonResponse({'status': 'error', 'message': 'The AI could not understand the ingredients. Please try rephrasing them.'}, status=400)

        return JsonResponse({
            'status': 'success',
            'message': 'Please confirm the ingredients.',
            'ingredient_choices': ingredient_choices
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)


def _trigger_macro_calculation(meal_id):
    """
    Runs in a background thread to fetch macros and servings for a meal
    without blocking the main request.
    """
    try:
        meal = UserSavedMeal.objects.get(id=meal_id)
        
        # This logic is copied from the get_meal_macros view
        if not meal.macros_json:
            ingredients_list = meal.get_ingredients_list()
            meal_data = {"strMeal": meal.meal_name, "ingredients": ingredients_list}
            macros = ai.get_meal_macros(meal_data)
            if macros and "error" not in macros:
                meal.macros_json = macros
                if 'prep_time_min' in macros:
                    meal.prep_time_min = macros['prep_time_min']
                meal.save(update_fields=['macros_json'])

        if not meal.recommended_servings:
            servings = ai.get_recommended_servings(meal)
            meal.recommended_servings = servings
            meal.save(update_fields=['recommended_servings'])

    except UserSavedMeal.DoesNotExist:
        print(f"Background macro-calc failed: Meal with id {meal_id} not found.")
    except Exception as e:
        print(f"Background macro-calc failed for meal {meal_id}: {e}")


@login_required
@require_http_methods(["POST"])
def save_chosen_custom_meal(request):
    """
    Step 2 of 2 for adding a custom meal.
    Takes the user's chosen structured ingredients and other meal data,
    and saves the final UserSavedMeal object.
    """
    try:
        data = json.loads(request.body)
        meal_name = data.get('meal_name')
        category = data.get('category')
        area = data.get('area')
        instructions = data.get('instructions')
        chosen_ingredients = data.get('chosen_ingredients') # This is now a clean, structured list

        if not all([meal_name, category, instructions, chosen_ingredients]):
            return JsonResponse({'status': 'error', 'message': 'Missing required fields.'}, status=400)

        # Build the MealDB-compatible data structure from the clean ingredients
        raw_mealdb_data = {
            'strMeal': meal_name,
            'strCategory': category,
            'strArea': area,
            'strInstructions': instructions,
            'strMealThumb': '', # No image for custom meals
        }
        for idx, item in enumerate(chosen_ingredients, 1):
            raw_mealdb_data[f'strIngredient{idx}'] = item.get('ingredient', '')
            raw_mealdb_data[f'strMeasure{idx}'] = item.get('measure', '')
        
        # Fill remaining ingredient slots
        for idx in range(len(chosen_ingredients) + 1, 21):
            raw_mealdb_data[f'strIngredient{idx}'] = ''
            raw_mealdb_data[f'strMeasure{idx}'] = ''

        # Create the meal instance first
        new_meal = UserSavedMeal.objects.create(
            user=request.user,
            mealdb_id=f'custom_{meal_name[:10]}_{int(timezone.now().timestamp())}',
            meal_name=meal_name,
            category=category,
            area=area,
            instructions=instructions,
            meal_thumb='', # No image for custom meals
            raw_mealdb_data=raw_mealdb_data,
            source='Custom',
        )

        # Now, trigger the background task to fetch macros
        thread = threading.Thread(target=_trigger_macro_calculation, args=(new_meal.id,))
        thread.daemon = True
        thread.start()

        return JsonResponse({'status': 'success', 'message': 'Custom meal saved. Nutritional info is being calculated in the background.'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred during save: {str(e)}'}, status=500)

@login_required
@require_http_methods(["POST"])
def get_prep_time(request, meal_id):
    """
    On-demand AI call to get prep_time_min for a saved meal.
    """
    try:
        meal = UserSavedMeal.objects.get(id=meal_id, user=request.user)

        # Only call AI if prep_time_min is missing
        if meal.prep_time_min is None:
            ingredients_list = meal.get_ingredients_list()
            meal_data = {"strMeal": meal.meal_name, "ingredients": ingredients_list}
            macros = ai.get_meal_macros(meal_data)
            if macros and "prep_time_min" in macros:
                meal.prep_time_min = macros["prep_time_min"]
                meal.save(update_fields=["prep_time_min"])
                return JsonResponse({"status": "success", "prep_time_min": meal.prep_time_min})
            else:
                return JsonResponse({"status": "error", "message": "Failed to get prep time from AI."})
        else:
            return JsonResponse({"status": "success", "prep_time_min": meal.prep_time_min})

    except UserSavedMeal.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Meal not found."}, status=404)
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@require_POST
@login_required
def regenerate_wellness_score(request):
    user = request.user
    try:
        prefs = UserDietaryPreferences.objects.get(user=user)
        meal_analysis = prefs.meal_planning_analysis
    except UserDietaryPreferences.DoesNotExist:
        meal_analysis = None
        prefs = None

    today = date.today()
    week_days = []
    week_dates = []
    for i in range(7):
        day = today + timedelta(days=i+1)
        week_days.append({
            'date': day,
            'formatted_date': day.strftime('%Y-%m-%d')
        })
        week_dates.append(day)

    planned_meals_qs = PlannedMeal.objects.filter(
        user=user,
        planned_date__in=week_dates
    )
    planned_meals = {}
    for pm in planned_meals_qs:
        date_key = pm.planned_date.strftime('%Y-%m-%d')
        slot_key = pm.meal_type
        if date_key not in planned_meals:
            planned_meals[date_key] = {}
        planned_meals[date_key][slot_key] = {
            'meal_name': None,
            'meal_thumb': None,
            'id': pm.id,
            'macros': None,
            'recommended_servings': None,
            'portion_multiplier': 1.0,
        }
        if pm.plan_json and 'meals' in pm.plan_json and pm.plan_json['meals']:
            meal = pm.plan_json['meals'][0]
            planned_meals[date_key][slot_key]['meal_name'] = meal.get('meal_name')
            planned_meals[date_key][slot_key]['meal_thumb'] = meal.get('meal_thumb')
            planned_meals[date_key][slot_key]['saved_meal_id'] = meal.get('saved_meal_id')
            planned_meals[date_key][slot_key]['portion_multiplier'] = meal.get('portion_multiplier', 1.0)
            if 'saved_meal_id' in meal:
                try:
                    saved_meal = UserSavedMeal.objects.get(id=meal['saved_meal_id'])
                    planned_meals[date_key][slot_key]['macros'] = saved_meal.macros_json
                    planned_meals[date_key][slot_key]['recommended_servings'] = saved_meal.recommended_servings
                except UserSavedMeal.DoesNotExist:
                    pass

    meal_slots = ["breakfast", "lunch", "dinner", "snack"]

    adherence_ratio = 1.0
    if meal_analysis and week_days:
        daily_target = meal_analysis.get('daily_calories', 2000)
        week_target = daily_target * 7
        total_calories = 0
        days_with_data = 0
        missing_days = 0
        for day in week_days:
            date_key = day['formatted_date']
            day_meals = planned_meals.get(date_key, {})
            day_total = 0
            for slot in meal_slots:
                meal = day_meals.get(slot)
                if meal and meal.get('macros') and meal.get('recommended_servings'):
                    macros = meal['macros']
                    servings = meal['recommended_servings']
                    portion = float(meal.get('portion_multiplier', 1.0))
                    day_total += (macros.get('calories', 0) / servings) * portion
            if day_total > 0:
                total_calories += day_total
                days_with_data += 1
            else:
                missing_days += 1
        diff = abs(total_calories - week_target)
        # Ratio logic
        if missing_days > 0:
            adherence_ratio = 0.6  # Strong penalty for missing days
        elif diff <= 200 * 7:  # within 200 kcal per day
            adherence_ratio = 1.2
        elif diff <= 400 * 7:  # within 400 kcal per day
            adherence_ratio = 1.0
        elif diff <= 800 * 7:  # within 800 kcal per day
            adherence_ratio = 0.8
        else:
            adherence_ratio = 0.6
        NutritionAdherenceSnapshot.objects.update_or_create(
            user=user,
            defaults={"adherence_ratio": adherence_ratio}
        )
    else:
        # If data is missing or something is wrong, set a safe penalty ratio
        NutritionAdherenceSnapshot.objects.update_or_create(
            user=user,
            defaults={"adherence_ratio": 0.6}
        )
    return HttpResponseRedirect(reverse('diet:my_saved_meals'))

@login_required
def adjust_shopping_list(request):
    user = request.user
    # Use the same logic as shopping_list to generate the combined shopping list
    start_date = date.today() + timedelta(days=1)
    end_date = start_date + timedelta(days=6)
    planned_meals = PlannedMeal.objects.filter(
        user=user,
        planned_date__range=[start_date, end_date]
    ).select_related('user')
    meal_counts = defaultdict(int)
    meal_ingredients = defaultdict(list)
    for planned_meal in planned_meals:
        if planned_meal.plan_json and 'meals' in planned_meal.plan_json:
            for meal_data in planned_meal.plan_json['meals']:
                if 'saved_meal_id' in meal_data:
                    try:
                        saved_meal = UserSavedMeal.objects.get(
                            id=meal_data['saved_meal_id'],
                            user=user
                        )
                        meal_counts[saved_meal.meal_name] += 1
                        if saved_meal.meal_name not in meal_ingredients:
                            meal_ingredients[saved_meal.meal_name] = saved_meal.get_ingredients_list()
                    except UserSavedMeal.DoesNotExist:
                        continue
    meal_counts_dict = dict(meal_counts)
    meal_ingredients_dict = dict(meal_ingredients)
    aggregated_ingredients = aggregate_ingredients(meal_ingredients_dict, meal_counts_dict)
    # Flatten for editable table
    shopping_list = [
        {
            'name': ing_name,
            'quantity': ing_data['amount'],
            'unit': ing_data['unit']
        }
        for ing_name, ing_data in aggregated_ingredients.items()
    ]
    versions = ShoppingListVersion.objects.filter(user=user).order_by('-created_at')
    return render(request, 'diet/adjust_shopping_list.html', {
        'shopping_list': shopping_list,
        'versions': versions,
    })

@csrf_exempt
@login_required
def save_shopping_list_version(request):
    if request.method == 'POST':
        user = request.user
        import json
        data = json.loads(request.body)
        name = data.get('name', '')
        notes = data.get('notes', '')
        items = data.get('items', [])
        version = ShoppingListVersion.objects.create(
            user=user,
            name=name,
            notes=notes,
            items_json=items
        )
        return JsonResponse({'status': 'success', 'version_id': version.id})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

@login_required
def get_shopping_list_version(request, version_id):
    user = request.user
    try:
        version = ShoppingListVersion.objects.get(id=version_id, user=user)
        return JsonResponse({
            'status': 'success',
            'name': version.name,
            'notes': version.notes,
            'created_at': version.created_at.isoformat(),
            'items': version.items_json
        })
    except ShoppingListVersion.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Not found'}, status=404)

@require_GET
@login_required
def generate_ai_recipe(request):
    user = request.user
    try:
        prefs = UserDietaryPreferences.objects.get(user=user)
        daily_calories = 2000
        if prefs.meal_planning_analysis and 'daily_calories' in prefs.meal_planning_analysis:
            daily_calories = prefs.meal_planning_analysis['daily_calories']
        allergies = prefs.allergies or []
        dislikes = prefs.dislikes or []
    except UserDietaryPreferences.DoesNotExist:
        daily_calories = 2000
        allergies = []
        dislikes = []
    meal_types = ["breakfast", "lunch", "dinner", "snack", "dessert"]
    proteins = ["chicken", "beef", "pork", "fish", "tofu", "lentils", "eggs", "cheese", "beans", "turkey", "shrimp"]
    carbs = ["rice", "pasta", "bread", "potatoes", "quinoa", "oats", "tortilla", "couscous", "barley", "sweet potato"]
    cuisines = ["Italian", "Mexican", "Asian", "American", "Indian", "French", "Greek", "Spanish"]
    prompt = f"""
    Generate a creative, realistic, and unique recipe for a single meal that fits the following user profile:
    - Daily calorie target: {daily_calories}
    - Allergies: {', '.join(allergies) if allergies else 'None'}
    - Dislikes: {', '.join(dislikes) if dislikes else 'None'}

    Randomly select a meal type, main protein, main carb, and cuisine from the following lists. You may also generate a creative dessert or snack instead of a main meal.

    Meal types: {', '.join(meal_types)}
    Main proteins: {', '.join(proteins)}
    Main carbs: {', '.join(carbs)}
    Cuisines: {', '.join(cuisines)}

    The recipe should:
    - Not include any ingredients the user is allergic to or dislikes
    - Be plausible and not too exotic
    - Include a title, a list of ingredients (with quantities and units), and step-by-step instructions
    - Be suitable for a typical home cook
    - Output as JSON with keys: title, ingredients (list of {{'ingredient', 'measure'}}), instructions (list of steps), meal_type, cuisine
    - Make each recipe unique and do not repeat previous recipes. Add some random variation each time.
    """
    from .ai import client
    import json as pyjson
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful recipe assistant. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.99,
            top_p=1
        )
        content = response.choices[0].message.content.strip()
        # Try to parse JSON
        recipe = pyjson.loads(content)
        return JsonResponse({"status": "success", "recipe": recipe})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})

@csrf_exempt
@login_required
def save_ai_recipe(request):
    if request.method == 'POST':
        import json
        import random
        user = request.user
        try:
            data = json.loads(request.body)
            title = data.get('title')
            ingredients = data.get('ingredients', [])
            instructions = data.get('instructions', [])
            if not title or not ingredients or not instructions:
                return JsonResponse({'status': 'error', 'message': 'Missing required fields'})
            # Generate a unique random mealdb_id
            for _ in range(5):
                mealdb_id = random.randint(10_000_000, 99_999_999)
                if not UserSavedMeal.objects.filter(user=user, mealdb_id=mealdb_id).exists():
                    break
            else:
                return JsonResponse({'status': 'error', 'message': 'Could not generate unique mealdb_id'})
            meal = UserSavedMeal.objects.create(
                user=user,
                meal_name=title,
                mealdb_id=mealdb_id,
                raw_mealdb_data={
                    'strMeal': title,
                    'strInstructions': '\n'.join(instructions),
                    **{f'strIngredient{i+1}': ing['ingredient'] for i, ing in enumerate(ingredients)},
                    **{f'strMeasure{i+1}': ing['measure'] for i, ing in enumerate(ingredients)}
                }
            )
            # Trigger macro/serving calculation as with custom meal
            try:
                from .ai import get_meal_macros, get_recommended_servings
                macros = get_meal_macros({'strMeal': title, 'ingredients': ingredients})
                if macros and 'error' not in macros:
                    meal.macros_json = macros
                    if 'prep_time_min' in macros:
                        meal.prep_time_min = macros['prep_time_min']
                    meal.save()
                if meal.macros_json:
                    servings = get_recommended_servings(meal)
                    if servings:
                        meal.recommended_servings = servings
                        meal.save()
            except Exception as e:
                pass
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

@csrf_exempt
@login_required
def suggest_ingredient_substitute(request):
    if request.method == 'POST':
        import json
        user = request.user
        try:
            data = json.loads(request.body)
            ingredient = data.get('ingredient')
            if not ingredient:
                return JsonResponse({'status': 'error', 'message': 'Missing ingredient'})
            try:
                prefs = UserDietaryPreferences.objects.get(user=user)
                allergies = prefs.allergies or []
                dislikes = prefs.dislikes or []
            except UserDietaryPreferences.DoesNotExist:
                allergies = []
                dislikes = []
            prompt = f"""
            Suggest a realistic, common substitute for the ingredient: '{ingredient}'.
            The substitute should avoid the user's allergies ({', '.join(allergies) if allergies else 'None'}) and dislikes ({', '.join(dislikes) if dislikes else 'None'}).
            If possible, suggest something that is likely to be available in a typical home or grocery store.
            Respond with only the substitute ingredient name, nothing else.
            """
            from .ai import client
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful kitchen assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                top_p=1
            )
            suggestion = response.choices[0].message.content.strip()
            return JsonResponse({'status': 'success', 'suggestion': suggestion})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

@csrf_exempt
@login_required
def save_meal_with_substitute(request):
    if request.method == 'POST':
        import json
        import uuid
        from django.utils import timezone
        user = request.user
        try:
            data = json.loads(request.body)
            meal_id = data.get('meal_id')
            orig_ing = data.get('original_ingredient')
            sub = data.get('substitute')
            if not (meal_id and orig_ing and sub):
                return JsonResponse({'status': 'error', 'message': 'Missing data'})
            from .models import UserSavedMeal
            orig = UserSavedMeal.objects.get(id=meal_id, user=user)
            # Copy and modify raw_mealdb_data
            raw = dict(orig.raw_mealdb_data) if orig.raw_mealdb_data else {}
            # Replace ingredient in the correct slot
            for i in range(1, 21):
                ing_key = f'strIngredient{i}'
                if raw.get(ing_key, '').strip().lower() == orig_ing.strip().lower():
                    raw[ing_key] = sub
                    break
            # Generate a unique mealdb_id
            new_mealdb_id = f"subs-{uuid.uuid4().hex[:12]}"
            new_meal = UserSavedMeal.objects.create(
                user=user,
                mealdb_id=new_mealdb_id,
                meal_name=f"Subs - {orig.meal_name}",
                category=orig.category,
                area=orig.area,
                instructions=orig.instructions,
                macros_json=orig.macros_json,
                recommended_servings=orig.recommended_servings,
                prep_time_min=orig.prep_time_min,
                meal_thumb=orig.meal_thumb,
                source='Substitute',
                source_link=orig.source_link,
                youtube_link=orig.youtube_link,
                raw_mealdb_data=raw,
                created_at=timezone.now(),
            )
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

@csrf_exempt
@login_required
def generate_nutritional_analysis(request):
    """
    Generate AI nutritional analysis based on scraped page data.
    This is completely isolated and doesn't modify any existing models.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST requests allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        
        # Extract data from the request (scraped by JavaScript)
        daily_targets = data.get('daily_targets', {})
        daily_totals = data.get('daily_totals', {})
        wellness_score_info = data.get('wellness_score_info', {})
        
        # Generate AI analysis using the isolated function
        from . import ai
        analysis = ai.generate_nutritional_analysis_insights(
            daily_targets=daily_targets,
            daily_totals=daily_totals,
            wellness_score_info=wellness_score_info
        )
        
        return JsonResponse({
            'success': True,
            'analysis': analysis
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Analysis generation failed: {str(e)}'}, status=500)