"""Content Studio API."""

from flask import jsonify, request

from . import content_studio_bp
from ..services.content_studio_service import ContentStudioService


@content_studio_bp.route('/<report_id>', methods=['GET'])
def get_content_studio(report_id: str):
    try:
        return jsonify({"success": True, "data": ContentStudioService.get_studio(report_id)})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@content_studio_bp.route('/<report_id>/generate', methods=['POST'])
def generate_content_studio(report_id: str):
    try:
        payload = request.get_json(silent=True) or {}
        return jsonify({"success": True, "data": ContentStudioService.generate(report_id, options=payload)})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@content_studio_bp.route('/check', methods=['POST'])
def check_content():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    platform = payload.get("platform")
    post = payload.get("post") if isinstance(payload.get("post"), dict) else None
    return jsonify({"success": True, "data": ContentStudioService.check(text, platform, post)})


@content_studio_bp.route('/posts/<post_id>', methods=['PATCH'])
def patch_content_post(post_id: str):
    try:
        payload = request.get_json(silent=True) or {}
        return jsonify({"success": True, "data": ContentStudioService.patch_post(post_id, payload)})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

