import base64
from openai import OpenAI

client = OpenAI(api_key="empty", base_url="http://localhost:8791/v1")

# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


# Path to your image
image_path = "image.jpeg"

# Getting the Base64 string
base64_image = encode_image(image_path)

completion = client.chat.completions.create(
    model="unsloth/gemma-3-4b-it-bnb-4bit",
    messages=[
        {
            "role": "user",
            "content": [
                { "type": "text", "text": "Describe the image in Vietnamese" },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                    },
                },
            ],
        }
    ],
)

print(completion.choices[0].message.content)