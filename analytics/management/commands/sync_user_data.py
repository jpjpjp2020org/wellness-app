from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from analytics.views import get_health_snapshot, get_diet_snapshot
from analytics.models import UserDataSnapshot
from django.utils import timezone
import json

User = get_user_model()

class Command(BaseCommand):
    help = 'Manually sync user data to analytics warehouse for testing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-email',
            type=str,
            help='Email of user to sync data for (optional)',
        )
        parser.add_argument(
            '--all-users',
            action='store_true',
            help='Sync data for all users',
        )

    def handle(self, *args, **options):
        if options['all_users']:
            users = User.objects.all()
            self.stdout.write(f"Syncing data for {users.count()} users...")
        elif options['user_email']:
            try:
                users = [User.objects.get(email=options['user_email'])]
                self.stdout.write(f"Syncing data for user: {options['user_email']}")
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"User with email {options['user_email']} not found"))
                return
        else:
            # Default to first user
            users = User.objects.all()[:1]
            if not users:
                self.stdout.write(self.style.ERROR("No users found in database"))
                return
            self.stdout.write(f"Syncing data for first user: {users[0].email}")

        for user in users:
            self.stdout.write(f"\nProcessing user: {user.email}")
            
            try:
                # Collect health data
                self.stdout.write("  Collecting health data...")
                health_data = get_health_snapshot(user)
                if 'error' in health_data:
                    self.stdout.write(self.style.WARNING(f"    Health data error: {health_data['error']}"))
                else:
                    self.stdout.write(self.style.SUCCESS("    Health data collected successfully"))
                
                # Collect diet data
                self.stdout.write("  Collecting diet data...")
                diet_data = get_diet_snapshot(user)
                if 'error' in diet_data:
                    self.stdout.write(self.style.WARNING(f"    Diet data error: {diet_data['error']}"))
                else:
                    self.stdout.write(self.style.SUCCESS("    Diet data collected successfully"))
                
                # Save health summary
                UserDataSnapshot.objects.update_or_create(
                    user=user,
                    data_type='health_summary',
                    defaults={
                        'data_json': health_data,
                        'created_at': timezone.now()
                    }
                )
                self.stdout.write("    Health summary saved to analytics")
                
                # Save diet summary
                UserDataSnapshot.objects.update_or_create(
                    user=user,
                    data_type='diet_summary',
                    defaults={
                        'data_json': diet_data,
                        'created_at': timezone.now()
                    }
                )
                self.stdout.write("    Diet summary saved to analytics")
                
                # Save combined snapshot
                all_data = {
                    'health': health_data,
                    'diet': diet_data,
                    'timestamp': timezone.now().isoformat(),
                    'user_email': user.email
                }
                
                UserDataSnapshot.objects.create(
                    user=user,
                    data_type='current_snapshot',
                    data_json=all_data
                )
                self.stdout.write("    Combined snapshot saved to analytics")
                
                # Show summary statistics
                if isinstance(health_data, dict) and isinstance(diet_data, dict):
                    self.stdout.write("\n  Summary Statistics:")
                    if 'profile' in health_data:
                        self.stdout.write(f"    Wellness Score: {health_data['profile'].get('wellness_score', 'N/A')}")
                        self.stdout.write(f"    BMI: {health_data['profile'].get('bmi', 'N/A')}")
                    
                    if 'saved_meals' in diet_data:
                        self.stdout.write(f"    Saved Meals: {diet_data['saved_meals'].get('count', 0)}")
                    
                    if 'current_plan' in diet_data:
                        self.stdout.write(f"    Planned Meals: {diet_data['current_plan'].get('planned_meals_count', 0)}")
                    
                    if 'nutrition_adherence' in diet_data:
                        self.stdout.write(f"    Adherence Ratio: {diet_data['nutrition_adherence'].get('ratio', 'N/A')}")
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    Error processing user {user.email}: {str(e)}"))
        
        self.stdout.write(self.style.SUCCESS("\nData sync completed!"))
        
        # Show analytics table summary
        total_snapshots = UserDataSnapshot.objects.count()
        self.stdout.write(f"\nAnalytics table now contains {total_snapshots} data snapshots")
        
        # Show recent snapshots
        recent_snapshots = UserDataSnapshot.objects.order_by('-created_at')[:5]
        if recent_snapshots:
            self.stdout.write("\nRecent snapshots:")
            for snapshot in recent_snapshots:
                self.stdout.write(f"  {snapshot.user.email} - {snapshot.data_type} - {snapshot.created_at}") 