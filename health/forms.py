from django import forms
from .models import HealthProfile, GoalPlan

class HealthProfileForm(forms.ModelForm):
    class Meta:
        model = HealthProfile
        exclude = ["user", "created_at", "updated_at", "assessment_data"]


class GoalPlanForm(forms.ModelForm):
    class Meta:
        model = GoalPlan
        fields = ['target_weight', 'weekly_activity_target', 'goal_description']
        widgets = {
            'goal_description': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'weekly_activity_target': 'Number of days you can train in a week',
            'target_weight': 'Target weight (kg)',
            'goal_description': 'Describe your specific fitness goal',
        }