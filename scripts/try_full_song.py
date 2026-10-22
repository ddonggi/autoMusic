"""Generate one full song without changing the scheduled pipeline."""
from pathlib import Path
import base64
import json
import sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from automusic.config import load_config, load_dotenv
from automusic.prompts import build_music_prompt_with_metadata, build_track_title


def main():
    from google import genai

    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    config = load_config(root / "configs/categories/study.yaml")
    result = build_music_prompt_with_metadata(config)
    result["prompt"] = "Create an original three-minute instrumental ambient study composition. Soft felt piano, gentle sustained strings, spacious warm acoustics, calm quiet dynamics. Begin with a sparse piano introduction, gradually add gentle strings, explore a complementary middle theme, return to the opening motif, and finish with a natural soft resolution. Instrumental throughout."
    title = build_track_title(config, result)
    output = root / "workspace/manual-full-songs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    metadata = dict(result, title=title, model="lyria-3.5", status="requested")
    metadata_path = output / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))
    client = genai.Client(http_options={"timeout": 600000})
    response = client.interactions.create(model="lyria-3.5", input=result["prompt"])
    # Save the complete response before extracting audio for SDK compatibility.
    (output / "response.json").write_text(response.model_dump_json(exclude_none=True))
    data = response.model_dump(exclude_none=True)
    chunks = []

    def collect(value):
        if isinstance(value, dict):
            if value.get("type") == "audio" and value.get("data"):
                chunks.append(base64.b64decode(value["data"]))
            else:
                for child in value.values():
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(data)
    if not chunks:
        raise RuntimeError(f"No inline audio returned; inspect {output / 'response.json'}")
    (output / "song.mp3").write_bytes(b"".join(chunks))
    metadata["status"] = "completed"
    metadata_path.write_text(json.dumps(metadata, indent=2))
    print(output, flush=True)


if __name__ == "__main__":
    main()
