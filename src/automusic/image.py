from __future__ import annotations

import base64
from pathlib import Path


def decode_image_response(response: object) -> bytes:
    data = getattr(response, "data")
    if not data:
        raise RuntimeError("OpenAI image response did not include image data")
    b64_json = getattr(data[0], "b64_json", None)
    if not b64_json:
        raise RuntimeError("OpenAI image response did not include b64_json")
    return base64.b64decode(b64_json)


def generate_image(prompt: str, output_path: Path, *, model: str = "gpt-image-1.5") -> Path:
    from openai import OpenAI

    client = OpenAI()
    response = client.images.generate(
        model=model,
        prompt=prompt,
        n=1,
        size="1536x1024",
        quality="medium",
        output_format="png",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(decode_image_response(response))
    return output_path
