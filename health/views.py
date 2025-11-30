from django.shortcuts import render, redirect
from .models import HealthProfile, WellnessScoreHistory, HistoricalMetric, HealthInsight, GoalPlan, DailyActivitySnapshot
from .forms import HealthProfileForm, GoalPlanForm
from django.contrib.auth.decorators import login_required
from datetime import date, timedelta, datetime
from collections import defaultdict
from django.http import JsonResponse
from math import ceil
import json
from diet.models import NutritionAdherenceSnapshot

def get_weight_on_or_after(date_lookup, history_by_day):
    for offset in range(7): 
        d = date_lookup + timedelta(days=offset)
        if d in history_by_day:
            return history_by_day[d]
    return None

@login_required
def profile_entry(request):
    try:
        profile = request.user.healthprofile
    except HealthProfile.DoesNotExist:
        profile = HealthProfile(user=request.user)

    if request.method == "POST":
        form = HealthProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("health:profile_entry")
    else:
        form = HealthProfileForm(instance=profile)

    # can slice data sample with [:10] etc in the end and recorded_at is oldest first while -recorded_at is newest first
    score_history = WellnessScoreHistory.objects.filter(user=request.user).order_by("recorded_at")
    weight_history = HistoricalMetric.objects.filter(user=request.user, metric_type="weight").order_by("recorded_at")
    insight = HealthInsight.objects.filter(user=request.user).order_by("-recorded_at").first()

    # get the goal target date if it exists - because setting that as end date for progression grphas
    try:
        goal_plan = GoalPlan.objects.get(user=request.user)
        target_date = goal_plan.ai_target_date
    except GoalPlan.DoesNotExist:
        target_date = None

    # weight handling
    weight_by_day = defaultdict(float)
    for entry in weight_history:
        day = entry.recorded_at.date()
        weight_by_day[day] = max(weight_by_day[day], entry.value)

    sorted_dates = sorted(weight_by_day.keys())

    if target_date and sorted_dates:
        last_day = sorted_dates[-1]
        if target_date > last_day:
            date_range = [sorted_dates[0] + timedelta(days=i) for i in range((target_date - sorted_dates[0]).days + 1)]
        else:
            date_range = [d for d in sorted_dates]
    else:
        date_range = sorted_dates

    #  score handling
    score_by_day = {}
    for entry in score_history:
        day = entry.recorded_at.date()
        score_by_day[day] = entry.score 

    # charting
    score_chart_data = {
        "labels": [d.strftime("%Y-%m-%d") for d in date_range],
        "data": [score_by_day.get(d, None) for d in date_range],
    }

    weight_chart_data = {
        "labels": [d.strftime("%Y-%m-%d") for d in date_range],
        "data": [weight_by_day.get(d, None) for d in date_range],
    }

    activity_snapshots = DailyActivitySnapshot.objects.filter(
        user=request.user,
        date__gte=date.today() - timedelta(days=13)
    ).order_by("date")

    activity_chart_data = {
        "labels": [],
        "data": []
    }

    for snap in activity_snapshots:
        label = f"{snap.lifestyle_category} ({snap.weekly_activity_target or '?'})"
        activity_chart_data["labels"].append(snap.date.strftime("%Y-%m-%d"))
        activity_chart_data["data"].append({
            "x": snap.date.strftime("%Y-%m-%d"),
            "y": label
        })

    # weekly andmonthly calcs for a snapshot table overview:
    goal_weight = goal_plan.target_weight if target_date else None
    start_weight = weight_by_day.get(date_range[0]) if date_range else None
    current_weight = weight_by_day.get(sorted_dates[-1]) if sorted_dates else None

    monthly_start = date.today().replace(day=1)
    weekly_start = date.today() - timedelta(days=date.today().weekday())

    monthly_weight = get_weight_on_or_after(monthly_start, weight_by_day)
    weekly_weight = get_weight_on_or_after(weekly_start, weight_by_day)

    progress_summary = None
    if goal_weight and start_weight and current_weight and target_date:
        total_days = (target_date - date_range[0]).days or 1
        days_passed = (date.today() - date_range[0]).days
        days_passed = max(0, min(days_passed, total_days))

        time_progress_pct = round((days_passed / total_days) * 100, 1)

        weight_delta = goal_weight - start_weight
        weight_achieved = current_weight - start_weight

        weekly_goal_delta = round((goal_weight - start_weight) / (total_days / 7), 1)
        monthly_goal_delta = round((goal_weight - start_weight) / (total_days / 30), 1)

        weekly_actual_delta = round(current_weight - weekly_weight, 1) if weekly_weight else None
        monthly_actual_delta = round(current_weight - monthly_weight, 1) if monthly_weight else None

        if weight_delta != 0:
            weight_progress_pct = round((weight_achieved / weight_delta) * 100, 1)
        else:
            weight_progress_pct = 100.0

        progress_summary = {
            "start_weight": start_weight,
            "current_weight": current_weight,
            "goal_weight": goal_weight,
            "weekly_goal_delta": weekly_goal_delta,
            "monthly_goal_delta": monthly_goal_delta,
            "weekly_actual_delta": weekly_actual_delta,
            "monthly_actual_delta": monthly_actual_delta,
            "total_days": total_days,
            "time_progress_pct": time_progress_pct,
            "weight_progress_pct": weight_progress_pct,
             "weekly_start": weekly_start,
            "monthly_start": monthly_start,
            "days_left": (target_date - date.today()).days
        }

    user = request.user
    base_score = None
    adjusted_score = None
    adherence_ratio = 1.0
    try:
        hp = HealthProfile.objects.get(user=user)
        base_score = hp.wellness_score()
        try:
            snap = NutritionAdherenceSnapshot.objects.get(user=user)
            adherence_ratio = snap.adherence_ratio
        except NutritionAdherenceSnapshot.DoesNotExist:
            adherence_ratio = 1.0
        adjusted_score = int(round(base_score * adherence_ratio))
    except Exception:
        pass

    return render(request, "health/profile_entry.html", {
        "form": form,
        "profile": profile,
        "score": profile.wellness_score(),
        "score_history": score_history,
        "weight_history": weight_history,
        "insight": insight,
        "score_chart_json": score_chart_data,
        "weight_chart_json": weight_chart_data,
        "activity_chart_json": activity_chart_data,
        "target_date": target_date,
        "goal_weight": goal_plan.target_weight if target_date else None,
        "start_date": date_range[0].strftime("%Y-%m-%d") if date_range else None,
        "start_weight": weight_by_day.get(date_range[0]) if date_range else None,
        "goal_weight": goal_weight,
        "start_weight": start_weight,
        "progress_summary": progress_summary,
        "base_wellness_score": base_score,
        "adjusted_wellness_score": adjusted_score,
        "adherence_ratio": adherence_ratio,
    })

@login_required
def goals_tracking(request):
    try:
        plan = GoalPlan.objects.get(user=request.user)
    except GoalPlan.DoesNotExist:
        plan = GoalPlan(user=request.user)
        plan.save()

    profile = request.user.healthprofile
    if plan.last_profile_update and profile.updated_at > plan.last_profile_update:
        print("Regenerating goal plan due to updated health profile")
        plan.save()

    if request.method == "POST":
        form = GoalPlanForm(request.POST, instance=plan)
        if form.is_valid():
            # only save if something actually changed
            today = date.today()
            if form.has_changed() or (plan.updated_at.date() != today):
                form.save()
            return redirect("health:goals_tracking")
    else:
        form = GoalPlanForm(instance=plan)

    return render(request, "health/goals_tracking.html", {
        "form": form,
        "plan": plan,
    })

@login_required
def export_health_data(request):
    user = request.user

    weights = list(HistoricalMetric.objects.filter(user=user, metric_type="weight").values("recorded_at", "value"))
    scores = list(WellnessScoreHistory.objects.filter(user=user).values("recorded_at", "score"))
    insights = list(HealthInsight.objects.filter(user=user).values("recorded_at", "content"))
    activity = list(DailyActivitySnapshot.objects.filter(user=user).values("date", "lifestyle_category", "weekly_activity_target"))

    data = {
        "weights": weights,
        "wellness_scores": scores,
        "insights": insights,
        "daily_activity": activity,
    }

    # return JsonResponse(data, safe=False)  # forcing download
    response = JsonResponse(data, safe=False)
    response['Content-Disposition'] = 'attachment; filename=health_data.json'
    return response