from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse
import json
from datetime import date, timedelta
from .models import UserDataSnapshot
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from .ai_utils import generate_ai_response


def get_health_snapshot(user):
    """Collect comprehensive health data for the user"""
    try:
        from health.models import HealthProfile, GoalPlan, HistoricalMetric, WellnessScoreHistory, DailyActivitySnapshot
        from datetime import date, timedelta
        
        profile = user.healthprofile
        goal_plan = GoalPlan.objects.get(user=user)
        
        # Get recent weight history
        weight_history = HistoricalMetric.objects.filter(
            user=user, 
            metric_type="weight"
        ).order_by('-recorded_at')[:20]  # Last 20 entries for better trend analysis
        
        # Get recent wellness scores
        score_history = WellnessScoreHistory.objects.filter(
            user=user
        ).order_by('-recorded_at')[:20]  # Last 20 entries
        
        # Get daily activity snapshots
        activity_snapshots = DailyActivitySnapshot.objects.filter(
            user=user
        ).order_by('-date')[:30]  # Last 30 days
        
        # Calculate weight trends
        weight_trend = None
        if len(weight_history) >= 2:
            latest_weight = weight_history[0].value
            previous_weight = weight_history[1].value
            weight_change = latest_weight - previous_weight
            weight_trend = {
                'current_weight': latest_weight,
                'previous_weight': previous_weight,
                'change': weight_change,
                'change_percentage': (weight_change / previous_weight * 100) if previous_weight > 0 else 0,
                'trend_direction': 'up' if weight_change > 0 else 'down' if weight_change < 0 else 'stable'
            }
        
        # Calculate wellness score trends
        wellness_trend = None
        if len(score_history) >= 2:
            latest_score = score_history[0].score
            previous_score = score_history[1].score
            score_change = latest_score - previous_score
            wellness_trend = {
                'current_score': latest_score,
                'previous_score': previous_score,
                'change': score_change,
                'trend_direction': 'up' if score_change > 0 else 'down' if score_change < 0 else 'stable'
            }
        
        # Calculate goal progress
        goal_progress = None
        if goal_plan.target_weight and profile.weight_kg:
            current_weight = profile.weight_kg
            target_weight = goal_plan.target_weight
            weight_diff = current_weight - target_weight
            
            # Determine if user is trying to lose or gain weight
            if weight_diff > 0:  # Current weight > target (trying to lose)
                progress_percentage = max(0, min(100, (1 - weight_diff / (current_weight - target_weight)) * 100))
                goal_type = 'weight_loss'
            else:  # Current weight < target (trying to gain)
                progress_percentage = max(0, min(100, (1 + weight_diff / (target_weight - current_weight)) * 100))
                goal_type = 'weight_gain'
            
            goal_progress = {
                'current_weight': current_weight,
                'target_weight': target_weight,
                'weight_difference': abs(weight_diff),
                'progress_percentage': progress_percentage,
                'goal_type': goal_type,
                'remaining_weight': abs(weight_diff)
            }
        
        # Calculate activity trends (use lifestyle_category)
        activity_trend = None
        if activity_snapshots.exists():
            recent_activities = activity_snapshots[:7]  # Last 7 days
            avg_activity_level = None  # Not numeric, so just show categories
            activity_trend = {
                'recent_activities': [
                    {
                        'date': a.date.isoformat(),
                        'lifestyle_category': a.lifestyle_category,
                        'weekly_activity_target': a.weekly_activity_target,
                        'notes': getattr(a, 'notes', None)
                    } for a in recent_activities
                ]
            }
        
        health_data = {
            'profile': {
                'height_cm': profile.height_cm,
                'weight_kg': profile.weight_kg,
                'bmi': profile.bmi(),
                'wellness_score': profile.wellness_score(),
                'lifestyle': profile.lifestyle,
                'dietary_preferences': profile.dietary_preferences,
                'fitness_goals': profile.fitness_goals,
                'assessment_data': profile.assessment_data,
            },
            'goals': {
                'target_weight': goal_plan.target_weight,
                'weekly_activity_target': goal_plan.weekly_activity_target,
                'goal_description': goal_plan.goal_description,
                'ai_weekly_plan': goal_plan.ai_weekly_plan,
                'ai_monthly_plan': goal_plan.ai_monthly_plan,
                'ai_priority': goal_plan.ai_priority,
                'ai_target_date': goal_plan.ai_target_date.isoformat() if goal_plan.ai_target_date else None,
            },
            'trends': {
                'weight_trend': weight_trend,
                'wellness_trend': wellness_trend,
                'goal_progress': goal_progress,
                'activity_trend': activity_trend
            },
            'history': {
                'weight_history': [
                    {
                        'date': entry.recorded_at.isoformat(),
                        'weight': entry.value
                    } for entry in weight_history
                ],
                'score_history': [
                    {
                        'date': entry.recorded_at.isoformat(),
                        'score': entry.score
                    } for entry in score_history
                ],
                'activity_history': [
                    {
                        'date': entry.date.isoformat(),
                        'lifestyle_category': entry.lifestyle_category,
                        'weekly_activity_target': entry.weekly_activity_target
                    } for entry in activity_snapshots
                ]
            }
        }
        
        return health_data
        
    except Exception as e:
        return {'error': f'Health data collection failed: {str(e)}'}


def get_key_user_metrics(user):
    """Return key user metrics for AI context and function calling compliance."""
    from diet.models import UserDietaryPreferences
    from health.models import HealthProfile, GoalPlan
    metrics = {}
    try:
        prefs = UserDietaryPreferences.objects.get(user=user)
        # Try to get AI-generated values from meal_planning_analysis
        meal_analysis = prefs.meal_planning_analysis or {}
        daily_calories = prefs.calorie_target or meal_analysis.get('daily_calories') or 2000
        macro_split = meal_analysis.get('macro_split', {})
        protein_target = prefs.protein_target or macro_split.get('protein') or 100
        metrics['daily_calorie_target'] = daily_calories
        metrics['protein_target'] = protein_target
        metrics['allergies'] = prefs.allergies or []
        metrics['dislikes'] = prefs.dislikes or []
    except Exception:
        metrics['daily_calorie_target'] = 2000
        metrics['protein_target'] = 100
        metrics['allergies'] = []
        metrics['dislikes'] = []
    try:
        hp = HealthProfile.objects.get(user=user)
        metrics['weight'] = hp.weight_kg or None
        metrics['wellness_goal'] = hp.fitness_goals or None
    except Exception:
        metrics['weight'] = None
        metrics['wellness_goal'] = None
    try:
        gp = GoalPlan.objects.get(user=user)
        metrics['weight_goal'] = gp.target_weight or None
    except Exception:
        metrics['weight_goal'] = None
    return metrics


def get_diet_snapshot(user):
    """Collect comprehensive diet data for the user"""
    try:
        from diet.models import UserDietaryPreferences, PlannedMeal, UserSavedMeal, NutritionAdherenceSnapshot, MealPlanVersion, ShoppingListVersion
        from datetime import date, timedelta
        from collections import defaultdict
        
        prefs = UserDietaryPreferences.objects.get(user=user)
        meal_analysis = prefs.meal_planning_analysis or {}
        # --- Generate next 7 days for meal planning ---
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
        # --- Fetch planned meals for the rolling window ---
        planned_meals_qs = PlannedMeal.objects.filter(
            user=user,
            planned_date__in=week_dates
        )
        planned_meals = {}
        daily_totals = {}
        meal_slots = ["breakfast", "lunch", "dinner", "snack"]
        for pm in planned_meals_qs:
            date_key = pm.planned_date.strftime('%Y-%m-%d')
            slot_key = pm.meal_type
            if date_key not in planned_meals:
                planned_meals[date_key] = {}
            if date_key not in daily_totals:
                daily_totals[date_key] = {
                    'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0,
                    'meals': [], 'date': pm.planned_date.isoformat()
                }
            meal_data = {
                'meal_name': None,
                'meal_thumb': None,
                'id': pm.id,
                'macros': None,
                'recommended_servings': None,
                'portion_multiplier': 1.0,
                'adjusted_nutrition': None
            }
            # Extract meal info from plan_json if available
            if pm.plan_json and 'meals' in pm.plan_json and pm.plan_json['meals']:
                meal = pm.plan_json['meals'][0]
                meal_data.update({
                    'meal_name': meal.get('meal_name'),
                    'meal_thumb': meal.get('meal_thumb'),
                    'saved_meal_id': meal.get('saved_meal_id'),
                    'portion_multiplier': meal.get('portion_multiplier', 1.0)
                })
                # Get macros and servings from saved meal
                if 'saved_meal_id' in meal:
                    try:
                        saved_meal = UserSavedMeal.objects.get(id=meal['saved_meal_id'])
                        meal_data['macros'] = saved_meal.macros_json
                        meal_data['recommended_servings'] = saved_meal.recommended_servings
                        # Calculate adjusted nutrition
                        portion_multiplier = float(meal.get('portion_multiplier', 1.0))
                        if saved_meal.macros_json and saved_meal.recommended_servings:
                            servings = float(saved_meal.recommended_servings)
                            if servings > 0:
                                adjusted_nutrition = {
                                    'calories': (saved_meal.macros_json.get('calories', 0) / servings) * portion_multiplier,
                                    'protein': (saved_meal.macros_json.get('protein', 0) / servings) * portion_multiplier,
                                    'carbs': (saved_meal.macros_json.get('carbs', 0) / servings) * portion_multiplier,
                                    'fat': (saved_meal.macros_json.get('fat', 0) / servings) * portion_multiplier
                                }
                                meal_data['adjusted_nutrition'] = adjusted_nutrition
                                # Add to daily totals
                                daily_totals[date_key]['calories'] += adjusted_nutrition['calories']
                                daily_totals[date_key]['protein'] += adjusted_nutrition['protein']
                                daily_totals[date_key]['carbs'] += adjusted_nutrition['carbs']
                                daily_totals[date_key]['fat'] += adjusted_nutrition['fat']
                    except UserSavedMeal.DoesNotExist:
                        pass
            planned_meals[date_key][slot_key] = meal_data
            daily_totals[date_key]['meals'].append({
                'meal_type': slot_key,
                'meal_name': meal_data['meal_name'],
                'calories': meal_data['adjusted_nutrition']['calories'] if meal_data['adjusted_nutrition'] else 0
            })
        # --- Now calculate summary ---
        daily_calorie_target = prefs.calorie_target or meal_analysis.get('daily_calories') or 2000
        weekly_calorie_target = daily_calorie_target * 7
        current_week_total_calories = sum(day['calories'] for day in daily_totals.values())
        weekly_calorie_difference = weekly_calorie_target - current_week_total_calories
        summary = {
            'daily_calorie_target': daily_calorie_target,
            'weekly_calorie_target': weekly_calorie_target,
            'current_week_total_calories': current_week_total_calories,
            'weekly_calorie_difference': weekly_calorie_difference
        }
        
        # Get nutrition adherence and wellness score adjustments
        try:
            adherence = NutritionAdherenceSnapshot.objects.get(user=user)
            adherence_ratio = adherence.adherence_ratio
        except NutritionAdherenceSnapshot.DoesNotExist:
            adherence_ratio = 1.0
        
        # Calculate wellness score adjustments
        base_score = None
        adjusted_score = None
        try:
            from health.models import HealthProfile
            hp = HealthProfile.objects.get(user=user)
            base_score = hp.wellness_score()
            adjusted_score = int(round(base_score * adherence_ratio))
        except Exception:
            pass
        
        # Get meal plan versions (historical data)
        meal_plan_versions = MealPlanVersion.objects.filter(
            user=user
        ).order_by('-created_at')[:10]  # Last 10 versions
        
        version_history = []
        for version in meal_plan_versions:
            version_history.append({
                'id': version.id,
                'name': version.version_name,
                'created_at': version.created_at.isoformat(),
                'meal_plan_snapshot': version.meal_plan_snapshot,
                'daily_totals_snapshot': version.daily_totals_snapshot,
                'notes': version.notes
            })
        
        # Get shopping list versions
        shopping_versions = ShoppingListVersion.objects.filter(
            user=user
        ).order_by('-created_at')[:5]  # Last 5 versions
        
        shopping_history = []
        for version in shopping_versions:
            shopping_history.append({
                'id': version.id,
                'name': version.name,
                'created_at': version.created_at.isoformat(),
                'shopping_data': version.items_json if hasattr(version, 'items_json') else None,
                'notes': version.notes
            })
        
        # Get saved meals with detailed info
        saved_meals = UserSavedMeal.objects.filter(user=user).order_by('-saved_at')
        saved_meals_data = []
        for meal in saved_meals:
            meal_data = {
                'id': meal.id,
                'meal_name': meal.meal_name,
                'category': meal.category,
                'area': meal.area,
                'source': meal.source,
                'meal_thumb': meal.meal_thumb,
                'saved_at': meal.saved_at.isoformat(),
                'macros': meal.macros_json,
                'recommended_servings': meal.recommended_servings,
                'prep_time_min': meal.prep_time_min,
                'ingredients': meal.get_ingredients_list(),
                'instructions': meal.instructions,
                'youtube_link': meal.youtube_link,
                'source_link': meal.source_link
            }
            saved_meals_data.append(meal_data)
        
        # Calculate nutrition adherence metrics
        # Use defaults if any target is None to avoid NoneType * int errors
        daily_target_calories = prefs.calorie_target if prefs and prefs.calorie_target is not None else 2000
        weekly_target_calories = daily_target_calories * 7
        daily_target_protein = prefs.protein_target if prefs and prefs.protein_target is not None else 50
        daily_target_carbs = prefs.carb_target if prefs and prefs.carb_target is not None else 250
        daily_target_fat = prefs.fat_target if prefs and prefs.fat_target is not None else 70
        nutrition_adherence = {
            'ratio': adherence_ratio,
            'base_wellness_score': base_score,
            'adjusted_wellness_score': adjusted_score,
            'daily_target_calories': daily_target_calories,
            'weekly_target_calories': weekly_target_calories,
            'current_week_calories': sum(day['calories'] for day in daily_totals.values()),
            'days_with_meals': len([day for day in daily_totals.values() if day['calories'] > 0]),
            'days_without_meals': 7 - len([day for day in daily_totals.values() if day['calories'] > 0]),
            'daily_target_protein': daily_target_protein,
            'daily_target_carbs': daily_target_carbs,
            'daily_target_fat': daily_target_fat,
        }
        
        diet_data = {
            'preferences': {
                'dietary_tags': prefs.dietary_tags,
                'allergies': prefs.allergies,
                'dislikes': prefs.dislikes,
                'preferred_cuisines': prefs.preferred_cuisines,
                'meals_per_day': prefs.meals_per_day,
                'preferred_meal_times': prefs.preferred_meal_times,
            },
            'targets': {
                'calories': prefs.calorie_target,
                'protein': prefs.protein_target,
                'carbs': prefs.carb_target,
                'fat': prefs.fat_target,
            },
            'current_plan': {
                'planned_meals': planned_meals,
                'daily_totals': daily_totals,
                'meal_slots': meal_slots,
                'week_dates': [d.isoformat() for d in week_dates],
                'planned_meals_count': planned_meals_qs.count(),
            },
            'nutrition_adherence': nutrition_adherence,
            'saved_meals': {
                'count': saved_meals.count(),
                'meals': saved_meals_data
            },
            'history': {
                'meal_plan_versions': version_history,
                'shopping_list_versions': shopping_history
            },
            'meal_analysis': prefs.meal_planning_analysis,
            'meal_baseline': prefs.meal_baseline,
            'summary': summary,
            'key_metrics': get_key_user_metrics(user),
        }
        
        return diet_data
        
    except Exception as e:
        return {'error': f'Diet data collection failed: {str(e)}'}


@login_required
def ai_assistant(request):
    """AI Assistant playground - displays comprehensive user data and charts"""
    
    # Collect current data
    health_data = get_health_snapshot(request.user)
    diet_data = get_diet_snapshot(request.user)
    
    # Combine all data
    all_data = {
        'health': health_data,
        'diet': diet_data,
        'timestamp': timezone.now().isoformat(),
        'user_email': request.user.email
    }
    
    # Save snapshot for debugging
    UserDataSnapshot.objects.create(
        user=request.user,
        data_type='current_snapshot',
        data_json=all_data
    )
    
    # Prepare chart data for the template
    chart_data = {}
    
    # Health chart data
    if 'history' in health_data and 'weight_history' in health_data['history']:
        weight_history = health_data['history']['weight_history']
        if weight_history:
            chart_data['weight_labels'] = json.dumps([entry['date'][:10] for entry in weight_history[:10]])  # Last 10 entries
            chart_data['weight_values'] = json.dumps([entry['weight'] for entry in weight_history[:10]])
    
    if 'history' in health_data and 'score_history' in health_data['history']:
        score_history = health_data['history']['score_history']
        if score_history:
            chart_data['wellness_labels'] = json.dumps([entry['date'][:10] for entry in score_history[:10]])
            chart_data['wellness_values'] = json.dumps([entry['score'] for entry in score_history[:10]])
    
    # Diet chart data
    if 'current_plan' in diet_data and 'daily_totals' in diet_data['current_plan']:
        daily_totals = diet_data['current_plan']['daily_totals']
        if daily_totals:
            chart_data['diet_labels'] = json.dumps(list(daily_totals.keys()))
            chart_data['diet_calories'] = json.dumps([day['calories'] for day in daily_totals.values()])
            chart_data['diet_protein'] = json.dumps([day['protein'] for day in daily_totals.values()])
            chart_data['diet_carbs'] = json.dumps([day['carbs'] for day in daily_totals.values()])
            chart_data['diet_fat'] = json.dumps([day['fat'] for day in daily_totals.values()])
    
    # Calculate summary statistics
    summary_stats = {
        'total_saved_meals': diet_data.get('saved_meals', {}).get('count', 0) if isinstance(diet_data, dict) else 0,
        'planned_meals_count': diet_data.get('current_plan', {}).get('planned_meals_count', 0) if isinstance(diet_data, dict) else 0,
        'current_wellness_score': health_data.get('profile', {}).get('wellness_score', 0) if isinstance(health_data, dict) else 0,
        'nutrition_adherence': diet_data.get('nutrition_adherence', {}).get('ratio', 1.0) if isinstance(diet_data, dict) else 1.0,
    }
    
    return render(request, 'analytics/ai_assistant.html', {
        'data_dump': json.dumps(all_data, indent=2),
        'user': request.user,
        'health_data': health_data,
        'diet_data': diet_data,
        'chart_data': chart_data,
        'summary_stats': summary_stats
    })


@require_GET
@login_required
def get_chat_history(request):
    history = request.session.get('chat_history', [])
    return JsonResponse({'history': history})


@require_POST
@login_required
@csrf_exempt
def chat_with_ai(request):
    import json
    user = request.user
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        print(f"[DEBUG] user_message: {user_message}")
        if not user_message:
            print("[DEBUG] Empty message received.")
            return JsonResponse({'error': 'Empty message.'}, status=400)
        # Get last 5 turns of chat history
        history = request.session.get('chat_history', [])[-5:]
        print(f"[DEBUG] history: {history}")
        # Get current user context
        health_data = get_health_snapshot(user)
        print(f"[DEBUG] health_data: {health_data}")
        diet_data = get_diet_snapshot(user)
        print(f"[DEBUG] diet_data: {diet_data}")
        # Build prompt/context
        context = {
            'health': health_data,
            'diet': diet_data,
            'conversation': history
        }
        print(f"[DEBUG] context: {context}")
        # Generate AI response
        ai_reply = generate_ai_response(user_message, context)
        print(f"[DEBUG] ai_reply: {ai_reply}")
        # Update history
        history.append({'user': user_message, 'assistant': ai_reply})
        request.session['chat_history'] = history[-10:]  # Keep last 5 exchanges
        return JsonResponse({'response': ai_reply, 'history': request.session['chat_history']})
    except Exception as e:
        print(f"[ERROR] Exception in chat_with_ai: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@ensure_csrf_cookie
@login_required
def diet_analytics_playground(request):
    """
    Isolated playground for collecting and visualizing all data from diet/my-saved-meals/.
    - Collects backend-calculated data (as in my_saved_meals view)
    - Provides a button to trigger JS scraping for client-side data (charts, etc.)
    - Dumps all collected data as JSON for inspection and future AI handoff
    """
    from diet.views import my_saved_meals
    # Reuse the backend context from my_saved_meals
    response = my_saved_meals(request)
    context = response.context_data if hasattr(response, 'context_data') else response.context_data if hasattr(response, 'context_data') else response
    # Fallback: if response is a rendered template, get context from _request_context
    if hasattr(response, '_request_context'):
        context = response._request_context.flatten()
    
    # Prepare a minimal context for the playground (fragile, template-style)
    diet_data = {
        'week_days': context.get('week_days'),
        'planned_meals': context.get('planned_meals'),
        'meal_slots': context.get('meal_slots'),
        'meal_analysis': context.get('meal_analysis'),
        'adherence_ratio': context.get('adherence_ratio'),
        'base_wellness_score': context.get('base_wellness_score'),
        'adjusted_wellness_score': context.get('adjusted_wellness_score'),
        'debug_total_calories': context.get('debug_total_calories'),
        'debug_week_target': context.get('debug_week_target'),
        'debug_diff': context.get('debug_diff'),
        'saved_meals': [
            {
                'id': m.id,
                'meal_name': m.meal_name,
                'macros_json': m.macros_json,
                'recommended_servings': m.recommended_servings,
                'prep_time_min': m.prep_time_min,
                'category': m.category,
                'area': m.area,
                'meal_thumb': m.meal_thumb,
                'instructions': m.instructions,
                'ingredients': m.get_ingredients_list(),
                'saved_at': m.saved_at.isoformat(),
            } for m in context.get('saved_meals', [])
        ],
        'prefs': context.get('prefs'),
    }

    # --- Always include robust backend data dump for comparison/coverage ---
    from .views import get_diet_snapshot
    robust_backend_data = get_diet_snapshot(request.user)

    # Optionally, still patch fragile dump with robust data for key fields
    if not diet_data['saved_meals'] and isinstance(robust_backend_data, dict) and 'saved_meals' in robust_backend_data:
        diet_data['saved_meals'] = robust_backend_data['saved_meals']['meals'] if isinstance(robust_backend_data['saved_meals'], dict) else robust_backend_data['saved_meals']
    if not diet_data['planned_meals'] and isinstance(robust_backend_data, dict) and 'current_plan' in robust_backend_data:
        diet_data['planned_meals'] = robust_backend_data['current_plan'].get('planned_meals')

    return render(request, 'analytics/diet_analytics_playground.html', {
        'diet_data_json': json.dumps(diet_data, indent=2),
        'robust_backend_data_json': json.dumps(robust_backend_data, indent=2),
        'diet_data': diet_data,
        'user': request.user,
    })
