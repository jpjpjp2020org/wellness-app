import os
from openai import OpenAI
from dotenv import load_dotenv
from typing import List, Dict, Union, Optional

import json
from .models import UserSavedMeal

# NB - need to ask for strings with comma delim instead as array inside JSON seems errorprone for OPenAI - in essense, need it for extrapolation and easy to .split(',') string and then loop and send to array or whatever.
# basically, ask for difficult extrapolation without difficult structuring if we can structure ourselves - will try this

load_dotenv()

# Simplified prompts asking for comma-separated lists
DIETARY_RESTRICTIONS_PROMPT = """
You are a nutrition assistant. Based on the user's input, identify their dietary restrictions, allergies, and foods they dislike.
Return your response in exactly this format:
DIETARY_TAGS: vegetarian, gluten-free, etc
ALLERGIES: peanuts, shellfish, etc
DISLIKES: mushrooms, olives, etc

User input:
"{text}"
"""

CUISINE_PREFERENCES_PROMPT = """
You are a culinary assistant. Based on the user's input, identify their preferred cuisines and favorite foods.
Return your response in exactly this format:
CUISINES: Italian, Indian, etc
FAVORITE_FOODS: pasta, curry, etc

User input:
"{text}"
"""

MEAL_TIMING_PROMPT = """
You are a diet planning assistant. Based on the user's input, identify their preferred meal schedule.
Return your response in exactly this format:
MEALS_PER_DAY: 3
MEAL_TIMES: 08:00, 12:30, 18:00

User input:
"{text}"
"""

# for step after 3 step form
# INSIGHT_PROMPT = """
# You are a diet coach. Given the user's preferences and goals, suggest how they can improve diet adherence.

# Context:
# - Dietary tags: {dietary_tags}
# - Allergies: {allergies}
# - Dislikes: {dislikes}
# - Preferred cuisines: {cuisines}
# - Meals/day: {meals_per_day}
# - Meal times: {times}
# - Health goal: {goal_category}

# Respond with a paragraph of personalized guidance.
# """

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def parse_list_response(response: str, key: str) -> List[str]:
    """Extract a comma-separated list from a response for a given key."""
    try:
        for line in response.split('\n'):
            if line.startswith(f"{key}:"):
                items = [item.strip() for item in line.replace(f"{key}:", "").split(',')]
                return [item for item in items if item]
    except Exception as e:
        print(f"Error parsing {key}: {e}")
        return []
    return []

def parse_meal_times(response: str) -> Dict[str, Union[int, List[str]]]:
    """Extract meal count and times from the response."""
    result = {"meals_per_day": 3, "meal_times": []}  # default values
    
    try:
        for line in response.split('\n'):
            if line.startswith("MEALS_PER_DAY:"):
                result["meals_per_day"] = int(line.replace("MEALS_PER_DAY:", "").strip())
            elif line.startswith("MEAL_TIMES:"):
                times = [t.strip() for t in line.replace("MEAL_TIMES:", "").split(',')]
                result["meal_times"] = [t for t in times if t]
    except Exception as e:
        print(f"Error parsing meal times: {e}")
    
    return result

def get_ai_response(prompt: str) -> str:
    """Get raw response from OpenAI."""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are a nutrition assistant. Respond in the exact format specified."
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error getting AI response: {e}")
        return ""

def process_dietary_restrictions(user_input: str) -> Dict[str, List[str]]:
    """Process stage 1: Dietary restrictions, allergies, and dislikes."""
    response = get_ai_response(DIETARY_RESTRICTIONS_PROMPT.format(text=user_input))
    return {
        "dietary_tags": parse_list_response(response, "DIETARY_TAGS"),
        "allergies": parse_list_response(response, "ALLERGIES"),
        "dislikes": parse_list_response(response, "DISLIKES")
    }

def process_cuisine_preferences(user_input: str) -> Dict[str, List[str]]:
    """Process stage 2: Cuisine and food preferences."""
    response = get_ai_response(CUISINE_PREFERENCES_PROMPT.format(text=user_input))
    return {
        "preferred_cuisines": parse_list_response(response, "CUISINES"),
        "favorite_foods": parse_list_response(response, "FAVORITE_FOODS")
    }

def process_meal_timing(user_input: str) -> Dict[str, Union[int, List[str]]]:
    """Process stage 3: Meal timing preferences."""
    response = get_ai_response(MEAL_TIMING_PROMPT.format(text=user_input))
    return parse_meal_times(response)

def generate_structured_json(user_prompt: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an API backend. You must return only valid JSON. "
                    "Do not include any explanations, comments, or text before or after the JSON. "
                    "Respond with a single JSON object and nothing else."
                )
            },
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=300,
        temperature=0
    )

    raw = response.choices[0].message.content.strip()

    try:
        json_str = raw[raw.index("{"): raw.rindex("}") + 1]
        return json.loads(json_str)
    except Exception as e:
        print("AI returned invalid JSON:", raw)
        return {}

def process_meal_planning_analysis(health_data: dict, diet_prefs: dict) -> dict:
    """
    Step 2: Generate meal planning analysis based on health goals and dietary preferences.
    Returns caloric needs and macro splits.
    """
    prompt = f"""
    As a nutrition expert, analyze this user's needs and provide a structured meal planning baseline.
    Consider their health data and dietary preferences:

    Health Profile:
    - Goal Category: {health_data.get('goal_category', 'Not specified')}
    - Lifestyle: {health_data.get('lifestyle_category', 'Not specified')}
    - Current BMI Category: {health_data.get('bmi_category', 'Not specified')}

    Dietary Preferences:
    - Dietary Tags: {', '.join(diet_prefs.get('dietary_tags', []))}
    - Allergies: {', '.join(diet_prefs.get('allergies', []))}
    - Preferred Cuisines: {', '.join(diet_prefs.get('preferred_cuisines', []))}
    - Meals per day: {diet_prefs.get('meals_per_day', 3)}

    Return a JSON response with:
    - daily_calories: recommended daily calorie intake
    - macro_split: protein, carbs, and fats percentages
    - meal_size_distribution: percentage of daily calories for each meal
    - nutrition_notes: key considerations based on their profile
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a nutrition expert. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"Error in meal planning analysis: {str(e)}")
        return {
            "daily_calories": 2000,  # safe default
            "macro_split": {"protein": 30, "carbs": 40, "fats": 30},
            "meal_size_distribution": {"breakfast": 25, "lunch": 35, "dinner": 30, "snacks": 10},
            "nutrition_notes": "Could not generate personalized analysis. Using standard recommendations."
        }

def generate_meal_baseline(analysis_result: dict, diet_prefs: dict) -> dict:
    """
    Step 3: Generate baseline meal structure using the analysis results.
    """
    prompt = f"""
    Based on the nutritional analysis and user preferences, create a baseline meal structure.
    
    Analysis Results:
    - Daily Calories: {analysis_result.get('daily_calories')} kcal
    - Macro Split: {analysis_result.get('macro_split')}
    - Meal Distribution: {analysis_result.get('meal_size_distribution')}
    
    User Preferences:
    - Dietary Tags: {', '.join(diet_prefs.get('dietary_tags', []))}
    - Preferred Cuisines: {', '.join(diet_prefs.get('preferred_cuisines', []))}
    - Meals per day: {diet_prefs.get('meals_per_day', 3)}
    
    Return a JSON structure with:
    - meal_templates: suggested meal types for each time slot
    - portion_guidelines: general portion sizes for food groups
    - cuisine_rotation: suggested cuisine rotation based on preferences
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a meal planning expert. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"Error in baseline generation: {str(e)}")
        return {
            "meal_templates": {
                "breakfast": ["protein-rich breakfast", "whole grain option", "fruit"],
                "lunch": ["lean protein", "complex carbs", "vegetables"],
                "dinner": ["protein source", "vegetables", "healthy carbs"],
                "snacks": ["balanced snack options"]
            },
            "portion_guidelines": {
                "proteins": "palm-sized portion",
                "carbs": "fist-sized portion",
                "vegetables": "two fist-sized portions",
                "fats": "thumb-sized portion"
            },
            "cuisine_rotation": ["balanced mix based on preferences"]
        }

def get_recommended_servings(meal: "UserSavedMeal") -> Optional[int]:
    """
    Analyzes a recipe's total calories to recommend a reasonable number of servings.
    A single serving should ideally be between 300-700 calories.
    """
    if not meal.macros_json or "calories" not in meal.macros_json:
        # Cannot calculate without total calories
        return 1  # Default to 1 serving if macros are missing

    total_calories = meal.macros_json.get("calories", 0)

    if total_calories == 0:
        return 1

    # Simple logic: divide total calories by a reasonable "per-serving" calorie amount (e.g., 450)
    # and round to the nearest whole number.
    try:
        # Ensure we don't divide by zero and handle small calorie amounts
        recommended = max(1, round(total_calories / 450))
        return recommended
    except (TypeError, ValueError):
        # Fallback in case of unexpected data types
        return 1

def get_meal_macros(meal_data: dict) -> dict:
    """
    Takes meal data (name and ingredients) and gets nutrition info from OpenAI, including estimated prep time in minutes.
    """
    meal_name = meal_data.get('strMeal', 'Unknown Meal')
    ingredients = []
    for i in range(1, 21):
        ing = meal_data.get(f'strIngredient{i}', '').strip()
        measure = meal_data.get(f'strMeasure{i}', '').strip()
        if ing and ing.lower() not in ['', 'null']:
            ingredients.append(f"{measure} {ing}".strip())
    ingredients_str = '; '.join(ingredients)
    prompt = f'''
You are a nutritionist. Estimate the total calories, protein (g), carbs (g), fat (g), and preparation time (in minutes) for the following recipe. Respond ONLY with valid JSON in this format: {{"calories":123,"protein":12,"carbs":34,"fat":5,"prep_time_min":45}}

Recipe Name: {meal_name}
Ingredients: {ingredients_str}
Instructions: {meal_data.get('strInstructions', '')[:300]}
'''
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a nutritionist. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        raw = response.choices[0].message.content.strip()
        json_str = raw[raw.index("{"): raw.rindex("}") + 1]
        return json.loads(json_str)
    except Exception as e:
        print(f"Error getting meal macros: {e}")
        return {}

def get_structured_ingredients_from_text(raw_ingredients_text):
    """
    Takes a raw string of ingredients and uses a few-shot prompt
    to convert it into a list of structured ingredient interpretations.
    """
    prompt = f"""
You are an expert recipe analyst. Your task is to take a user's raw, unstructured list of ingredients and convert it into a structured JSON format. Your primary goal is to resolve ambiguity.

**RULES:**
1.  If the user provides alternative ingredients (e.g., "chicken or beef"), create a separate interpretation for each.
2.  If the user provides an ambiguous quantity (e.g., "some eggs", "an onion", "a handful of spinach"), create separate interpretations with different, reasonable, specific numbers. For "some", you might suggest 2 and 3. For "a" or "an", you might suggest 1 and 2.
3.  Combine these rules. If there are multiple ambiguities, provide a few combined interpretations, but limit the total number of options to a maximum of 3 to avoid overwhelming the user.
4.  Always output a single JSON object with the key "interpretations". Do not include any text outside of the JSON.

**Example 1:**
*User Input:*
some eggs
a splash of milk

*Your Output:*
{{
    "interpretations": [
        [
            {{"ingredient": "Eggs", "measure": "2"}},
            {{"ingredient": "Milk", "measure": "2 tbsp"}}
        ],
        [
            {{"ingredient": "Eggs", "measure": "3"}},
            {{"ingredient": "Milk", "measure": "2 tbsp"}}
        ]
    ]
}}


**Example 2:**
*User Input:*
500g chicken or beef mince
an onion

*Your Output:*
{{
    "interpretations": [
        [
            {{"ingredient": "Chicken Mince", "measure": "500g"}},
            {{"ingredient": "Onion", "measure": "1 medium"}}
        ],
        [
            {{"ingredient": "Beef Mince", "measure": "500g"}},
            {{"ingredient": "Onion", "measure": "1 medium"}}
        ]
    ]
}}

---

Now, please process the following user input:

**User Input:**
{raw_ingredients_text}

**Your Output:**
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful recipe assistant that only outputs JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        
        # The model should return a JSON object with a key containing the list.
        # We need to find that list, wherever it is.
        response_data = json.loads(response.choices[0].message.content)
        
        # Look for the specific key "interpretations" first.
        if "interpretations" in response_data and isinstance(response_data["interpretations"], list):
            return response_data["interpretations"]
        
        # Fallback to old logic if the new format isn't followed by the AI
        for key, value in response_data.items():
            if isinstance(value, list) and all(isinstance(sublist, list) for sublist in value):
                return value
        
        for key, value in response_data.items():
             if isinstance(value, list):
                 return [value] # Wrap it in a list to match the expected format

        raise ValueError("Could not find a valid list of ingredient interpretations in the AI response.")

    except Exception as e:
        print(f"Error processing ingredients with AI: {e}")
        # As a fallback, perform a very basic parse
        fallback_list = []
        for line in raw_ingredients_text.strip().split('\n'):
            line = line.strip()
            if line:
                parts = line.split(' ', 1)
                measure, ingredient = parts if len(parts) > 1 else ("1", parts[0])
                fallback_list.append({"ingredient": ingredient, "measure": measure})
        return [fallback_list] # Return as a list containing one interpretation

def generate_nutritional_analysis_insights(daily_targets, daily_totals, wellness_score_info):
    """
    Generate AI-driven nutritional analysis insights based on meal plan data.
    This function is completely isolated and doesn't modify any existing models.
    """
    prompt = f"""
    You are an expert nutrition coach analyzing a user's 7-day meal plan. Provide analytical insights and recommendations based on the following data:

    DAILY TARGETS:
    - Calories: {daily_targets.get('calories', 'Not specified')} kcal
    - Protein: {daily_targets.get('protein', 'Not specified')}g
    - Carbs: {daily_targets.get('carbs', 'Not specified')}g
    - Fat: {daily_targets.get('fat', 'Not specified')}g

    7-DAY MEAL PLAN TOTALS:
    - Total Calories: {daily_totals.get('total_calories', 'Not specified')} kcal
    - Total Protein: {daily_totals.get('total_protein', 'Not specified')}g
    - Total Carbs: {daily_totals.get('total_carbs', 'Not specified')}g
    - Total Fat: {daily_totals.get('total_fat', 'Not specified')}g

    WELLNESS SCORE INFO:
    - Base Score: {wellness_score_info.get('base_score', 'Not specified')}
    - Adjusted Score: {wellness_score_info.get('adjusted_score', 'Not specified')}
    - Adherence Ratio: {wellness_score_info.get('adherence_ratio', 'Not specified')}

    DAILY BREAKDOWN:
    {daily_totals.get('daily_breakdown', 'Not available')}

    Provide a comprehensive analysis in this exact format:

    SUMMARY:
    [2-3 sentences summarizing key achievements and potential concerns]

    MACRONUTRIENT ANALYSIS:
    [Analysis of protein, carbs, and fat balance with specific observations]

    IMPROVEMENT SUGGESTIONS:
    [3-4 specific, actionable recommendations for food choices, meal timing, portion adjustments, or meal plan optimizations]

    Keep the tone analytical and professional. Focus on actionable insights rather than generic advice. Assume the user's targets are already AI-calculated and appropriate for their goals.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system", 
                    "content": "You are an expert nutrition coach providing analytical insights. Be specific, actionable, and professional. Focus on the data provided."
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating nutritional analysis: {str(e)}")
        return "Unable to generate analysis at this time. Please try again later."
