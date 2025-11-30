import os
from openai import OpenAI


from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # after dotenv load

def classify_input(prompt_template: str, user_input: str) -> str:
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # way cheaper than 4.1 or o3
        messages=[
            {"role": "system", "content": "You classify free-text health input into a fixed label."},
            {"role": "user", "content": prompt_template.format(text=user_input)},
        ],
        max_tokens=10,
        temperature=0
    )

    return response.choices[0].message.content.strip()

def generate_insight(profile_json: dict) -> str:
    system_prompt = "You are a personal health assistant. Based on the user's structured health profile, provide 1 personalized recommendation that refers to the user’s goal and condition."
    user_prompt = f"User data:\n{profile_json}\n\nRespond with one paragraph recommendation."

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=200,
        temperature=1
    )

    return response.choices[0].message.content.strip()


def generate_structured_json(user_prompt: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You return structured JSON only."},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=300,
        temperature=0.7
    )

    import json
    try:
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print("AI returned invalid JSON:", response.choices[0].message.content)
        return {
            "weekly": "No plan generated.",
            "monthly": "No plan generated.",
            "priority": "medium"
        }
