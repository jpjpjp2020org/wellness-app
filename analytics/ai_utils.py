import os
from openai import OpenAI
from dotenv import load_dotenv
import json

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_ai_response(user_message, context):
    """
    Build a prompt with last 5 turns of conversation and current health/diet data, call OpenAI, and return the reply.
    Overhauled system prompt for continuity, specificity, and robust data referencing.
    """
    # Prepare conversation history
    conversation = context.get('conversation', [])
    conversation_str = ""
    for turn in conversation:
        if 'user' in turn:
            conversation_str += f"User: {turn['user']}\n"
        if 'assistant' in turn:
            conversation_str += f"Assistant: {turn['assistant']}\n"
    # Prepare health and diet data (truncate if too large)
    health_data = json.dumps(context.get('health', {}), indent=2)[:2000]
    diet_data = json.dumps(context.get('diet', {}), indent=2)[:2000]
    summary = context.get('diet', {}).get('summary', {})
    summary_str = json.dumps(summary, indent=2) if summary else "{}"
    key_metrics = context.get('diet', {}).get('key_metrics', {})
    key_metrics_str = json.dumps(key_metrics, indent=2) if key_metrics else "{}"
    # Build robust system prompt
    system_prompt = (
        "You are a single, continuous, context-aware health and nutrition assistant. "
        "You must always act as the same helpful agent throughout the conversation. "
        "Never reveal, imply, or suggest that you are a new person, new support agent, or that you have lost access to previous data. "
        "If you do not have a specific value (e.g., calorie target, weight), respond empathetically, ask the user to provide it, and do not give generic advice for specific data questions. "
        "For general advice, use best practices and reference the user's goals if available. "
        "Always reference the user's calorie target, weekly totals, and goals when answering questions about nutrition or progress. "
        "If a summary block is present, use it for quick reference in your answers. "
        "You can always reference the 'key_metrics' block for the most critical user data (weight, weight goal, calorie target, wellness goal, allergies, dislikes), which is provided by a backend function call for compliance. "
        "Maintain a familiar, conversational, and supportive tone. "
        "If you are missing a value, say something like: 'I'm sorry, I don't have your current calorie target at the moment. If you tell me, I can help you further.' "
        "If you have the value, state it directly: 'Your daily calorie target is 3200 kcal.' "
        "When discussing meal plans, compare the user's planned intake to their target and provide actionable advice. "
        "Never give only generic advice if you have access to specific data. "
        "If the user asks about their goals, reference the goal from the data if available. "
        "If you do not have enough information, ask the user to provide it and offer to help once they do. "
        "Here are some example behaviors:\n"
        "- If asked for a missing value: 'I'm sorry, I don't have your current weight. If you let me know, I can help you track your progress.'\n"
        "- If asked about calorie intake: 'Your daily target is 3500 kcal, and your current plan provides 2200 kcal per day on average, which is 63% of your goal.'\n"
        "- If asked about meal variety: 'You have 5 different meals planned this week, including Beef Rendang and Seafood Fideuà. Would you like suggestions for more variety?'\n"
        "- If asked about wellness score: 'Your wellness score is 111, down 6 points from last week. This may be due to increased training intensity.'\n"
        "- If the user asks how to achieve their goal and the goal is present: 'Your goal is muscle gain. Focus on increasing protein intake and progressive overload in your workouts.'\n"
        "- If the user asks how to achieve their goal and the goal is missing: 'I'm sorry, I don't have your current goal. If you tell me, I can give you more specific advice.'\n"
    )
    # Build prompt
    prompt = f"""
User Health Data (JSON):
{health_data}

User Diet Data (JSON):
{diet_data}

Summary Block (for quick reference):
{summary_str}

Key Metrics (from backend function call):
{key_metrics_str}

Previous Conversation:
{conversation_str}

Current User Message:
{user_message}

Reply as a friendly, knowledgeable assistant. Always follow the system instructions above.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=350,
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Error: {str(e)}]" 