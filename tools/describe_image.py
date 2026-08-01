import requests
import base64
import os

def describe_image(image_path: str, question: str = "Что на этой картинке? Если есть текст - распознай его.") -> str:
    """
    MANDATORY: call this tool immediately whenever the incoming message metadata
    mentions an image/photo attachment with a file path (e.g. "Attachments: photo... saved to /tmp/...").
    Do this automatically, without waiting for the user to explicitly ask you to look at the image.

    Analyzes an image using a vision-capable model, bypassing the standard image pipeline.

    Args:
        image_path (str): Absolute path to the image file (from message attachment metadata).
        question (str): What to ask about the image. Defaults to general description + OCR.

    Returns:
        str: Text description of the image contents, or a graceful error message if the
             analysis could not be completed (never raises).
    """
    try:
        api_key = os.environ.get("SAMBANOVA_API_KEY")
        if not api_key:
            return "Не удалось проанализировать изображение: не настроен ключ API. Сообщи об этом пользователю прямо."

        if not os.path.exists(image_path):
            return f"Не удалось найти файл изображения по пути {image_path}. Сообщи об этом пользователю."

        with open(image_path, "rb") as f:
            img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

        resp = requests.post(
            "https://api.sambanova.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gemma-4-31B-it",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    ],
                }],
            },
            timeout=30,
        )

        if resp.status_code == 429:
            return "Сервис распознавания картинок сейчас перегружен (лимит запросов). Скажи пользователю попробовать прислать картинку ещё раз через минуту."
        if resp.status_code != 200:
            return f"Не удалось проанализировать изображение (ошибка сервиса {resp.status_code}). Сообщи об этом пользователю простыми словами, не техническими деталями."

        return resp.json()["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:
        return "Анализ изображения занял слишком много времени и был прерван. Скажи пользователю попробовать ещё раз."
    except Exception as e:
        return f"Не удалось проанализировать изображение из-за технической ошибки. Сообщи об этом пользователю простыми словами, не упоминая технические детали."
