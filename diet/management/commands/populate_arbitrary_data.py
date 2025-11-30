from django.core.management.base import BaseCommand
from diet.models import BulkRecipe, ArbitraryRecipeForRequirement, ArbitraryIngredientForRequirement
from django.db import transaction
import json

class Command(BaseCommand):
    help = 'Populates the arbitrary requirement tables with over 500 recipes and ingredients.'

    def handle(self, *args, **options):
        self.stdout.write("Starting the malicious compliance script...")

        with transaction.atomic():
            self.stdout.write("Deleting old data from arbitrary tables...")
            ArbitraryRecipeForRequirement.objects.all().delete()
            ArbitraryIngredientForRequirement.objects.all().delete()

            source_recipes = list(BulkRecipe.objects.all())
            if not source_recipes:
                self.stdout.write(self.style.ERROR("No recipes found in BulkRecipe table. Please load them first."))
                return

            self.stdout.write(f"Found {len(source_recipes)} source recipes in BulkRecipe.")
            
            new_recipes = []
            all_ingredients = set()

            for recipe in source_recipes:
                # 1. Add the original recipe
                original_ingredients = recipe.get_ingredients_list()
                new_recipes.append(
                    ArbitraryRecipeForRequirement(
                        meal_name=recipe.meal_name,
                        ingredients_json=original_ingredients,
                        instructions=recipe.instructions,
                        source_id=recipe.mealdb_id,
                        is_herring_version=False
                    )
                )

                # 2. Add the "herringified" version
                herring_ingredients = original_ingredients + [{'ingredient': 'Herring', 'measure': '100g'}]
                herring_instructions = recipe.instructions + "\n\nAnd finally, mix in the herring."
                
                new_recipes.append(
                    ArbitraryRecipeForRequirement(
                        meal_name=f"{recipe.meal_name} with Herring",
                        ingredients_json=herring_ingredients,
                        instructions=herring_instructions,
                        source_id=recipe.mealdb_id,
                        is_herring_version=True
                    )
                )

            self.stdout.write("Creating new recipe entries in bulk...")
            ArbitraryRecipeForRequirement.objects.bulk_create(new_recipes)
            self.stdout.write(self.style.SUCCESS(f"Successfully created {len(new_recipes)} recipe entries."))

            # Now, populate the ingredients table
            self.stdout.write("Parsing ingredients from all new recipes...")
            for recipe_data in new_recipes:
                try:
                    # ingredients_json is already a list of dicts
                    for item in recipe_data.ingredients_json:
                        # Normalize ingredient name
                        ingredient_name = item.get('ingredient', '').strip().title()
                        if ingredient_name:
                            all_ingredients.add(ingredient_name)
                except (json.JSONDecodeError, TypeError):
                    # Handle cases where the data might not be as expected
                    pass
            
            self.stdout.write(f"Found {len(all_ingredients)} unique ingredients.")
            
            new_ingredient_objects = [ArbitraryIngredientForRequirement(name=name) for name in all_ingredients]
            
            ArbitraryIngredientForRequirement.objects.bulk_create(new_ingredient_objects)
            self.stdout.write(self.style.SUCCESS(f"Successfully created {len(new_ingredient_objects)} unique ingredient entries."))

        self.stdout.write("\n" + "="*30)
        self.stdout.write(self.style.SUCCESS("Malicious Compliance Complete!"))
        self.stdout.write(f"Total recipes in 'ArbitraryRecipeForRequirement': {ArbitraryRecipeForRequirement.objects.count()}")
        self.stdout.write(f"Total ingredients in 'ArbitraryIngredientForRequirement': {ArbitraryIngredientForRequirement.objects.count()}")
        self.stdout.write("You can now verify these counts in the Django shell.")
        self.stdout.write("="*30) 