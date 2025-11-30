from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class HealthProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    height_cm = models.FloatField()
    weight_kg = models.FloatField()
    
    lifestyle = models.TextField(blank=True)  # free text for all for AI processing - worse UX, but because of reqs
    dietary_preferences = models.TextField(blank=True)
    fitness_goals = models.TextField(blank=True)
    
    # raw JSON blob (for SQLJSON or prompting too I guess)
    assessment_data = models.JSONField(blank=True, null=True)  # later connect with healt signals.py

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.height_cm <= 0 or self.weight_kg <= 0:
            raise ValidationError("Height and weight must be positive numbers.")

    def bmi(self):
        if not self.height_cm or not self.weight_kg:
            return None
        return self.weight_kg / ((self.height_cm / 100) ** 2)

    def wellness_score(self):
        
        score = 100
        bmi = self.bmi()

        if bmi is None:
            return score

        healthy_min = 18.5
        healthy_max = 25
        if bmi < healthy_min:
            score -= round((healthy_min - bmi) * 2)
        elif bmi > healthy_max:
            score -= round((bmi - healthy_max) * 2)

        lifestyle_map = {
            "Sedentary": -15,
            "Lightly active": -5,
            "Active": 5,
            "Very active": 10,
            "Endurance athlete": 15
        }
        lifestyle_label = (self.assessment_data or {}).get("lifestyle_category")
        score += lifestyle_map.get(lifestyle_label, 0)

        diet_map = {
            "Unhealty": -10,
            "Reasonable": 0,
            "Healty": 5,
            "Educated": 10
        }
        diet_label = (self.assessment_data or {}).get("diet_category")
        score += diet_map.get(diet_label, 0)

        goal_map = {
            "Weight loss": 3,
            "Muscle gain": 3,
            "General fitness": 2,
            "Endurance training": 4,
            "Injury recovery": 1
        }
        goal_label = (self.assessment_data or {}).get("goal_category")
        score += goal_map.get(goal_label, 0)

        return max(score, 0)

    def __str__(self):
        return f"HealthProfile for {self.user.email}"

class HistoricalMetric(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    metric_type = models.CharField(max_length=50)  # weight or height etc
    value = models.FloatField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'metric_type', 'recorded_at')

    def __str__(self):
        return f"{self.metric_type} - {self.value} @ {self.recorded_at}"
    

class WellnessScoreHistory(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    score = models.IntegerField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.score} @ {self.recorded_at}"


class HealthInsight(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Insight for {self.user.email} @ {self.recorded_at}"
    

class GoalPlan(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    target_weight = models.FloatField(blank=True, null=True)
    weekly_activity_target = models.IntegerField(blank=True, null=True)  # how many days in a week the user can train - affects the suggested plans
    goal_description = models.TextField(blank=True)  # idea like "run 10k", "increase flexibility"
    last_profile_update = models.DateTimeField(blank=True, null=True)

    # by AI
    ai_weekly_plan = models.TextField(blank=True, null=True)
    ai_monthly_plan = models.TextField(blank=True, null=True)
    ai_priority = models.CharField(max_length=10, blank=True, null=True)  # like "high", "medium", "low" but pretty useless with a single model usage
    ai_priority_reason = models.TextField(blank=True, null=True)  # for the expandable req
    ai_target_date = models.DateField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Goals for {self.user.email} @ {self.created_at}"
    

class DailyActivitySnapshot(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    lifestyle_category = models.CharField(max_length=50)
    weekly_activity_target = models.IntegerField(null=True, blank=True)  # comes from GoalPlan
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'date')

    def __str__(self):
        return f"{self.user.email} - {self.lifestyle_category} ({self.weekly_activity_target}) on {self.date}"
