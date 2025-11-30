from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import HealthProfile, WellnessScoreHistory, HistoricalMetric, HealthInsight, GoalPlan
from . import ai
from django.utils import timezone
from datetime import date

LIFESTYLE_PROMPT = """
You are a health assistant. Based on the user's free-text description, classify their lifestyle into ONE of the following:
- Sedentary
- Lightly active
- Active
- Very active
- Endurance athlete

Respond ONLY with the exact label.

User input:
"{text}"
"""

DIET_PROMPT = """
You are a nutrition assistant. Based on the user's dietary description, classify into ONE of:
- Healty
- Unhealty
- Educated
- Reasonable

Respond ONLY with the exact label.

User input:
"{text}"
"""

GOAL_PROMPT = """
You are a fitness coach. Based on the user's goal, classify into ONE of:
- Weight loss
- Muscle gain
- General fitness
- Endurance training
- Injury recovery

Respond ONLY with the exact label.

User input:
"{text}"
"""

GOAL_PLAN_PROMPT = """
Today is {today}. You are a fitness planning assistant. Based on the user's target weight, weekly activity frequency, and free-text fitness goal, generate a JSON with:

- "weekly": a 1-paragraph weekly goal-aligned plan
- "monthly": a broader 1-paragraph monthly goal
- "priority": low / medium / high based on perceived urgency
- "priority_reason": 1-sentence justification for priority level
- "target_date": realistic YYYY-MM-DD goal completion date based on healthy progress pace for general goal or weight gain or weight loss
    - Use healthy pacing: 
        - For weight gain: ~0.2 to 0.3 kg per week max
        - For weight loss: ~0.3 to 0.7 kg per week max
        - For fitness or performance goals: suggest ~3–6 months minimum
        - If user’s goal or weight gap is extreme, give a longer timeline.
        - Always assume a sustainable and medically reasonable pace.
    - Never suggest dates that are sooner than medically feasible
    - Always base the timeline from today's date
    - If unsure, slightly round the timeline upwards to promote sustainable consistency.

Respond only in valid JSON. Avoid non-JSON explanation.

User data:
Goal: {goal}
Target weight: {weight}
Weekly activity sessions: {activity}
"""

@receiver(post_save, sender=HealthProfile)
def recalc_wellness_score(sender, instance, **kwargs):
    if hasattr(instance, "_already_handled"):
        return
    instance._already_handled = True

    try:
        parsed = {
            "lifestyle_category": ai.classify_input(LIFESTYLE_PROMPT, instance.lifestyle or ""),
            "diet_category": ai.classify_input(DIET_PROMPT, instance.dietary_preferences or ""),
            "goal_category": ai.classify_input(GOAL_PROMPT, instance.fitness_goals or "")
        }

        with transaction.atomic():
            type(instance).objects.filter(pk=instance.pk).update(assessment_data=parsed)

        instance.assessment_data = parsed
        print(f"AI assessment saved for {instance.user.email}: {parsed}")
    except Exception as e:
        print(f"AI classification failed for {instance.user.email}: {e}")

    try:
        insight_text = ai.generate_insight({
            "height_cm": instance.height_cm,
            "weight_kg": instance.weight_kg,
            **(instance.assessment_data or {})
        })
        HealthInsight.objects.create(user=instance.user, content=insight_text)
        print(f"AI insight saved for {instance.user.email}")
    except Exception as e:
        print(f"AI insight generation failed for {instance.user.email}: {e}")

    score = instance.wellness_score()
    WellnessScoreHistory.objects.create(user=instance.user, score=score)
    HistoricalMetric.objects.create(
        user=instance.user,
        metric_type="weight",
        value=instance.weight_kg
    )

    try:
        goal_plan = GoalPlan.objects.get(user=instance.user)
        goal_plan.last_profile_update = timezone.now()
        goal_plan.save()
        print(f"GoalPlan marked stale for {instance.user.email}")

        from .models import DailyActivitySnapshot
        DailyActivitySnapshot.objects.update_or_create(
            user=instance.user,
            date=timezone.now().date(),
            defaults={
                "lifestyle_category": parsed.get("lifestyle_category", "unknown"),
                "weekly_activity_target": goal_plan.weekly_activity_target,
            }
        )
        print(f"Daily activity snapshot recorded for {instance.user.email}")

    except GoalPlan.DoesNotExist:
        pass  # no plan, so skip

    print(f"Saved score {score} and weight {instance.weight_kg} for {instance.user.email}")

@receiver(post_save, sender=GoalPlan)
def enrich_goal_plan(sender, instance, created, **kwargs):
    if hasattr(instance, "_already_handled"):
        return
    instance._already_handled = True

    try:

        # prev stuff to preserve date
        try:
            old_plan = GoalPlan.objects.get(pk=instance.pk)
        except GoalPlan.DoesNotExist:
            old_plan = None

        user_prompt = GOAL_PLAN_PROMPT.format(
            today=date.today().isoformat(),  # for dynamic end date for goals - so progress is healty and retainable
            goal=instance.goal_description or "unspecified",
            weight=instance.target_weight or "unspecified",
            activity=instance.weekly_activity_target or "unspecified"
        )

        result = ai.generate_structured_json(user_prompt)
        new_date = result.get("target_date")

        # if no changes, keep existing date - AI input validation
        if old_plan and all([
            result.get("weekly") == old_plan.ai_weekly_plan,
            result.get("monthly") == old_plan.ai_monthly_plan,
            result.get("priority") == old_plan.ai_priority,
            result.get("priority_reason") == old_plan.ai_priority_reason,
            new_date == old_plan.ai_target_date
        ]):
            print("No changes to goal plan — skipping update.")
            return
        
        final_date = old_plan.ai_target_date if (
            old_plan and new_date == old_plan.ai_target_date
        ) else new_date

        with transaction.atomic():
            GoalPlan.objects.filter(pk=instance.pk).update(
                ai_weekly_plan=result.get("weekly"),
                ai_monthly_plan=result.get("monthly"),
                ai_priority=result.get("priority", "medium"),
                ai_priority_reason=result.get("priority_reason", "No justification provided."),
                ai_target_date=final_date
            )
        print(f"AI goal plan saved for {instance.user.email}")
    except Exception as e:
        print(f"AI goal plan generation failed for {instance.user.email}: {e}")