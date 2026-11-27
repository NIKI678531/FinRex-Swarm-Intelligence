"""Public Opinion Layer API."""

from flask import jsonify

from . import public_opinion_bp
from ..services.public_opinion_service import PublicOpinionService


@public_opinion_bp.route('/<report_id>', methods=['GET'])
def get_public_opinion(report_id: str):
    try:
        return jsonify({"success": True, "data": PublicOpinionService.get_public_opinion(report_id)})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@public_opinion_bp.route('/<report_id>/regenerate', methods=['POST'])
def regenerate_public_opinion(report_id: str):
    try:
        data = PublicOpinionService.get_public_opinion(report_id, regenerate=True)
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500

