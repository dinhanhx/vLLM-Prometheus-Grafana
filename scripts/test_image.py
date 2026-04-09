from openai import OpenAI
import base64

client = OpenAI(api_key="dummy", base_url="http://localhost:8791/v1")

with open("assets/sample.jpg", "rb") as image_file:
    image_data = base64.standard_b64encode(image_file.read()).decode("utf-8")

response = client.chat.completions.create(
    model="Qwen/Qwen3.5-2B",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": ""},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                },
            ],
        }
    ],
)

print(response.choices[0].message.content)
