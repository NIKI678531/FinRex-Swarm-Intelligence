"""
Report API路由
提供模拟报告生成、获取、对话等接口
"""

import os
import re
import traceback
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from flask import request, jsonify, send_file

from . import report_bp
from ..config import Config
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.report_v2_adapter import ReportV2Adapter
from ..services.simulation_manager import SimulationManager
from ..repositories.project_repository import ProjectManager
from ..repositories.task_repository import TaskManager, TaskStatus
from ..utils.logger import get_logger
from ..utils.locale import t, get_locale, set_locale

logger = get_logger('finrex.api.report')


_OBSERVED_COMMENT_RE = re.compile(r"^\s*\[\d+\]\s+(?P<text>.+?)\s*$")
_SECTION_HEADER_RE = re.compile(r"^===\s*(?P<title>.+?)\s*===$")
_STOCK_PRECISE_FORECAST_CACHE: Dict[str, Dict[str, Any]] = {}


def _is_usable_report(report) -> bool:
    return bool(
        report
        and report.status == ReportStatus.COMPLETED
        and (report.markdown_content or report.outline)
    )


def _replacement_report_for(report, preferred_type=None):
    if not report or not getattr(report, 'simulation_id', None):
        return None

    report_types = []
    if preferred_type in {'narrative', 'financial'}:
        report_types.append(preferred_type)
    if getattr(report, 'report_type', None) in {'narrative', 'financial'}:
        report_types.append(report.report_type)
    report_types.append(None)

    seen = set()
    for report_type in report_types:
        if report_type in seen:
            continue
        seen.add(report_type)
        candidate = ReportManager.get_report_by_simulation(report.simulation_id, report_type)
        if candidate and candidate.report_id != report.report_id and _is_usable_report(candidate):
            return candidate
    return None


def _attach_recovery_fields(payload: Dict[str, Any], report, preferred_type=None) -> Dict[str, Any]:
    replacement = _replacement_report_for(report, preferred_type=preferred_type)
    if replacement:
        payload.update({
            "recoverable": True,
            "replacement_report_id": replacement.report_id,
            "replacement_report_type": replacement.report_type,
            "replacement_status": replacement.status.value,
        })
    else:
        payload.setdefault("recoverable", False)
    return payload


def _attach_report_metadata_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata = ((payload.get('financial_context') or {}).get('report_metadata') or {})
    if metadata:
        payload.setdefault('event_date', metadata.get('event_date') or '')
        payload.setdefault('data_cutoff_at', metadata.get('data_cutoff_at') or '')
        payload.setdefault('data_sources_summary', metadata.get('data_sources_summary') or {})
    else:
        payload.setdefault('event_date', payload.get('created_at') or '')
        payload.setdefault('data_cutoff_at', payload.get('completed_at') or payload.get('created_at') or '')
        payload.setdefault('data_sources_summary', {})
    return payload


def _attach_stock_precise_forecast_if_missing(payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return payload
    financial_context = payload.get('financial_context')
    if not isinstance(financial_context, dict):
        return payload
    forecast = financial_context.get('forecast')
    if not isinstance(forecast, dict) or forecast.get('precise_forecast'):
        return payload

    target_asset = financial_context.get('target_asset') or {}
    asset_type = str(target_asset.get('type') or '').lower()
    stock_forecast = forecast.get('stock_forecast') if isinstance(forecast.get('stock_forecast'), dict) else {}
    if asset_type != 'stock' and str((stock_forecast or {}).get('asset_type') or '').lower() != 'stock':
        return payload

    market = (stock_forecast or {}).get('market') or {}
    observed = financial_context.get('observed') or {}
    price_facts = observed.get('price_facts') or {}
    rows = market.get('ohlcv_tail') or observed.get('ohlcv_recent') or []
    last_close = (
        price_facts.get('last_close')
        or market.get('last_close')
        or (market.get('indicators') or {}).get('last_close')
    )
    horizon_days = (
        (stock_forecast or {}).get('horizon_days')
        or (forecast.get('target_price_range') or {}).get('horizon_days')
        or 1
    )
    symbol = str(target_asset.get('symbol') or (stock_forecast or {}).get('symbol') or '').strip().upper()
    cache_key = "|".join([
        str(payload.get('report_id') or ''),
        symbol,
        str(horizon_days),
        str(payload.get('data_cutoff_at') or payload.get('completed_at') or ''),
    ])
    cached = _STOCK_PRECISE_FORECAST_CACHE.get(cache_key)
    if cached:
        forecast['precise_forecast'] = dict(cached)
        if isinstance(stock_forecast, dict) and not stock_forecast.get('precise_forecast'):
            stock_forecast['precise_forecast'] = dict(cached)
        return payload

    if symbol and len(rows) < 64:
        try:
            from ..services.financial.market_provider import MarketProvider

            snapshot = MarketProvider().fetch_snapshot(symbol, asset_type='stock', lookback_days=180)
            fetched_rows = snapshot.get('ohlcv') or []
            if snapshot.get('ok') and len(fetched_rows) > len(rows):
                rows = fetched_rows
                last_close = last_close or (snapshot.get('indicators') or {}).get('last_close')
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to refresh OHLCV for stock precise forecast %s: %s", symbol, exc)

    try:
        from ..services.financial.stock_forecast_service import build_precise_forecast_from_ohlcv

        precise_forecast = build_precise_forecast_from_ohlcv(
            rows=rows,
            last_close=last_close,
            target_range=forecast.get('target_price_range'),
            horizon_days=horizon_days,
            symbol=symbol,
        )
        if precise_forecast:
            _STOCK_PRECISE_FORECAST_CACHE[cache_key] = dict(precise_forecast)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to attach stock precise forecast for %s: %s", payload.get('report_id'), exc)
        precise_forecast = None

    if precise_forecast:
        forecast['precise_forecast'] = precise_forecast
        if isinstance(stock_forecast, dict) and not stock_forecast.get('precise_forecast'):
            stock_forecast['precise_forecast'] = precise_forecast
    return payload


def _first_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(
            item.get('text')
            or item.get('content')
            or item.get('comment')
            or item.get('body')
            or item.get('summary')
            or ''
        ).strip()
    return ''


def _normalize_seed_article(item: Any, project, fallback_title: str = 'Selected market seed') -> Dict[str, Any] | None:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return {
            'title': fallback_title,
            'text': text,
            'source': 'selected_seed',
            'site': 'Selected market seed',
            'published_at': getattr(project, 'created_at', '') or '',
        }
    if not isinstance(item, dict):
        return None
    text = _first_text(item)
    title = str(item.get('title') or fallback_title).strip()
    if not text and not title:
        return None
    published_at = item.get('published_at') or item.get('publishedDate') or item.get('date') or item.get('created_at') or getattr(project, 'created_at', '') or ''
    return {
        'title': title,
        'text': text or title,
        'url': item.get('url') or item.get('link') or '',
        'site': item.get('site') or item.get('source_type') or item.get('source') or 'Selected market seed',
        'published_at': published_at,
        'tickers': item.get('tickers') or '',
        'source': item.get('source_type') or item.get('source') or 'selected_seed',
        'content_type': item.get('content_type') or '',
        'source_article_id': item.get('source_article_id') or item.get('id') or '',
    }


def _normalize_seed_comment(item: Any, project, source: str = 'observed_seed') -> Dict[str, Any] | None:
    text = _first_text(item)
    if not text:
        return None
    if isinstance(item, dict):
        published_at = item.get('published_at') or item.get('created_at') or item.get('date') or getattr(project, 'created_at', '') or ''
        return {
            'title': item.get('title') or 'Observed market comment',
            'text': text,
            'source': item.get('source') or source,
            'site': item.get('site') or 'Binance/Paste observed layer',
            'published_at': published_at,
            'post_id': item.get('post_id') or '',
        }
    return {
        'text': text,
        'source': source,
        'site': 'Binance/Paste observed layer',
        'published_at': getattr(project, 'created_at', '') or '',
    }


def _dedupe_financial_items(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        key = str(item.get('text') or item.get('title') or '').strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _parse_report_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 10_000_000_000:
                ts /= 1000
            return datetime.fromtimestamp(ts)
        return datetime.fromisoformat(str(value).replace('Z', '+00:00').replace('T', ' ')).replace(tzinfo=None)
    except Exception:
        return None


def _iso_seconds(value: datetime | None) -> str:
    return value.isoformat(timespec='seconds') if value else ''


def _build_financial_report_metadata(
    project,
    selected_articles: List[Dict[str, Any]],
    user_comments: List[Dict[str, Any]],
    financial_context: Dict[str, Any],
) -> Dict[str, Any]:
    article_dates = [_parse_report_dt(a.get('published_at') or a.get('date')) for a in selected_articles]
    comment_dates = [_parse_report_dt(c.get('published_at') or c.get('created_at') or c.get('date')) for c in user_comments]
    project_dt = _parse_report_dt(getattr(project, 'created_at', '') or '')
    event_dt = next((d for d in article_dates if d), None) or project_dt

    observed = financial_context.get('observed') or {}
    forecast = financial_context.get('forecast') or {}
    crypto = forecast.get('crypto_forecast') or {}
    market = crypto.get('market') or {}
    price_facts = observed.get('price_facts') or {}
    market_dates = [
        _parse_report_dt(market.get('fetched_at')),
        _parse_report_dt(price_facts.get('as_of')),
    ]
    cutoff_candidates = [d for d in article_dates + comment_dates + market_dates + [project_dt, datetime.now()] if d]
    data_cutoff = max(cutoff_candidates) if cutoff_candidates else datetime.now()

    def _count_source(name: str) -> int:
        return sum(1 for a in selected_articles if str(a.get('source') or a.get('site') or '').lower().startswith(name))

    data_quality = financial_context.get('data_quality') or crypto.get('data_quality') or {}
    return {
        'event_date': _iso_seconds(event_dt),
        'data_cutoff_at': _iso_seconds(data_cutoff),
        'data_sources_summary': {
            'fmp_articles': _count_source('fmp'),
            'binance_articles': _count_source('binance'),
            'manual_articles': _count_source('manual'),
            'selected_articles': len(selected_articles),
            'observed_comments': len(user_comments),
            'remote_news': bool(data_quality.get('remote_news')),
            'market_rows': data_quality.get('market_rows') or 0,
        },
    }


def _extract_financial_seed_context(project) -> Dict[str, List[Dict[str, Any]]]:
    """Extract selected articles and observed comments saved by Step1.

    The sentiment page writes Binance/paste comments into an
    "Observed comment layer" section and selected FMP/Binance/manual article
    text into a "Simulated seed material" section before Process creates the
    project. Final report generation keeps these two channels separate.
    """
    comments: List[Dict[str, Any]] = []
    articles: List[Dict[str, Any]] = []

    structured = getattr(project, 'financial_seed_context', None) or {}
    if isinstance(structured, dict):
        for item in (structured.get('selected_articles') or structured.get('articles') or []):
            normalized = _normalize_seed_article(item, project)
            if normalized:
                articles.append(normalized)
        for item in structured.get('comments') or []:
            normalized = _normalize_seed_comment(item, project, source='project_metadata')
            if normalized:
                comments.append(normalized)

    try:
        text = ProjectManager.get_extracted_text(project.project_id) or ''
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"读取项目提取文本失败，无法抽取金融评论: {exc}")
        text = ''

    layer = ''
    current_title = ''
    current_meta: Dict[str, str] = {}
    seed_buffer: List[str] = []

    def flush_seed_buffer() -> None:
        nonlocal seed_buffer, current_meta, current_title
        text_block = ' '.join(part.strip() for part in seed_buffer if part.strip())
        seed_buffer = []
        if text_block:
            source = current_meta.get('source_type') or current_meta.get('source') or 'selected_seed'
            content_type = current_meta.get('content_type') or ''
            articles.append({
                'title': current_title or 'Selected market seed',
                'text': text_block[:1200],
                'source': source,
                'site': source if not content_type else f"{source}/{content_type}",
                'content_type': content_type,
                'published_at': getattr(project, 'created_at', '') or '',
            })

    for line in text.splitlines():
        stripped = line.strip()
        header_match = _SECTION_HEADER_RE.match(stripped)
        if header_match:
            header = header_match.group('title').strip()
            if header == 'Source metadata':
                layer = 'meta'
                continue
            if header == 'Simulated seed material':
                layer = 'seed'
                continue
            if header == 'Observed comment layer':
                layer = 'observed'
                continue
            if header and not header.startswith('/'):
                flush_seed_buffer()
                current_title = header
                current_meta = {}
                layer = ''
                continue
        if stripped == '=== Simulated seed material ===':
            flush_seed_buffer()
            layer = 'seed'
            continue
        if stripped == '=== Observed comment layer ===':
            flush_seed_buffer()
            layer = 'observed'
            continue
        if stripped.startswith('===') and layer:
            flush_seed_buffer()
            layer = ''
            continue
        if layer == 'meta':
            if ':' in stripped:
                key, value = stripped.split(':', 1)
                current_meta[key.strip()] = value.strip()
            continue
        if layer == 'seed':
            if stripped and not stripped.startswith('---'):
                seed_buffer.append(stripped)
            continue
        if layer != 'observed' or not stripped:
            continue
        if stripped.lower().startswith('no real comment text was available'):
            continue
        match = _OBSERVED_COMMENT_RE.match(stripped)
        if match:
            comment_text = match.group('text').strip()
        else:
            comment_text = stripped
        if comment_text:
            comments.append({
                'text': comment_text,
                'source': current_meta.get('source_type') or 'observed_seed',
                'site': current_meta.get('source_type') or 'Binance/Paste observed layer',
                'published_at': getattr(project, 'created_at', '') or '',
            })
    flush_seed_buffer()

    return {
        'articles': _dedupe_financial_items(articles, 200),
        'comments': _dedupe_financial_items(comments, 500),
    }


def _extract_financial_user_comments(project) -> List[Dict[str, Any]]:
    """Backward-compatible wrapper for callers that only need comments."""
    return _extract_financial_seed_context(project).get('comments', [])


# ============== 报告生成接口 ==============

@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """
    生成模拟分析报告（异步任务）
    
    这是一个耗时操作，接口会立即返回task_id，
    使用 GET /api/report/generate/status 查询进度
    
    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",    // 必填，模拟ID
            "force_regenerate": false        // 可选，强制重新生成
        }
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",
                "status": "generating",
                "message": "报告生成任务已启动"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t('api.requireSimulationId')
            }), 400

        force_regenerate = data.get('force_regenerate', False)
        # report_type: 'narrative' | 'financial' | 'both'，默认 'both'
        report_type = (data.get('report_type') or 'both').lower()
        if report_type not in {'narrative', 'financial', 'both'}:
            report_type = 'both'
        
        # 获取模拟信息
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": t('api.simulationNotFound', id=simulation_id)
            }), 404

        # 检查是否已有报告（依 report_type 决定需要哪些）
        if not force_regenerate:
            need_narrative = report_type in {'narrative', 'both'}
            need_financial = report_type in {'financial', 'both'}
            existing_narr = ReportManager.get_report_by_simulation(simulation_id, 'narrative') if need_narrative else None
            existing_fin = ReportManager.get_report_by_simulation(simulation_id, 'financial') if need_financial else None

            narr_ok = (not need_narrative) or (existing_narr and existing_narr.status == ReportStatus.COMPLETED)
            fin_ok = (not need_financial) or (existing_fin and existing_fin.status == ReportStatus.COMPLETED)

            if narr_ok and fin_ok:
                primary = existing_narr or existing_fin
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": primary.report_id if primary else None,
                        "narrative_report_id": existing_narr.report_id if existing_narr else None,
                        "financial_report_id": existing_fin.report_id if existing_fin else None,
                        "report_type": report_type,
                        "status": "completed",
                        "message": t('api.reportAlreadyExists'),
                        "already_generated": True
                    }
                })
        
        # 获取项目信息
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=state.project_id)
            }), 404
        
        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": t('api.missingGraphIdEnsure')
            }), 400
        
        simulation_requirement = project.simulation_requirement
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": t('api.missingSimRequirement')
            }), 400
        
        # 提前生成 report_id，以便立即返回给前端
        import uuid
        narrative_report_id = f"report_{uuid.uuid4().hex[:12]}"
        financial_report_id = f"freport_{uuid.uuid4().hex[:12]}"
        # 兼容旧字段：返回叙事报告 id 作为主 report_id
        primary_report_id = narrative_report_id if report_type != 'financial' else financial_report_id
        
        # 创建异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="report_generate",
            metadata={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "report_id": primary_report_id,
                "narrative_report_id": narrative_report_id if report_type in {'narrative', 'both'} else None,
                "financial_report_id": financial_report_id if report_type in {'financial', 'both'} else None,
                "report_type": report_type,
            }
        )
        
        # Capture locale before spawning background thread
        current_locale = get_locale()

        # 收集金融分析所需的额外上下文
        target_asset = getattr(project, 'target_asset', None) or {}
        # Step1 金融输入：FMP/Binance/manual seed articles 与 Observed comment layer 分开抽取。
        financial_seed_context = _extract_financial_seed_context(project)
        user_comments = financial_seed_context.get('comments') or []
        selected_articles = financial_seed_context.get('articles') or []
        if user_comments:
            logger.info(f"金融预测抽取到真实评论: {len(user_comments)} 条")
        if selected_articles:
            logger.info(f"金融预测抽取到已选种子文章: {len(selected_articles)} 条")

        # 定义后台任务
        def run_generate():
            set_locale(current_locale)
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message=t('api.initReportAgent')
                )

                results: Dict[str, Any] = {}

                # 进度回调
                def make_progress_cb(prefix: str):
                    def _cb(stage, progress, message):
                        task_manager.update_task(
                            task_id,
                            progress=progress,
                            message=f"[{prefix}/{stage}] {message}"
                        )
                    return _cb

                # 1) 叙事报告（保留原有行为）
                if report_type in {'narrative', 'both'}:
                    agent = ReportAgent(
                        graph_id=graph_id,
                        simulation_id=simulation_id,
                        simulation_requirement=simulation_requirement,
                        report_type='narrative',
                    )
                    n_report = agent.generate_report(
                        progress_callback=make_progress_cb('narrative'),
                        report_id=narrative_report_id,
                    )
                    ReportManager.save_report(n_report)
                    results['narrative'] = {
                        'report_id': n_report.report_id,
                        'status': n_report.status.value if hasattr(n_report.status, 'value') else str(n_report.status),
                    }

                # 2) 金融预测报告
                if report_type in {'financial', 'both'}:
                    # 调用分析器收集 OIF + Forecast 上下文
                    from ..services.financial import FinancialForecastAnalyzer
                    from ..services.time_pulse_model import TimePulseModel

                    try:
                        analyzer = FinancialForecastAnalyzer()
                        # OASIS dashboard（如有）
                        oasis_dashboard = None
                        try:
                            oasis_dashboard = TimePulseModel.build_dashboard(
                                report={
                                    'simulation_id': simulation_id,
                                    'created_at': '',
                                },
                                topics=[],
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(f"TimePulseModel build_dashboard 失败: {exc}")

                        financial_context = analyzer.analyze(
                            target_asset=target_asset,
                            simulation_requirement=simulation_requirement,
                            user_comments=user_comments,
                            selected_articles=selected_articles,
                            oasis_dashboard=oasis_dashboard,
                        )
                        financial_context['report_metadata'] = _build_financial_report_metadata(
                            project=project,
                            selected_articles=selected_articles,
                            user_comments=user_comments,
                            financial_context=financial_context,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(f"FinancialForecastAnalyzer.analyze 失败: {exc}")
                        financial_context = {
                            'target_asset': target_asset,
                            'mode': 'event',
                            'observed': {},
                            'inferred': {},
                            'simulated': {},
                            'forecast': {
                                'direction': 'neutral',
                                'probability': 0.5,
                                'horizon': '72h',
                                'confidence': 'low',
                                'risk_caveats': [f'分析器失败: {exc}'],
                            },
                            'data_quality': {},
                            'report_metadata': _build_financial_report_metadata(
                                project=project,
                                selected_articles=selected_articles,
                                user_comments=user_comments,
                                financial_context={},
                            ),
                        }

                    f_agent = ReportAgent(
                        graph_id=graph_id,
                        simulation_id=simulation_id,
                        simulation_requirement=simulation_requirement,
                        report_type='financial',
                        financial_context=financial_context,
                    )
                    f_report = f_agent.generate_report(
                        progress_callback=make_progress_cb('financial'),
                        report_id=financial_report_id,
                    )
                    ReportManager.save_report(f_report)
                    results['financial'] = {
                        'report_id': f_report.report_id,
                        'status': f_report.status.value if hasattr(f_report.status, 'value') else str(f_report.status),
                    }

                # 完成
                primary = results.get('narrative') or results.get('financial')
                if primary and primary.get('status') == 'completed':
                    task_manager.complete_task(
                        task_id,
                        result={
                            "report_id": primary['report_id'],
                            "simulation_id": simulation_id,
                            "status": "completed",
                            "narrative_report_id": (results.get('narrative') or {}).get('report_id'),
                            "financial_report_id": (results.get('financial') or {}).get('report_id'),
                            "report_type": report_type,
                        }
                    )
                else:
                    task_manager.fail_task(task_id, t('api.reportGenerateFailed'))

            except Exception as e:
                logger.error(f"报告生成失败: {str(e)}")
                task_manager.fail_task(task_id, str(e))
        
        # 启动后台线程
        thread = threading.Thread(target=run_generate, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "report_id": primary_report_id,
                "narrative_report_id": narrative_report_id if report_type in {'narrative', 'both'} else None,
                "financial_report_id": financial_report_id if report_type in {'financial', 'both'} else None,
                "report_type": report_type,
                "task_id": task_id,
                "status": "generating",
                "message": t('api.reportGenerateStarted'),
                "already_generated": False
            }
        })
        
    except Exception as e:
        logger.error(f"启动报告生成任务失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _status_request_payload():
    payload = request.get_json(silent=True) or {}
    for key in ('task_id', 'simulation_id', 'report_id'):
        value = request.args.get(key)
        if value:
            payload[key] = value
    return payload


def _report_status_payload(report, task_id=None):
    progress_data = ReportManager.get_progress(report.report_id) or {}
    status = report.status.value
    progress = progress_data.get('progress')
    if progress is None:
        progress = 100 if report.status == ReportStatus.COMPLETED else (-1 if report.status == ReportStatus.FAILED else 0)

    payload = {
        "status": status,
        "progress": progress,
        "message": progress_data.get('message') or ("Report completed" if status == "completed" else "Report status loaded"),
        "report_id": report.report_id,
        "simulation_id": report.simulation_id,
        "task_id": task_id,
        "already_completed": report.status == ReportStatus.COMPLETED,
        "error": report.error,
    }
    return _attach_recovery_fields(payload, report)


def _task_status_payload(task_data, fallback_report_id=None, fallback_simulation_id=None):
    metadata = task_data.get('metadata') or {}
    result = task_data.get('result') or {}
    status = task_data.get('status') or 'pending'
    report_id = (
        result.get('report_id')
        or metadata.get('report_id')
        or metadata.get('narrative_report_id')
        or metadata.get('financial_report_id')
        or fallback_report_id
    )
    simulation_id = result.get('simulation_id') or metadata.get('simulation_id') or fallback_simulation_id

    return {
        "status": status,
        "progress": task_data.get('progress', 0),
        "message": task_data.get('message', ''),
        "report_id": report_id,
        "narrative_report_id": result.get('narrative_report_id') or metadata.get('narrative_report_id'),
        "financial_report_id": result.get('financial_report_id') or metadata.get('financial_report_id'),
        "simulation_id": simulation_id,
        "task_id": task_data.get('task_id'),
        "already_completed": status == TaskStatus.COMPLETED.value,
        "error": task_data.get('error'),
    }


def _find_report_generation_task(task_manager, report_id=None, simulation_id=None):
    for task_data in task_manager.list_tasks(task_type="report_generate"):
        metadata = task_data.get('metadata') or {}
        result = task_data.get('result') or {}
        task_report_ids = {
            metadata.get('report_id'),
            metadata.get('narrative_report_id'),
            metadata.get('financial_report_id'),
            result.get('report_id'),
            result.get('narrative_report_id'),
            result.get('financial_report_id'),
        }
        if report_id and report_id in task_report_ids:
            return task_data
        if simulation_id and (metadata.get('simulation_id') == simulation_id or result.get('simulation_id') == simulation_id):
            return task_data
    return None


@report_bp.route('/generate/status', methods=['GET', 'POST'])
def get_generate_status():
    """
    查询报告生成任务进度
    
    请求（JSON）：
        {
            "task_id": "task_xxxx",         // 可选，generate返回的task_id
            "simulation_id": "sim_xxxx"     // 可选，模拟ID
        }
    
    返回：
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|failed",
                "progress": 45,
                "message": "..."
            }
        }
    """
    try:
        data = _status_request_payload()
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        report_id = data.get('report_id')

        if report_id:
            report = ReportManager.get_report(report_id)
            if report:
                return jsonify({"success": True, "data": _report_status_payload(report, task_id=task_id)})

        task_manager = TaskManager()
        task_data = None
        if task_id:
            task = task_manager.get_task(task_id)
            if task:
                task_data = task.to_dict()
        if not task_data:
            task_data = _find_report_generation_task(
                task_manager,
                report_id=report_id,
                simulation_id=simulation_id,
            )

        if task_data:
            status_payload = _task_status_payload(
                task_data,
                fallback_report_id=report_id,
                fallback_simulation_id=simulation_id,
            )
            persisted_report_id = status_payload.get('report_id')
            if persisted_report_id:
                report = ReportManager.get_report(persisted_report_id)
                if report:
                    return jsonify({"success": True, "data": _report_status_payload(report, task_id=status_payload.get('task_id'))})
            return jsonify({"success": True, "data": status_payload})
        
        # 如果提供了simulation_id，先检查是否已有完成的报告
        if simulation_id:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report:
                return jsonify({"success": True, "data": _report_status_payload(existing_report, task_id=task_id)})
        
        if not any([task_id, simulation_id, report_id]):
            return jsonify({
                "success": False,
                "error": t('api.requireTaskOrSimId')
            }), 400
        
        if report_id or simulation_id:
            return jsonify({
                "success": True,
                "data": {
                    "status": "generating",
                    "progress": 0,
                    "message": "Report generation has started; report files are not persisted yet.",
                    "report_id": report_id,
                    "simulation_id": simulation_id,
                    "task_id": task_id,
                    "already_completed": False,
                    "error": None,
                }
            })
        
        return jsonify({
            "success": False,
            "error": t('api.taskNotFound', id=task_id)
        }), 404
        
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== 报告获取接口 ==============

@report_bp.route('/<report_id>', methods=['GET'])
def get_report(report_id: str):
    """
    获取报告详情
    
    返回：
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "simulation_id": "sim_xxxx",
                "status": "completed",
                "outline": {...},
                "markdown_content": "...",
                "created_at": "...",
                "completed_at": "..."
            }
        }
    """
    try:
        report = ReportManager.get_report(report_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": t('api.reportNotFound', id=report_id)
            }), 404
        
        data = _attach_report_metadata_fields(
            _attach_stock_precise_forecast_if_missing(
                _attach_recovery_fields(report.to_dict(), report)
            )
        )
        return jsonify({
            "success": True,
            "data": data
        })
        
    except Exception as e:
        logger.error(f"获取报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/v2', methods=['GET'])
def get_report_v2(report_id: str):
    """Return sectioned report dashboard data backed by a real saved report."""
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({
                "success": False,
                "error": t('api.reportNotFound', id=report_id)
            }), 404

        replacement = _replacement_report_for(report, preferred_type='narrative')
        if replacement and not _is_usable_report(report):
            bundle = ReportV2Adapter.build(replacement)
            bundle.setdefault("meta", {})
            bundle["meta"].update({
                "requested_report_id": report.report_id,
                "recovered_from": report.report_id,
                "replacement_report_id": replacement.report_id,
            })
            bundle["requested_report_id"] = report.report_id
            bundle["replacement_report_id"] = replacement.report_id
            return jsonify({
                "success": True,
                "data": bundle,
                "recoverable": True,
                "replacement_report_id": replacement.report_id,
            })

        return jsonify({
            "success": True,
            "data": ReportV2Adapter.build(report)
        })
    except Exception as e:
        logger.error(f"build report v2 data failed: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
def get_report_by_simulation(simulation_id: str):
    """
    根据模拟ID获取报告

    Query 参数:
        report_type: 可选 'narrative' | 'financial' | 'both'
            - 默认行为（不传）：返回叙事报告（兼容旧客户端）
            - 'both': 返回 { narrative, financial } 双报告
    """
    try:
        report_type_q = (request.args.get('report_type') or '').lower()

        if report_type_q == 'both':
            narrative = ReportManager.get_report_by_simulation(simulation_id, 'narrative')
            financial = ReportManager.get_report_by_simulation(simulation_id, 'financial')
            if not narrative and not financial:
                return jsonify({
                    "success": False,
                    "error": t('api.noReportForSim', id=simulation_id),
                    "has_report": False
                }), 404
            return jsonify({
                "success": True,
                "data": {
                    "narrative": _attach_report_metadata_fields(
                        _attach_stock_precise_forecast_if_missing(narrative.to_dict())
                    ) if narrative else None,
                    "financial": _attach_report_metadata_fields(
                        _attach_stock_precise_forecast_if_missing(financial.to_dict())
                    ) if financial else None,
                },
                "has_report": True,
            })

        filter_type = report_type_q if report_type_q in {'narrative', 'financial'} else None
        report = ReportManager.get_report_by_simulation(simulation_id, filter_type)

        if not report:
            return jsonify({
                "success": False,
                "error": t('api.noReportForSim', id=simulation_id),
                "has_report": False
            }), 404

        return jsonify({
            "success": True,
            "data": _attach_report_metadata_fields(
                _attach_stock_precise_forecast_if_missing(report.to_dict())
            ),
            "has_report": True
        })
        
    except Exception as e:
        logger.error(f"获取报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/download', methods=['GET'])
def download_report(report_id: str):
    """
    下载报告（Markdown格式）
    
    返回Markdown文件
    """
    try:
        report = ReportManager.get_report(report_id)
        
        if not report:
            return jsonify({
                "success": False,
                "error": t('api.reportNotFound', id=report_id)
            }), 404
        
        md_path = ReportManager._get_report_markdown_path(report_id)
        
        if not os.path.exists(md_path):
            # 如果MD文件不存在，生成一个临时文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(report.markdown_content)
                temp_path = f.name
            
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f"{report_id}.md"
            )
        
        return send_file(
            md_path,
            as_attachment=True,
            download_name=f"{report_id}.md"
        )
        
    except Exception as e:
        logger.error(f"下载报告失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Report Agent对话接口 ==============

@report_bp.route('/chat', methods=['POST'])
def chat_with_report_agent():
    """
    与Report Agent对话
    
    Report Agent可以在对话中自主调用检索工具来回答问题
    
    请求（JSON）：
        {
            "simulation_id": "sim_xxxx",        // 必填，模拟ID
            "message": "请解释一下舆情走向",    // 必填，用户消息
            "chat_history": [                   // 可选，对话历史
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }
    
    返回：
        {
            "success": true,
            "data": {
                "response": "Agent回复...",
                "tool_calls": [调用的工具列表],
                "sources": [信息来源]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        message = data.get('message')
        chat_history = data.get('chat_history', [])
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t('api.requireSimulationId')
            }), 400

        if not message:
            return jsonify({
                "success": False,
                "error": t('api.requireMessage')
            }), 400
        
        # 获取模拟和项目信息
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": t('api.simulationNotFound', id=simulation_id)
            }), 404

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=state.project_id)
            }), 404
        
        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": t('api.missingGraphId')
            }), 400
        
        simulation_requirement = project.simulation_requirement or ""
        
        # 创建Agent并进行对话
        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement
        )
        
        result = agent.chat(message=message, chat_history=chat_history)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"对话失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 报告状态检查接口 ==============

@report_bp.route('/check/<simulation_id>', methods=['GET'])
def check_report_status(simulation_id: str):
    """
    检查模拟是否有报告，以及报告状态
    
    用于前端判断是否解锁Interview功能
    
    返回：
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "has_report": true,
                "report_status": "completed",
                "report_id": "report_xxxx",
                "interview_unlocked": true
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)
        
        has_report = report is not None
        report_status = report.status.value if report else None
        report_id = report.report_id if report else None
        
        # 只有报告完成后才解锁interview
        interview_unlocked = has_report and report.status == ReportStatus.COMPLETED
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "has_report": has_report,
                "report_status": report_status,
                "report_id": report_id,
                "interview_unlocked": interview_unlocked
            }
        })
        
    except Exception as e:
        logger.error(f"检查报告状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Agent 日志接口 ==============

@report_bp.route('/<report_id>/agent-log', methods=['GET'])
def get_agent_log(report_id: str):
    """
    获取 Report Agent 的详细执行日志
    
    实时获取报告生成过程中的每一步动作，包括：
    - 报告开始、规划开始/完成
    - 每个章节的开始、工具调用、LLM响应、完成
    - 报告完成或失败
    
    Query参数：
        from_line: 从第几行开始读取（可选，默认0，用于增量获取）
    
    返回：
        {
            "success": true,
            "data": {
                "logs": [
                    {
                        "timestamp": "2025-12-13T...",
                        "elapsed_seconds": 12.5,
                        "report_id": "report_xxxx",
                        "action": "tool_call",
                        "stage": "generating",
                        "section_title": "执行摘要",
                        "section_index": 1,
                        "details": {
                            "tool_name": "insight_forge",
                            "parameters": {...},
                            ...
                        }
                    },
                    ...
                ],
                "total_lines": 25,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)
        
        log_data = ReportManager.get_agent_log(report_id, from_line=from_line)
        
        return jsonify({
            "success": True,
            "data": log_data
        })
        
    except Exception as e:
        logger.error(f"获取Agent日志失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 控制台日志接口 ==============

@report_bp.route('/<report_id>/console-log', methods=['GET'])
def get_console_log(report_id: str):
    """
    获取 Report Agent 的控制台输出日志
    
    实时获取报告生成过程中的控制台输出（INFO、WARNING等），
    这与 agent-log 接口返回的结构化 JSON 日志不同，
    是纯文本格式的控制台风格日志。
    
    Query参数：
        from_line: 从第几行开始读取（可选，默认0，用于增量获取）
    
    返回：
        {
            "success": true,
            "data": {
                "logs": [
                    "[19:46:14] INFO: 搜索完成: 找到 15 条相关事实",
                    "[19:46:14] INFO: 图谱搜索: graph_id=xxx, query=...",
                    ...
                ],
                "total_lines": 100,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)
        
        log_data = ReportManager.get_console_log(report_id, from_line=from_line)
        
        return jsonify({
            "success": True,
            "data": log_data
        })
        
    except Exception as e:
        logger.error(f"获取控制台日志失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


