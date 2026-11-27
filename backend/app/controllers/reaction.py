"""Reaction analysis API.

Provides a unified workflow for:
- agent_only: no observed comments, run an agent-style reaction projection
- observed_augmented: real comment analysis plus agent augmentation
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..services.reaction import ReactionRunManager
from ..utils.logger import get_logger

logger = get_logger("finrex.api.reaction")

reaction_bp = Blueprint("reaction", __name__)


@reaction_bp.route("/analyze", methods=["POST"])
def analyze_reaction():
    payload = request.get_json(silent=True) or {}
    try:
        run = ReactionRunManager.analyze(payload)
        status_code = 500 if run.status.value == "failed" else 200
        return jsonify({"success": run.status.value != "failed", "data": run.to_dict(), "error": run.error}), status_code
    except Exception as exc:
        logger.exception("Reaction analyze endpoint failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@reaction_bp.route("/<run_id>/report-context", methods=["GET"])
def get_reaction_report_context(run_id: str):
    run = ReactionRunManager.get_run(run_id)
    if not run:
        return jsonify({"success": False, "error": "reaction run not found"}), 404
    return jsonify({
        "success": True,
        "data": {
            "run_id": run.run_id,
            "context": ReactionRunManager.build_report_context(run),
        },
    })

