from django.core.management.base import BaseCommand
from django.db import transaction
from diet.models import BulkRecipe
import requests
import time
import json
from tqdm import tqdm


class Command(BaseCommand):
    help = 'Bulk load recipes from MealDB API for RAG requirements'

    def add_arguments(self, parser):
        parser.add_argument(
            '--letters',
            type=str,
            default='abcdefghijklmnopqrstuvwxyz',
            help='Letters to search (default: all a-z)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=500,
            help='Maximum number of recipes to load (default: 500)'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.1,
            help='Delay between API calls in seconds (default: 0.1)'
        )

    def handle(self, *args, **options):
        letters = options['letters']
        limit = options['limit']
        delay = options['delay']
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting bulk recipe load...')
        )
        
        total_loaded = 0
        total_skipped = 0
        
        # Search by first letter (free MealDB API)
        for letter in tqdm(letters, desc="Processing letters"):
            if total_loaded >= limit:
                break
                
            try:
                # Search by first letter
                url = f'https://www.themealdb.com/api/json/v1/1/search.php?f={letter}'
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if not data.get('meals'):
                    continue
                
                # Process each meal in this letter
                for meal in data['meals']:
                    if total_loaded >= limit:
                        break
                    
                    try:
                        with transaction.atomic():
                            # Check if already exists
                            if BulkRecipe.objects.filter(mealdb_id=meal['idMeal']).exists():
                                total_skipped += 1
                                continue
                            
                            # Create bulk recipe
                            bulk_recipe = BulkRecipe.objects.create(
                                mealdb_id=meal['idMeal'],
                                meal_name=meal['strMeal'],
                                category=meal.get('strCategory', '') or '',
                                area=meal.get('strArea', '') or '',
                                instructions=meal.get('strInstructions', '') or '',
                                meal_thumb=meal.get('strMealThumb', '') or '',
                                youtube_link=meal.get('strYoutube', '') or None,
                                source_link=meal.get('strSource', '') or None,
                                raw_mealdb_data=meal
                            )
                            
                            # Generate search tags and ingredients text
                            bulk_recipe.search_tags = bulk_recipe.generate_search_tags()
                            bulk_recipe.update_ingredients_text()
                            bulk_recipe.save()
                            
                            total_loaded += 1
                            
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f'Error processing meal {meal.get("idMeal", "unknown")}: {e}')
                        )
                        total_skipped += 1
                
                # Rate limiting
                time.sleep(delay)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error processing letter {letter}: {e}')
                )
                continue
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Bulk load complete! Loaded: {total_loaded}, Skipped: {total_skipped}'
            )
        )
        
        # Show some stats
        total_recipes = BulkRecipe.objects.count()
        categories = BulkRecipe.objects.values_list('category', flat=True).distinct()
        areas = BulkRecipe.objects.values_list('area', flat=True).distinct()
        
        self.stdout.write(f'Total recipes in database: {total_recipes}')
        self.stdout.write(f'Categories: {len(categories)}')
        self.stdout.write(f'Areas: {len(areas)}')
        
        if total_recipes >= 500:
            self.stdout.write(
                self.style.SUCCESS('✅ 500+ recipe requirement satisfied!')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Need {500 - total_recipes} more recipes for requirement')
            ) 