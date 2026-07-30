from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, render_template, request, send_file


def create_app(service: Any) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("web/index.html")

    @app.get("/api/presets")
    def presets():
        return jsonify(service.preset_summaries())

    @app.post("/api/jobs")
    def create_job():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error("요청 내용을 확인해 주세요.")
        preset_id = payload.get("preset_id")
        if not isinstance(preset_id, str) or preset_id not in service.preset_ids:
            return _error("유효한 프리셋을 선택해 주세요.")
        music_prompt = payload.get("music_prompt")
        if music_prompt is not None and (
            not isinstance(music_prompt, str) or not music_prompt.strip()
        ):
            return _error("프롬프트는 비어 있지 않은 문장으로 입력해 주세요.")
        return jsonify(service.start(preset_id, music_prompt)), 202

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id: str):
        try:
            return jsonify(service.get(job_id))
        except (FileNotFoundError, ValueError):
            return _not_found()

    @app.get("/api/jobs/<job_id>/downloads/<asset>")
    def download_asset(job_id: str, asset: str):
        try:
            path = service.asset_path(job_id, asset)
        except (FileNotFoundError, ValueError):
            return _not_found()
        return send_file(path, as_attachment=True, download_name=path.name)

    return app


def _error(message: str):
    return jsonify({"error": message}), 400


def _not_found():
    return jsonify({"error": "요청한 작업 또는 파일을 찾을 수 없습니다."}), 404
