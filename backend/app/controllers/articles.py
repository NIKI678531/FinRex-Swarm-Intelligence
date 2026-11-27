"""
FMP 文章相关 API：
- GET  /api/graph/articles                                列表代理（隐藏 apikey）
- POST /api/graph/ontology/generate-from-articles         用勾选文章作为现实种子生成本体

复用现有 OntologyGenerator / ProjectManager / TextProcessor，等同于 /ontology/generate
但输入来自 FMP API 文章而非用户上传的文件。
"""

import json
import os
import re
import traceback
from datetime import datetime, timezone
from flask import request, jsonify

import requests

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.text_processor import TextProcessor
from ..utils.logger import get_logger
from ..utils.locale import t
from ..repositories.project_repository import ProjectManager, ProjectStatus

logger = get_logger('finrex.api.articles')


_VALID_TARGET_TYPES = {'stock', 'crypto', 'event'}
_ALLOWED_HORIZON_DAYS = (1, 3, 5, 10)


def _clamp_horizon_days(value, default: int = 1) -> int:
    """Normalize a forecast horizon to one of the supported day buckets."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n in _ALLOWED_HORIZON_DAYS:
        return n
    # snap to the nearest allowed bucket
    return min(_ALLOWED_HORIZON_DAYS, key=lambda d: abs(d - n))


def _extract_target_asset(raw) -> dict | None:
    """从 JSON payload 提取金融预测标的。为空返回 None。"""
    if not isinstance(raw, dict):
        return None
    symbol = (raw.get('symbol') or '').strip()
    asset_type = (raw.get('type') or '').strip().lower()
    market = (raw.get('market') or '').strip()
    if not symbol and asset_type not in _VALID_TARGET_TYPES:
        return None
    if asset_type not in _VALID_TARGET_TYPES:
        asset_type = 'event'
    return {
        'symbol': symbol,
        'type': asset_type,
        'market': market,
        'horizon_days': _clamp_horizon_days(raw.get('horizon_days')),
    }


@graph_bp.route('/articles', methods=['GET'])
def list_articles():
    """
    代理 FMP 的文章列表 API，隐藏 apikey。

    Query 参数:
        page  (int, 默认 0):  FMP 是 0-based 分页
        limit (int, 默认 20): 每页条数，clamp 到 [1, 100]

    返回:
        {success, data: {items: [...], page, limit}}
    """
    try:
        if not Config.FMP_API_KEY:
            return jsonify({
                "success": False,
                "error": t('api.fmpApiKeyMissing')
            }), 500

        page = request.args.get('page', 0, type=int)
        limit = request.args.get('limit', 20, type=int)

        if page < 0:
            page = 0
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100

        url = f"{Config.FMP_BASE_URL.rstrip('/')}/fmp-articles"
        params = {
            "page": page,
            "limit": limit,
            "apikey": Config.FMP_API_KEY,
        }

        logger.info(f"FMP articles request: page={page}, limit={limit}")
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json()

        if not isinstance(items, list):
            items = []

        return jsonify({
            "success": True,
            "data": {
                "items": items,
                "page": page,
                "limit": limit,
                "count": len(items),
            }
        })

    except requests.RequestException as e:
        logger.error(f"FMP articles request failed: {e}")
        return jsonify({
            "success": False,
            "error": t('api.fmpRequestFailed', error=str(e))
        }), 502
    except Exception as e:
        logger.error(f"FMP articles unexpected error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/ontology/generate-from-articles', methods=['POST'])
def generate_ontology_from_articles():
    """
    用勾选的 FMP 文章作为现实种子生成本体。
    输入:
        {
          "articles": [{title, content, date, link, tickers?, author?, site?}, ...],
          "simulation_requirement": "...",
          "project_name": "...",          // 可选
          "additional_context": "..."     // 可选
        }
    输出与 /ontology/generate 一致。
    """
    try:
        logger.info("=== 开始生成本体定义（来自 FMP 文章） ===")

        payload = request.get_json(silent=True) or {}
        articles = payload.get('articles') or []
        simulation_requirement = (payload.get('simulation_requirement') or '').strip()
        project_name = payload.get('project_name') or 'FMP Articles Project'
        additional_context = payload.get('additional_context') or ''
        target_asset = _extract_target_asset(payload.get('target_asset'))
        financial_seed_context = payload.get('financial_seed_context') or None

        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": t('api.requireSimulationRequirement')
            }), 400

        if not isinstance(articles, list) or len(articles) == 0:
            return jsonify({
                "success": False,
                "error": t('api.requireArticles')
            }), 400

        # 创建项目
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        if target_asset:
            project.target_asset = target_asset
        if isinstance(financial_seed_context, dict):
            project.financial_seed_context = {
                'selected_articles': financial_seed_context.get('selected_articles') or [],
                'comments': financial_seed_context.get('comments') or [],
                'metadata': financial_seed_context.get('metadata') or {},
            }
        logger.info(f"创建项目: {project.project_id}, 文章数: {len(articles)}")

        # 把每篇文章组装成一段文本（HTML 标签原样保留交给 LLM）
        document_texts = []
        all_text_parts = []
        for idx, art in enumerate(articles):
            if not isinstance(art, dict):
                continue
            title = (art.get('title') or '').strip() or f'Untitled Article {idx + 1}'
            content = art.get('content') or ''
            date = art.get('date') or ''
            link = art.get('link') or ''
            tickers = art.get('tickers') or ''
            author = art.get('author') or ''
            site = art.get('site') or ''

            header_meta = []
            if date:
                header_meta.append(f"date: {date}")
            if tickers:
                header_meta.append(f"tickers: {tickers}")
            if author:
                header_meta.append(f"author: {author}")
            if site:
                header_meta.append(f"site: {site}")
            meta_line = " | ".join(header_meta)

            article_block = f"=== {title} ===\n"
            if meta_line:
                article_block += f"{meta_line}\n"
            article_block += f"\n{content}\n"
            if link:
                article_block += f"\n(source: {link})\n"

            processed = TextProcessor.preprocess_text(article_block)
            document_texts.append(processed)
            all_text_parts.append(article_block)

            # 在 project.files 中放入伪条目，便于历史项目列表展示
            project.files.append({
                "filename": f"FMP Article: {title}",
                "size": len(content),
            })

        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": t('api.noDocProcessed')
            }), 400

        all_text = "\n\n".join(all_text_parts)
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"文章文本拼接完成，共 {len(all_text)} 字符")

        # 生成本体（与 /ontology/generate 完全一致的调用）
        logger.info("调用 LLM 生成本体定义...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )

        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"本体生成完成: {entity_count} 个实体类型, {edge_count} 个关系类型")

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== 本体生成完成 === 项目ID: {project.project_id}")

        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })

    except Exception as e:
        logger.error(f"generate_ontology_from_articles failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============================================================================
# Binance 评论区数据源（Cloudflare D1）
# ============================================================================

class D1Unavailable(RuntimeError):
    """Cloudflare D1 is unavailable or not authorized for this backend."""


class D1QueryError(RuntimeError):
    """Cloudflare D1 accepted the request but rejected the SQL/query shape."""


def _d1_empty_payload(page: int, limit: int, source: str, reason: str, *, code: str = "d1_unavailable") -> dict:
    return {
        "success": True,
        "data": {
            "items": [],
            "page": page,
            "limit": limit,
            "count": 0,
            "source": source,
            "allowed_sources": Config.BINANCE_D1_ALLOWED_SOURCES,
            "comments_available": False,
            "data_quality": {
                "source": "cloudflare_d1",
                "available": False,
                "code": code,
                "reason": reason,
            },
            "warning": "",
        },
    }


def _d1_fallback_payload(
    page: int,
    limit: int,
    source: str,
    reason: str,
    items: list,
    *,
    code: str = "d1_unavailable",
    fallback_source: str = "local_jsonl_cache",
) -> dict:
    return {
        "success": True,
        "data": {
            "items": items,
            "page": page,
            "limit": limit,
            "count": len(items),
            "source": source,
            "allowed_sources": Config.BINANCE_D1_ALLOWED_SOURCES,
            "comments_available": False,
            "data_quality": {
                "source": "cloudflare_d1",
                "available": False,
                "code": code,
                "reason": reason,
                "fallback_source": fallback_source,
                "fallback_count": len(items),
                "source_filter_supported": False,
            },
            "warning": (
                "实时 Binance 社区数据源（Cloudflare D1）暂不可用，"
                "当前展示的是本地缓存帖子，可能不是最新数据。"
                "请检查 .env 中的 CLOUDFLARE_D1_* 配置或重新生成未过期的 API Token。"
            ),
        },
    }


def _binance_live_payload(page: int, limit: int, source: str, items: list) -> dict:
    return {
        "success": True,
        "data": {
            "items": items,
            "page": page,
            "limit": limit,
            "count": len(items),
            "source": source,
            "allowed_sources": Config.BINANCE_D1_ALLOWED_SOURCES,
            "comments_available": False,
            "data_quality": {
                "source": "binance_public_cms",
                "available": True,
                "realtime": True,
                "fallback_for": "cloudflare_d1",
                "source_filter_supported": False,
            },
            "warning": (
                "实时 Binance 社区数据源（Cloudflare D1）暂不可用，"
                "当前展示的是币安公开公告流，仅按标题匹配、不含社区帖子内容，"
                "搜索结果可能不完整或不是最新。请检查 .env 中的 CLOUDFLARE_D1_* 配置或重新生成未过期的 API Token。"
            ),
        },
    }


def _d1_empty_comments_payload(post_id: str, reason: str, *, code: str = "d1_unavailable") -> dict:
    return {
        "success": True,
        "data": {
            "post_id": post_id,
            "items": [],
            "count": 0,
            "comments_available": False,
            "unavailable_reason": reason,
            "data_quality": {
                "source": "cloudflare_d1",
                "available": False,
                "code": code,
                "reason": reason,
            },
        },
    }


def _cloudflare_d1_query(sql: str, params: list, timeout: int = 15) -> list:
    """
    向 Cloudflare D1 发送一条 SQL 查询，返回 results 数组。
    抛出 RuntimeError 表示配置缺失，requests.RequestException 表示网络错误。
    """
    account_id = Config.CLOUDFLARE_D1_ACCOUNT_ID
    db_id = Config.CLOUDFLARE_D1_DATABASE_ID
    token = Config.CLOUDFLARE_D1_API_TOKEN
    if not (account_id and db_id and token):
        raise D1Unavailable("Cloudflare D1 is not configured for this environment.")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
        f"/d1/database/{db_id}/query"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            url,
            headers=headers,
            json={"sql": sql, "params": params},
            timeout=timeout,
        )
        if resp.status_code in (401, 403):
            raise D1Unavailable(
                "Cloudflare D1 credentials are not authorized for this account/database."
            )
        resp.raise_for_status()
    except D1Unavailable:
        raise
    except requests.RequestException as exc:
        raise D1Unavailable(f"Cloudflare D1 request failed ({exc.__class__.__name__}).") from exc
    try:
        payload = resp.json()
    except ValueError as exc:
        raise D1Unavailable("Cloudflare D1 returned a non-JSON response.") from exc
    if not payload.get("success"):
        errs = payload.get("errors") or []
        safe_errors = []
        for err in errs[:3]:
            if isinstance(err, dict):
                safe_errors.append({"code": err.get("code"), "message": err.get("message")})
            else:
                safe_errors.append(str(err))
        raise D1QueryError(f"Cloudflare D1 query failed: {safe_errors}")
    result_blocks = payload.get("result") or []
    if not result_blocks:
        return []
    return result_blocks[0].get("results") or []


def _binance_cache_dir() -> str:
    return os.path.join(Config.UPLOAD_FOLDER, "backtest", "sentiment", "binance")


def _coerce_unix_seconds(value) -> int:
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        return int(ts)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return int(parsed.timestamp())
        except ValueError:
            return 0
    return 0


def _format_unix_date(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError):
        return ""


def _extract_cms_text(node) -> str:
    if isinstance(node, dict):
        parts = []
        text = node.get("text")
        if isinstance(text, str):
            parts.append(text)
        child = node.get("child")
        if isinstance(child, list):
            parts.extend(_extract_cms_text(item) for item in child)
        return " ".join(part for part in parts if part)
    if isinstance(node, list):
        return " ".join(_extract_cms_text(item) for item in node)
    return ""


def _binance_announcement_url(title: str, code: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    if slug:
        return f"https://www.binance.com/en/support/announcement/{slug}-{code}"
    return f"https://www.binance.com/en/support/announcement/{code}"


def _extract_binance_tickers(title: str, pairs) -> str:
    if isinstance(pairs, list) and pairs:
        values = []
        for pair in pairs[:8]:
            if isinstance(pair, dict):
                values.append(pair.get("symbol") or pair.get("pair") or pair.get("name"))
            else:
                values.append(pair)
        return ", ".join(str(v) for v in values if v)
    found = re.findall(r"\b[A-Z0-9]{2,20}USDT\b|\b[A-Z]{2,10}\b", title or "")
    stop = {"USD", "USDT", "UTC", "VIP", "API", "NFT", "ETF", "USDⓈ"}
    seen = []
    for item in found:
        if item in stop or item in seen:
            continue
        seen.append(item)
    return ", ".join(seen[:8])


def _normalize_binance_cms_article(article: dict, detail: dict | None, content_max_chars: int) -> dict:
    detail = detail or {}
    title = detail.get("title") or article.get("title") or ""
    code = detail.get("code") or article.get("code") or ""
    release_ms = (
        detail.get("publishDate") or detail.get("lastUpdateTime") or
        article.get("releaseDate") or article.get("publishDate")
    )
    publish_time = _coerce_unix_seconds(release_ms)
    body = detail.get("body") or ""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass
    content = _extract_cms_text(body) or detail.get("seoDesc") or title
    return {
        "id": f"binance-news:{code or article.get('id')}",
        "title": title,
        "content": _truncate(content, content_max_chars),
        "date": _format_unix_date(publish_time),
        "author": "Binance",
        "link": _binance_announcement_url(title, code) if code else "",
        "tickers": _extract_binance_tickers(title, detail.get("pairs")),
        "site": "Binance Announcements",
        "source": "binance_live_news",
        "comments_count": 0,
        "like_count": int(detail.get("shareCount") or 0),
        "view_count": 0,
        "publish_time": publish_time,
    }


def _fetch_binance_live_news(
    *,
    page: int,
    limit: int,
    since: int | None = None,
    q: str = "",
    min_comments: int | None = None,
) -> list:
    if min_comments and min_comments > 0:
        return []

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "clienttype": "web",
        "lang": "en",
    }
    list_url = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
    params = {"type": 1, "pageNo": 1, "pageSize": 50}
    resp = requests.get(list_url, params=params, headers=headers, timeout=12)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success", payload.get("code") == "000000"):
        raise D1Unavailable("Binance public CMS feed is unavailable.")

    by_code = {}
    for catalog in (payload.get("data") or {}).get("catalogs") or []:
        for article in catalog.get("articles") or []:
            code = article.get("code")
            if not code or code in by_code:
                continue
            by_code[code] = article

    candidates = sorted(
        by_code.values(),
        key=lambda item: int(item.get("releaseDate") or 0),
        reverse=True,
    )
    content_max = Config.BINANCE_D1_CONTENT_MAX_CHARS
    q_lower = (q or "").strip().lower()
    preliminary = []
    for article in candidates:
        release_time = _coerce_unix_seconds(article.get("releaseDate"))
        if since and release_time and release_time <= since:
            continue
        if q_lower and q_lower not in (article.get("title") or "").lower():
            continue
        preliminary.append(article)

    detail_url = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query"
    start = page * limit
    selected = preliminary[start:start + limit]
    items = []
    for idx, article in enumerate(selected):
        detail = None
        code = article.get("code")
        if code and idx < 10:
            try:
                detail_resp = requests.get(
                    detail_url,
                    params={"articleCode": code},
                    headers=headers,
                    timeout=10,
                )
                detail_resp.raise_for_status()
                detail_payload = detail_resp.json()
                if detail_payload.get("success", detail_payload.get("code") == "000000"):
                    detail = detail_payload.get("data") or None
            except requests.RequestException as exc:
                logger.warning(f"Binance CMS detail failed code={code}: {exc.__class__.__name__}")
        item = _normalize_binance_cms_article(article, detail, content_max)
        items.append(item)

    items.sort(key=lambda item: int(item.get("publish_time") or 0), reverse=True)
    return items


def _normalize_cached_binance_row(row: dict, content_max_chars: int) -> dict:
    published_at = row.get("published_at") or row.get("date") or ""
    publish_time = _coerce_unix_seconds(published_at or row.get("publish_time"))
    content = row.get("text") or row.get("content") or ""
    title = row.get("title") or ""
    if not title and content:
        title = (content[:80] + "...") if len(content) > 80 else content

    tickers = ""
    raw_symbols = row.get("symbol") or row.get("tickers") or ""
    if raw_symbols:
        try:
            parsed = json.loads(raw_symbols) if isinstance(raw_symbols, str) else raw_symbols
            if isinstance(parsed, list):
                tickers = ", ".join(str(x) for x in parsed[:6])
            else:
                tickers = str(parsed)
        except (TypeError, ValueError):
            tickers = str(raw_symbols)

    link = row.get("url") or row.get("link") or ""
    return {
        "id": row.get("id") or link or f"cache:{publish_time}:{row.get('author') or ''}:{title[:24]}",
        "title": title,
        "content": _truncate(content, content_max_chars),
        "date": _format_unix_date(publish_time) or published_at,
        "author": row.get("author") or row.get("author_name") or "",
        "link": link,
        "tickers": tickers,
        "site": row.get("site") or "Binance Square",
        "source": row.get("source") or "binance_cache",
        "comments_count": row.get("comment_count") or row.get("comments_count") or 0,
        "like_count": row.get("like_count") or 0,
        "view_count": row.get("view_count") or 0,
        "publish_time": publish_time,
    }


def _load_cached_binance_articles(
    *,
    page: int,
    limit: int,
    since: int | None = None,
    q: str = "",
    min_comments: int | None = None,
) -> list:
    cache_dir = _binance_cache_dir()
    if not os.path.isdir(cache_dir):
        return []

    q_lower = (q or "").strip().lower()
    content_max = Config.BINANCE_D1_CONTENT_MAX_CHARS
    items = []
    for name in sorted(os.listdir(cache_dir), reverse=True):
        if not name.endswith(".jsonl"):
            continue
        path = os.path.join(cache_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    item = _normalize_cached_binance_row(row, content_max)
                    if since and item.get("publish_time", 0) <= since:
                        continue
                    if min_comments and int(item.get("comments_count") or 0) < min_comments:
                        continue
                    if q_lower:
                        haystack = f"{item.get('title') or ''}\n{item.get('content') or ''}".lower()
                        if q_lower not in haystack:
                            continue
                    items.append(item)
        except OSError as exc:
            logger.warning(f"Binance cache read failed path={path}: {exc}")

    items.sort(key=lambda item: int(item.get("publish_time") or 0), reverse=True)
    start = page * limit
    return items[start:start + limit]


def _binance_articles_unavailable_response(
    *,
    page: int,
    limit: int,
    source: str,
    reason: str,
    code: str = "d1_unavailable",
    since: int | None = None,
    q: str = "",
    min_comments: int | None = None,
):
    try:
        live_items = _fetch_binance_live_news(
            page=page,
            limit=limit,
            since=since,
            q=q,
            min_comments=min_comments,
        )
        if live_items:
            return jsonify(_binance_live_payload(page, limit, source, live_items)), 200
    except Exception as exc:
        logger.warning(f"Binance live news fallback failed: {exc}")

    cached_items = _load_cached_binance_articles(
        page=page,
        limit=limit,
        since=since,
        q=q,
        min_comments=min_comments,
    )
    if cached_items:
        return jsonify(_d1_fallback_payload(
            page,
            limit,
            source,
            reason,
            cached_items,
            code=code,
        )), 200
    return jsonify(_d1_empty_payload(page, limit, source, reason, code=code)), 200


def _truncate(text, max_chars: int) -> str:
    if not isinstance(text, str):
        return text
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def _normalize_binance_row(row: dict, content_max_chars: int) -> dict:
    """
    把 D1 posts 表的一行帖子规范化成与 FMP article 兼容的形状，方便前端复用同一渲染。
    真实 schema (D1.posts):
      id, source, card_type, content_type, title, sub_title, content,
      author_name, author_id, author_avatar, publish_time (unix 秒/毫秒),
      web_link, share_link,
      like_count, comment_count, share_count, view_count, quote_count, reply_count,
      images_json, hashtags_json, trading_pairs_json, raw_json,
      first_seen_at, last_seen_at
    """
    publish_time = row.get('publish_time')
    date_str = ''
    try:
        if isinstance(publish_time, (int, float)) and publish_time > 0:
            from datetime import datetime, timezone
            ts = float(publish_time)
            if ts > 1e12:  # 毫秒转秒
                ts = ts / 1000.0
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc) \
                .strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(publish_time, str):
            date_str = publish_time
    except Exception:
        date_str = str(publish_time) if publish_time else ''

    content = row.get('content') or ''
    title = row.get('title') or row.get('sub_title') or ''
    if not title and content:
        title = (content[:80] + '…') if len(content) > 80 else content

    # trading_pairs_json: '["BTCUSDT", "ETHUSDT"]'
    tickers = ''
    tp_json = row.get('trading_pairs_json')
    if tp_json:
        try:
            import json as _json
            arr = _json.loads(tp_json) if isinstance(tp_json, str) else tp_json
            if isinstance(arr, list):
                tickers = ', '.join(str(x) for x in arr[:6])
        except Exception:
            tickers = ''

    return {
        "id": row.get('id'),
        "title": title,
        "content": _truncate(content, content_max_chars),
        "date": date_str,
        "author": row.get('author_name') or '',
        "link": row.get('web_link') or row.get('share_link') or '',
        "tickers": tickers,
        "site": "Binance Square",
        "source": row.get('source') or '',
        "comments_count": row.get('comment_count') or 0,
        "like_count": row.get('like_count') or 0,
        "view_count": row.get('view_count') or 0,
        "publish_time": publish_time,
    }


@graph_bp.route('/articles/binance', methods=['GET'])
def list_binance_articles():
    """
    从 Cloudflare D1 拉取 Binance Square 帖子。

    Query 参数:
        page   (int, 默认 0):   分页（0-based）
        limit  (int, 默认 20):  每页条数，clamp 到 [1, BINANCE_D1_MAX_LIMIT]
        source (str, 默认 news): feed | hashtag | news | user；传 'all' 不过滤
        since  (int, 可选):     仅返回 publish_time > since 的（秒级 unix）
        q      (str, 可选):     标题 / 内容模糊匹配
        min_comments (int, 可选): 最少评论数，过滤掉低交互贴
    """
    try:
        page = request.args.get('page', 0, type=int)
        limit = request.args.get('limit', 20, type=int)
        since = request.args.get('since', type=int)
        min_comments = request.args.get('min_comments', type=int)
        q = (request.args.get('q') or '').strip()
        source_param = (request.args.get('source') or Config.BINANCE_D1_DEFAULT_SOURCE).strip()

        if page < 0:
            page = 0
        max_limit = Config.BINANCE_D1_MAX_LIMIT
        if limit < 1:
            limit = 1
        if limit > max_limit:
            limit = max_limit

        offset = page * limit

        where = []
        params: list = []
        # source 取值限制在白名单内，避免任意输入
        if source_param and source_param != 'all':
            if source_param not in Config.BINANCE_D1_ALLOWED_SOURCES:
                return jsonify({
                    "success": False,
                    "error": f"不支持的 source: {source_param}，可选: {Config.BINANCE_D1_ALLOWED_SOURCES} 或 'all'"
                }), 400
            where.append("source = ?")
            params.append(source_param)
        if since and since > 0:
            where.append("publish_time > ?")
            params.append(since)
        if min_comments and min_comments > 0:
            where.append("comment_count >= ?")
            params.append(min_comments)
        if q:
            where.append("(title LIKE ? OR content LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like])

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        sql = (
            "SELECT id, source, title, sub_title, content, author_name, "
            "publish_time, web_link, share_link, "
            "like_count, comment_count, view_count, trading_pairs_json "
            f"FROM posts{where_sql} "
            "ORDER BY publish_time DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])

        logger.info(
            f"D1 binance articles: source={source_param}, page={page}, limit={limit}, "
            f"since={since}, min_comments={min_comments}, q={'Y' if q else 'N'}"
        )

        rows = _cloudflare_d1_query(sql, params)
        content_max = Config.BINANCE_D1_CONTENT_MAX_CHARS
        items = [_normalize_binance_row(r, content_max) for r in rows]

        return jsonify({
            "success": True,
            "data": {
                "items": items,
                "page": page,
                "limit": limit,
                "count": len(items),
                "source": source_param,
                "allowed_sources": Config.BINANCE_D1_ALLOWED_SOURCES,
            }
        })

    except D1Unavailable as e:
        reason = str(e)
        logger.warning(f"D1 binance unavailable: {reason}")
        return _binance_articles_unavailable_response(
            page=page,
            limit=limit,
            source=source_param,
            reason=reason,
            since=since,
            q=q,
            min_comments=min_comments,
        )
    except D1QueryError as e:
        reason = str(e)
        logger.warning(f"D1 binance query unavailable: {reason}")
        return _binance_articles_unavailable_response(
            page=page,
            limit=limit,
            source=source_param,
            reason=reason,
            code="d1_query_error",
            since=since,
            q=q,
            min_comments=min_comments,
        )
    except requests.RequestException as e:
        reason = f"Cloudflare D1 request failed ({e.__class__.__name__})."
        logger.warning(f"D1 binance request failed: {reason}")
        return _binance_articles_unavailable_response(
            page=page,
            limit=limit,
            source=source_param,
            reason=reason,
            since=since,
            q=q,
            min_comments=min_comments,
        )
    except RuntimeError as e:
        logger.error(f"D1 binance config/query error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        logger.error(f"list_binance_articles unexpected error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _normalize_binance_comment_row(row: dict) -> dict:
    text = (
        row.get('text') or row.get('content') or row.get('body') or
        row.get('comment') or row.get('comment_text') or row.get('message') or ''
    )
    author = row.get('author_name') or row.get('author') or row.get('username') or row.get('user_name') or ''
    return {
        "id": row.get('id') or row.get('comment_id'),
        "post_id": row.get('post_id') or row.get('article_id'),
        "text": _truncate(text, Config.BINANCE_D1_CONTENT_MAX_CHARS),
        "author": author,
        "author_id": row.get('author_id') or row.get('user_id'),
        "created_at": row.get('created_at') or row.get('publish_time') or row.get('timestamp') or '',
        "like_count": row.get('like_count') or row.get('likes') or row.get('upvotes') or 0,
        "reply_count": row.get('reply_count') or row.get('replies') or 0,
        "source": row.get('source') or 'binance',
    }


@graph_bp.route('/articles/binance/<post_id>/comments', methods=['GET'])
def list_binance_article_comments(post_id: str):
    """Fetch Binance Square comment rows for a post when the D1 schema provides them.

    Some D1 snapshots only contain post-level metadata. In that case this endpoint
    returns success with an empty list and an unavailable_reason so callers can run
    agent-only augmentation instead of treating comment_count as real text.
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        limit = max(1, min(limit, 500))
        offset = max(0, offset)

        candidate_tables = ['comments', 'post_comments', 'binance_comments']
        last_error = None
        rows = []
        used_table = None
        for table in candidate_tables:
            for id_column in ('post_id', 'article_id'):
                try:
                    sql = f"SELECT * FROM {table} WHERE {id_column} = ? LIMIT ? OFFSET ?"
                    rows = _cloudflare_d1_query(sql, [post_id, limit, offset])
                    used_table = table
                    break
                except D1Unavailable:
                    raise
                except Exception as table_exc:
                    last_error = table_exc
                    continue
            if used_table is not None:
                break

        if used_table is None:
            reason = str(last_error) if last_error else "comments table not found"
            code = "d1_query_error" if isinstance(last_error, D1QueryError) else "comments_unavailable"
            return jsonify(_d1_empty_comments_payload(post_id, reason, code=code))

        items = [c for c in (_normalize_binance_comment_row(r) for r in rows) if c.get('text')]
        return jsonify({
            "success": True,
            "data": {
                "post_id": post_id,
                "items": items,
                "count": len(items),
                "comments_available": True,
                "table": used_table,
                "limit": limit,
                "offset": offset,
            }
        })
    except D1Unavailable as e:
        reason = str(e)
        logger.warning(f"D1 binance comments unavailable: {reason}")
        return jsonify(_d1_empty_comments_payload(post_id, reason)), 200
    except D1QueryError as e:
        reason = str(e)
        logger.warning(f"D1 binance comments query unavailable: {reason}")
        return jsonify(_d1_empty_comments_payload(post_id, reason, code="d1_query_error")), 200
    except requests.RequestException as e:
        reason = f"Cloudflare D1 request failed ({e.__class__.__name__})."
        logger.warning(f"D1 binance comments request failed: {reason}")
        return jsonify(_d1_empty_comments_payload(post_id, reason)), 200
    except RuntimeError as e:
        logger.error(f"D1 binance comments config/query error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        logger.error(f"list_binance_article_comments unexpected error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
