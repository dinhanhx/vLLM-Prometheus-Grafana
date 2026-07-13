from openai import OpenAI
import base64

client = OpenAI(api_key="dummy", base_url="http://localhost:8791/v1")

with open("assets/table.jpeg", "rb") as image_file:
    image_data = base64.standard_b64encode(image_file.read()).decode("utf-8")

# prompt = "Convert the table in this image to HTML."
prompt = """
Convert the table in this image to HTML.
"""

response = client.chat.completions.create(
    model="rednote-hilab/dots.mocr",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_data}"},
                },
                {"type": "text", "text": f"<|img|><|imgpad|><|endofimg|>{prompt}"},
            ],
        }
    ],
    temperature=0.1,
    top_p=0.9,
)

print(response.choices[0].message.content)
