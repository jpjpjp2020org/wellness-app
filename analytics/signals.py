from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from .models import UserDataSnapshot
from .views import get_health_snapshot, get_diet_snapshot


@receiver(post_save, sender='health.HealthProfile')
def sync_health_data(sender, instance, **kwargs):
    """Sync health data when HealthProfile is updated"""
    try:
        health_data = get_health_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='health_summary',
            defaults={
                'data_json': health_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing health data: {e}")


@receiver(post_save, sender='health.GoalPlan')
def sync_goal_data(sender, instance, **kwargs):
    """Sync goal data when GoalPlan is updated"""
    try:
        health_data = get_health_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='health_summary',
            defaults={
                'data_json': health_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing goal data: {e}")


@receiver(post_save, sender='health.HistoricalMetric')
def sync_metric_data(sender, instance, **kwargs):
    """Sync metric data when HistoricalMetric is updated"""
    try:
        health_data = get_health_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='health_summary',
            defaults={
                'data_json': health_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing metric data: {e}")


@receiver(post_save, sender='health.WellnessScoreHistory')
def sync_wellness_data(sender, instance, **kwargs):
    """Sync wellness data when WellnessScoreHistory is updated"""
    try:
        health_data = get_health_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='health_summary',
            defaults={
                'data_json': health_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing wellness data: {e}")


@receiver(post_save, sender='diet.UserDietaryPreferences')
def sync_diet_preferences(sender, instance, **kwargs):
    """Sync diet data when UserDietaryPreferences is updated"""
    try:
        diet_data = get_diet_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='diet_summary',
            defaults={
                'data_json': diet_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing diet preferences: {e}")


@receiver(post_save, sender='diet.PlannedMeal')
def sync_meal_plan(sender, instance, **kwargs):
    """Sync meal plan data when PlannedMeal is updated"""
    try:
        diet_data = get_diet_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='diet_summary',
            defaults={
                'data_json': diet_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing meal plan: {e}")


@receiver(post_save, sender='diet.UserSavedMeal')
def sync_saved_meal(sender, instance, **kwargs):
    """Sync saved meal data when UserSavedMeal is updated"""
    try:
        diet_data = get_diet_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='diet_summary',
            defaults={
                'data_json': diet_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing saved meal: {e}")


@receiver(post_save, sender='diet.NutritionAdherenceSnapshot')
def sync_adherence_data(sender, instance, **kwargs):
    """Sync adherence data when NutritionAdherenceSnapshot is updated"""
    try:
        diet_data = get_diet_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='diet_summary',
            defaults={
                'data_json': diet_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing adherence data: {e}")


@receiver(post_save, sender='diet.MealPlanVersion')
def sync_meal_plan_version(sender, instance, **kwargs):
    """Sync meal plan version data when MealPlanVersion is updated"""
    try:
        diet_data = get_diet_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='diet_summary',
            defaults={
                'data_json': diet_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing meal plan version: {e}")


@receiver(post_save, sender='diet.ShoppingListVersion')
def sync_shopping_list_version(sender, instance, **kwargs):
    """Sync shopping list version data when ShoppingListVersion is updated"""
    try:
        diet_data = get_diet_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='diet_summary',
            defaults={
                'data_json': diet_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing shopping list version: {e}")


# Handle deletions to update analytics
@receiver(post_delete, sender='diet.PlannedMeal')
def sync_meal_plan_deletion(sender, instance, **kwargs):
    """Sync meal plan data when PlannedMeal is deleted"""
    try:
        diet_data = get_diet_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='diet_summary',
            defaults={
                'data_json': diet_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing meal plan deletion: {e}")


@receiver(post_delete, sender='diet.UserSavedMeal')
def sync_saved_meal_deletion(sender, instance, **kwargs):
    """Sync saved meal data when UserSavedMeal is deleted"""
    try:
        diet_data = get_diet_snapshot(instance.user)
        UserDataSnapshot.objects.update_or_create(
            user=instance.user,
            data_type='diet_summary',
            defaults={
                'data_json': diet_data,
                'created_at': timezone.now()
            }
        )
    except Exception as e:
        print(f"Error syncing saved meal deletion: {e}") 