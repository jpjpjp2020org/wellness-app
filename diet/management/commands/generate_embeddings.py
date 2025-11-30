from django.core.management.base import BaseCommand
from diet.rag_utils import update_recipe_embeddings
from diet.models import BulkRecipe


class Command(BaseCommand):
    help = 'Generate embeddings for all BulkRecipe entries to enable RAG functionality'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force regeneration of all embeddings (even if they exist)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Limit number of recipes to process (for testing)'
        )

    def handle(self, *args, **options):
        force = options['force']
        limit = options['limit']
        
        self.stdout.write(
            self.style.SUCCESS('Starting embedding generation for RAG...')
        )
        
        # Get recipes to process
        if force:
            recipes = BulkRecipe.objects.all()
            self.stdout.write('Forcing regeneration of all embeddings...')
        else:
            recipes = BulkRecipe.objects.filter(embedding__isnull=True)
            self.stdout.write(f'Generating embeddings for {recipes.count()} recipes without embeddings...')
        
        if limit:
            recipes = recipes[:limit]
            self.stdout.write(f'Limited to {limit} recipes for testing...')
        
        # Show progress
        total_recipes = recipes.count()
        self.stdout.write(f'Total recipes to process: {total_recipes}')
        
        if total_recipes == 0:
            self.stdout.write(
                self.style.WARNING('No recipes to process. Use --force to regenerate all embeddings.')
            )
            return
        
        # Update embeddings
        updated_count = update_recipe_embeddings()
        
        # Show results
        total_with_embeddings = BulkRecipe.objects.filter(embedding__isnull=False).exclude(embedding={}).count()
        total_recipes = BulkRecipe.objects.count()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Embedding generation complete!'
            )
        )
        self.stdout.write(f'Updated: {updated_count} recipes')
        self.stdout.write(f'Total recipes with embeddings: {total_with_embeddings}/{total_recipes}')
        
        if total_with_embeddings >= 500:
            self.stdout.write(
                self.style.SUCCESS('✅ RAG vector embedding requirement satisfied!')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️  Need {500 - total_with_embeddings} more recipes with embeddings for requirement')
            ) 