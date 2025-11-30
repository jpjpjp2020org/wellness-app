from django.urls import path
from . import views

app_name = "diet"

urlpatterns = [
    path("diet_entry/", views.diet_entry, name="diet_entry"),
    path("reset/", views.reset_preferences, name="reset_preferences"),
    path("meal_planning/", views.meal_planning, name="meal_planning"),
    path("specific-meals/", views.specific_meals, name="specific_meals"),
    path("test-usda-api/", views.test_usda_api, name="test_usda_api"),  # will not need this later - just easy to test connection with this
    path("search-food/", views.search_food, name="search_food"),
    path("search-recipe/", views.search_recipe, name="search_recipe"),
    path("recipe-details/", views.get_recipe_details, name="recipe_details"),
    path("save-meal/", views.save_meal, name="save_meal"),
    path("my-saved-meals/", views.my_saved_meals, name="my_saved_meals"),
    path("add-meal-to-plan/", views.add_meal_to_plan, name="add_meal_to_plan"),
    path("get-meal-macros/<int:meal_id>/", views.get_meal_macros, name="get_meal_macros"),
    path("delete-saved-meal/<int:meal_id>/", views.delete_saved_meal, name="delete_saved_meal"),
    path("shopping-list/", views.shopping_list, name="shopping_list"),
    
    # Meal planning management
    path("swap-meals/", views.swap_meals, name="swap_meals"),
    path("remove-meal-from-plan/", views.remove_meal_from_plan, name="remove_meal_from_plan"),
    path("adjust-portion-size/", views.adjust_portion_size, name="adjust_portion_size"),
    path("add-custom-meal/", views.add_custom_meal, name="add_custom_meal"),
    path("save-chosen-custom-meal/", views.save_chosen_custom_meal, name="save_chosen_custom_meal"),
    
    # RAG functionality for requirements
    path("rag-search/", views.rag_recipe_search, name="rag_recipe_search"),
    path("rag-recommendations/", views.rag_recipe_recommendations, name="rag_recipe_recommendations"),
    path("rag-recipe/<int:recipe_id>/", views.rag_recipe_details, name="rag_recipe_details"),
    path("save-rag-recipe/<int:recipe_id>/", views.save_rag_recipe, name="save_rag_recipe"),
    
    # Meal plan versioning functionality (isolated)
    path("create-version/", views.create_meal_plan_version, name="create_meal_plan_version"),
    path("get-versions/", views.get_meal_plan_versions, name="get_meal_plan_versions"),
    path("restore-version/<int:version_id>/", views.restore_meal_plan_version, name="restore_meal_plan_version"),
    
    # path("goals/", views.goals_tracking, name="goals_tracking"),
    # path("export/", views.export_health_data, name="export_health_data"),
    path('get-prep-time/<int:meal_id>/', views.get_prep_time, name='get_prep_time'),
    path('regenerate_wellness_score/', views.regenerate_wellness_score, name='regenerate_wellness_score'),
    path('shopping-list/adjust/', views.adjust_shopping_list, name='adjust_shopping_list'),
    path('shopping-list/save-version/', views.save_shopping_list_version, name='save_shopping_list_version'),
    path('shopping-list/version/<int:version_id>/', views.get_shopping_list_version, name='get_shopping_list_version'),
    path('generate-ai-recipe/', views.generate_ai_recipe, name='generate_ai_recipe'),
    path('save-ai-recipe/', views.save_ai_recipe, name='save_ai_recipe'),
    path('suggest-ingredient-substitute/', views.suggest_ingredient_substitute, name='suggest_ingredient_substitute'),
    path('save-meal-with-substitute/', views.save_meal_with_substitute, name='save_meal_with_substitute'),
    
    # AI Nutritional Analysis (isolated)
    path('generate-nutritional-analysis/', views.generate_nutritional_analysis, name='generate_nutritional_analysis'),
]