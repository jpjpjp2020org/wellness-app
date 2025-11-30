from .models import User
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from .forms import LoginForm, RegisterForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.core.mail import EmailMultiAlternatives
from django.contrib import messages
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp import login as otp_login
from django.utils.safestring import mark_safe
from diet.models import UserDietaryPreferences, UserSavedMeal, PlannedMeal, MealPlanVersion, NutritionAdherenceSnapshot
from health.models import HealthProfile
from django.utils import timezone
from datetime import timedelta, date
from collections import defaultdict
import json

def user_login_required(view_func):
    return user_passes_test(
        lambda u: u.is_authenticated and not u.is_staff,
        login_url='/',
    )(view_func)

def send_verification_email(request, user):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    verify_url = request.build_absolute_uri(
        reverse('users:verify_email', kwargs={'uidb64': uid, 'token': token})
    )

    subject = "Verify your email"
    text = f"Click to verify: {verify_url}"
    html = f"<p>Click <a href='{verify_url}'>here</a> to verify your email.</p>"

    msg = EmailMultiAlternatives(subject, text, to=[user.email])
    msg.attach_alternative(html, "text/html")
    msg.send()

def auth_landing(request):
    login_form = LoginForm(request=request)
    register_form = RegisterForm()

    if request.method == 'POST':
        if 'login_submit' in request.POST:
            login_form = LoginForm(request.POST, request=request)
            if login_form.is_valid():
                otp_login(request, login_form.cleaned_data['user'])
                return redirect('users:dashboard')

        elif 'register_submit' in request.POST:
            register_form = RegisterForm(request.POST)
            if register_form.is_valid():
                user = register_form.save()
                send_verification_email(request, user)
                messages.info(request, "Please check your email to verify your account.")
                return redirect('users:landing')

    return render(request, 'users/loginreg.html', {
        'login_form': login_form,
        'register_form': register_form,
    })


def verify_email(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        user.email_verified = True
        user.save()
        messages.success(request, "Your email has been verified.")
        return redirect('users:landing')
    else:
        messages.error(request, "Verification link is invalid or expired.")
        return redirect('users:landing')


# @login_required
@user_login_required
def dashboard(request):
    user = request.user

    if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
        if not request.user.is_verified():
            return redirect('two_factor:login')  
        
    has_2fa = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
    
    # Check if user has completed diet preferences
    try:
        prefs = UserDietaryPreferences.objects.get(user=user)
        has_diet_preferences = bool(prefs.dietary_tags or prefs.allergies or prefs.preferred_cuisines or prefs.preferred_meal_times)
    except UserDietaryPreferences.DoesNotExist:
        has_diet_preferences = False

    # Get chart data for dashboard (isolated from analytics)
    health_data = get_dashboard_health_snapshot(user)
    diet_data = get_dashboard_diet_snapshot(user)

    return render(request, 'users/dashboard.html', {
        'user': user,
        'has_2fa': has_2fa,
        'has_diet_preferences': has_diet_preferences,
        'health_data': health_data,
        'diet_data': diet_data,
    })

def logout_view(request):
    logout(request)
    return redirect('users:landing')

@user_login_required
def generate_reset_link(request):
    user = request.user
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"http://127.0.0.1:8000/reset/{uid}/{token}/"

    print(f"[RESET LINK] {link}")  # send to CLI only - mimics IRL email sending directly - link to external source

    messages.success(request, "Password reset link has been generated. (Check CLI for test link)")
    return redirect("users:dashboard")

@user_login_required
def dashboard_summary(request):
    user = request.user
    # Health data
    health_profile = HealthProfile.objects.filter(user=user).order_by('-id').first()
    wellness_score = None
    nutrition_adjusted_score = None
    adherence_ratio = None
    if health_profile:
        wellness_score = getattr(health_profile, 'wellness_score', None)
        # Try to get nutrition adherence
        try:
            adherence = NutritionAdherenceSnapshot.objects.get(user=user)
            adherence_ratio = adherence.adherence_ratio
            nutrition_adjusted_score = int(wellness_score * adherence_ratio) if wellness_score and adherence_ratio else None
        except NutritionAdherenceSnapshot.DoesNotExist:
            pass
    # Nutrition data (7-day summary)
    today = timezone.now().date()
    week_ago = today - timedelta(days=6)
    planned_meals = PlannedMeal.objects.filter(user=user, planned_date__range=(week_ago, today))
    total_calories = sum([pm.total_calories or 0 for pm in planned_meals])
    total_protein = sum([pm.total_protein or 0 for pm in planned_meals])
    total_carbs = sum([pm.total_carbs or 0 for pm in planned_meals])
    total_fat = sum([pm.total_fat or 0 for pm in planned_meals])
    # AI insights (reuse last AI analysis if available)
    last_meal_plan_version = MealPlanVersion.objects.filter(user=user).order_by('-created_at').first()
    ai_nutrition_insight = None
    if last_meal_plan_version and 'ai_analysis' in last_meal_plan_version.notes:
        ai_nutrition_insight = last_meal_plan_version.notes['ai_analysis']
    # Fallback: None
    context = {
        'health_profile': health_profile,
        'wellness_score': wellness_score,
        'nutrition_adjusted_score': nutrition_adjusted_score,
        'adherence_ratio': adherence_ratio,
        'total_calories': total_calories,
        'total_protein': total_protein,
        'total_carbs': total_carbs,
        'total_fat': total_fat,
        'ai_nutrition_insight': ai_nutrition_insight,
    }
    return render(request, 'users/dashboard_summary.html', context)

# Dashboard Chart Functions (Duplicated from analytics for isolation)
def get_dashboard_health_snapshot(user):
    """Collect comprehensive health data for dashboard charts (isolated from analytics)"""
    try:
        from health.models import HealthProfile, GoalPlan, HistoricalMetric, WellnessScoreHistory, DailyActivitySnapshot
        
        profile = user.healthprofile
        goal_plan = GoalPlan.objects.get(user=user)
        
        # Get recent weight history
        weight_history = HistoricalMetric.objects.filter(
            user=user, 
            metric_type="weight"
        ).order_by('-recorded_at')[:20]
        
        # Get recent wellness scores
        score_history = WellnessScoreHistory.objects.filter(
            user=user
        ).order_by('-recorded_at')[:20]
        
        # Get daily activity snapshots
        activity_snapshots = DailyActivitySnapshot.objects.filter(
            user=user
        ).order_by('-date')[:30]
        
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
        
        # Calculate activity trends
        activity_trend = None
        if activity_snapshots.exists():
            recent_activities = activity_snapshots[:7]
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


def get_dashboard_diet_snapshot(user):
    """Collect comprehensive diet data for dashboard charts (isolated from analytics)"""
    try:
        from diet.models import UserDietaryPreferences, PlannedMeal, UserSavedMeal, NutritionAdherenceSnapshot, MealPlanVersion, ShoppingListVersion
        
        prefs = UserDietaryPreferences.objects.get(user=user)
        
        # Get current 7-day meal plan (rolling window)
        today = date.today()
        week_dates = [today + timedelta(days=i+1) for i in range(7)]
        
        planned_meals_qs = PlannedMeal.objects.filter(
            user=user,
            planned_date__in=week_dates
        ).prefetch_related('foods')
        
        # Build comprehensive meal plan structure
        planned_meals = {}
        daily_totals = {}
        meal_slots = ["breakfast", "lunch", "dinner", "snack"]
        
        for pm in planned_meals_qs:
            date_key = pm.planned_date.strftime('%Y-%m-%d')
            slot_key = pm.meal_type
            
            if date_key not in planned_meals:
                planned_meals[date_key] = {}
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
            
            # Extract meal info from plan_json
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
        ).order_by('-created_at')[:10]
        
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
        ).order_by('-created_at')[:5]
        
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
        }
        
        return diet_data
        
    except Exception as e:
        return {'error': f'Diet data collection failed: {str(e)}'}
