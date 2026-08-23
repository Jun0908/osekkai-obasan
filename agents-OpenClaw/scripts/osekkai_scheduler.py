"""Fault-isolated live source scheduler and canonical Event Mesh cache."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from osekkai_connection import extract_connection_evidence
from osekkai_contracts import ContractError
from osekkai_doorkeeper import DoorkeeperError, sync_doorkeeper
from osekkai_event_normalizer import normalize_event_mesh
from osekkai_freebusy import ProviderError
from osekkai_luma import LumaError, sync_configured_calendar
from osekkai_opportunity_sync import events_to_opportunities
from osekkai_public_events import PublicEventError, sync_kcf_courses
from osekkai_routes import RoutesError, compute_event_route
from osekkai_source_registry import is_stale, load_source_registry, source_state
from osekkai_store import JsonStore, LockTimeout, StorageError
from osekkai_tokyo_ckan import CkanError, discover_datasets


ProviderAdapter = Callable[[datetime], Mapping[str, Any]]
RouteResolver = Callable[[Mapping[str, Any], Mapping[str, Any], datetime], Mapping[str, Any]]


class SchedulerError(RuntimeError):
    pass


def _cache_path(store: JsonStore, source_id: str) -> Path:
    return store._safe_path("opportunities", "sources", f"{source_id}.json")


def _mesh_path(store: JsonStore) -> Path:
    return store._safe_path("opportunities", "live-event-mesh.json")


def _status_path(store: JsonStore) -> Path:
    return store._safe_path("opportunities", "source-status.json")


def live_opportunities_path(store: JsonStore) -> Path:
    return store._safe_path("opportunities", "live-opportunities.json")


def _read(path: Path, default: Any) -> Any:
    return JsonStore._read_json(path, default)


def _checksum(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _default_adapter(source_id: str) -> ProviderAdapter:
    if source_id == "tokyo_ckan":
        return lambda now: {
            **discover_datasets(now=now, queries=("イベント", "交流 講座"), rows_per_query=5, inspect_resources=True),
            "events": [],
            "series": [],
            "communities": [],
        }
    if source_id == "luma_tokyo":
        return lambda now: sync_configured_calendar(fetched_at=now)
    if source_id == "doorkeeper":
        return lambda now: sync_doorkeeper(now=now)
    if source_id == "koto_culture":
        return lambda now: sync_kcf_courses(fetched_at=now)
    raise SchedulerError(f"no scheduler adapter for source {source_id}")


def _runtime_status(
    source: Mapping[str, Any],
    readiness: Mapping[str, Any],
    cache: Mapping[str, Any] | None,
    now: datetime,
    *,
    attempted: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    last_success = cache.get("lastSuccessAt") if isinstance(cache, Mapping) else None
    stale = bool(last_success and is_stale(source, str(last_success), now))
    if error:
        health = "stale" if last_success else "error"
    elif readiness["state"] != "ready":
        health = readiness["state"]
    elif stale:
        health = "stale"
    elif last_success:
        health = "healthy"
    else:
        health = "never_synced"
    provider_result = cache.get("providerResult", {}) if isinstance(cache, Mapping) else {}
    events = provider_result.get("events", []) if isinstance(provider_result, Mapping) else []
    datasets = provider_result.get("datasets", []) if isinstance(provider_result, Mapping) else []
    return {
        "id": source["id"],
        "displayName": source["displayName"],
        "requiredForDemo": source["requiredForDemo"],
        "readiness": readiness["state"],
        "health": health,
        "lastAttemptAt": now.isoformat() if attempted else (cache or {}).get("lastAttemptAt"),
        "lastSuccessAt": last_success,
        "eventCount": len(events) if isinstance(events, list) else 0,
        "datasetCount": len(datasets) if isinstance(datasets, list) else 0,
        "error": error,
        "stale": stale,
        "refreshMinutes": source["refreshMinutes"],
    }


def _is_due(source: Mapping[str, Any], cache: Mapping[str, Any] | None, now: datetime) -> bool:
    if not cache or not cache.get("lastSuccessAt"):
        return True
    try:
        last = datetime.fromisoformat(str(cache["lastSuccessAt"]).replace("Z", "+00:00"))
    except ValueError:
        return True
    return now >= last + timedelta(minutes=int(source["refreshMinutes"]))


def _safe_error(exc: BaseException) -> str:
    # Provider exception messages are written only after obvious URL query and
    # credential material is removed. Credentials are never part of adapters'
    # success results or status output.
    message = str(exc).split("?", 1)[0].strip() or exc.__class__.__name__
    return message[:300]


def _origin(environ: Mapping[str, str]) -> dict[str, float] | None:
    try:
        latitude = float(str(environ.get("OSEKKAI_LIVE_ORIGIN_LATITUDE", "")))
        longitude = float(str(environ.get("OSEKKAI_LIVE_ORIGIN_LONGITUDE", "")))
    except ValueError:
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return {"latitude": latitude, "longitude": longitude}


def _default_route_resolver(origin: Mapping[str, Any], event: Mapping[str, Any], now: datetime) -> Mapping[str, Any]:
    departure = datetime.fromisoformat(str(event["startsAt"]).replace("Z", "+00:00")) - timedelta(hours=1)
    return compute_event_route(origin, event, departure_time=max(departure, now))


def _materialize(
    store: JsonStore,
    provider_results: Iterable[Mapping[str, Any]],
    *,
    now: datetime,
    environ: Mapping[str, str],
    route_resolver: RouteResolver | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    mesh = normalize_event_mesh(provider_results, now=now)
    series_by_id = {item["id"]: item for item in mesh["series"]}
    communities_by_id = {item["id"]: item for item in mesh["communities"]}
    connection: dict[str, dict[str, Any]] = {}
    for event in mesh["events"]:
        evidence = extract_connection_evidence(
            event,
            evaluated_at=now,
            series=series_by_id.get(event.get("seriesId")),
            community=communities_by_id.get(event.get("communityId")),
        )
        connection[event["id"]] = evidence
    mesh["connectionEvidence"] = list(connection.values())

    route_by_id: dict[str, Mapping[str, Any]] = {}
    route_errors: list[dict[str, str]] = []
    configured_origin = _origin(environ)
    resolver = route_resolver or _default_route_resolver
    maximum = max(1, min(50, int(str(environ.get("OSEKKAI_MAX_ROUTE_CANDIDATES", "8")))))
    if configured_origin:
        candidates = [
            event for event in mesh["eligibleEvents"]
            if connection[event["id"]]["connectionLevel"] >= 2
        ][:maximum]
        for event in candidates:
            try:
                route_by_id[event["id"]] = dict(resolver(configured_origin, event, now))
            except RoutesError as exc:
                route_errors.append({"eventId": event["id"], "code": exc.code})
            except Exception:
                route_errors.append({"eventId": event["id"], "code": "ROUTES_UNAVAILABLE"})
    else:
        route_errors.append({"eventId": "*", "code": "ROUTES_ORIGIN_MISSING"})
    mesh["routeErrors"] = route_errors
    mesh["routeCount"] = len(route_by_id)

    opportunities, excluded = events_to_opportunities(
        mesh["eligibleEvents"],
        connection_by_event_id=connection,
        route_by_event_id=route_by_id,
        series_by_id=series_by_id,
    )
    cache = {
        "schemaVersion": "1.0",
        "dataMode": "live",
        "notice": (
            "Live Event Meshから交流根拠とGoogle Routes実測を確認できた候補です。"
            if opportunities
            else "Live Eventは取得済みですが、交流根拠とGoogle Routes実測を満たすPUSH候補はありません。"
        ),
        "opportunities": opportunities,
    }
    mesh["opportunityExclusions"] = excluded
    store._atomic_write_json(_mesh_path(store), mesh)
    store._atomic_write_json(live_opportunities_path(store), cache)
    return mesh, cache


def run_sync(
    *,
    store: JsonStore | None = None,
    now: datetime | None = None,
    force: bool = False,
    source_ids: Iterable[str] | None = None,
    adapters: Mapping[str, ProviderAdapter] | None = None,
    source_definitions: list[Mapping[str, Any]] | None = None,
    environ: Mapping[str, str] | None = None,
    route_resolver: RouteResolver | None = None,
    attempts: int = 3,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    captured = now or datetime.now().astimezone()
    if captured.tzinfo is None:
        raise SchedulerError("scheduler now must include a timezone")
    storage = store or JsonStore()
    env = os.environ if environ is None else environ
    sources = source_definitions or load_source_registry(environ=env)["sources"]
    requested = set(source_ids or [source["id"] for source in sources])
    statuses: list[dict[str, Any]] = []
    provider_results: list[Mapping[str, Any]] = []
    for source in sources:
        source_id = str(source["id"])
        cache = _read(_cache_path(storage, source_id), None)
        readiness = source_state(source, env)
        should_try = source_id in requested and readiness["canSync"] and (force or _is_due(source, cache, captured))
        error: str | None = None
        attempted = False
        if should_try:
            attempted = True
            try:
                with storage._file_lock(f"source-{source_id}", storage.lock_timeout):
                    cache = _read(_cache_path(storage, source_id), None)
                    if force or _is_due(source, cache, captured):
                        adapter = (adapters or {}).get(source_id) or _default_adapter(source_id)
                        result: Mapping[str, Any] | None = None
                        for attempt in range(max(1, min(attempts, 5))):
                            try:
                                result = adapter(captured)
                                break
                            except (CkanError, LumaError, DoorkeeperError, PublicEventError, OSError, TimeoutError) as exc:
                                error = _safe_error(exc)
                                if attempt + 1 < attempts:
                                    sleeper(min(2 ** attempt, 4))
                        if result is None:
                            raise SchedulerError(error or "provider did not return data")
                        value = dict(result)
                        if value.get("provider") != source_id:
                            raise SchedulerError(f"provider result mismatch for {source_id}")
                        previous_checksum = cache.get("checksum") if isinstance(cache, Mapping) else None
                        digest = _checksum(value)
                        cache = {
                            "schemaVersion": "1.0",
                            "sourceId": source_id,
                            "lastAttemptAt": captured.isoformat(),
                            "lastSuccessAt": captured.isoformat(),
                            "checksum": digest,
                            "changed": digest != previous_checksum,
                            "providerResult": value,
                        }
                        storage._atomic_write_json(_cache_path(storage, source_id), cache)
                        error = None
            except (SchedulerError, StorageError, LockTimeout) as exc:
                error = _safe_error(exc)
        if isinstance(cache, Mapping) and isinstance(cache.get("providerResult"), Mapping):
            provider_results.append(cache["providerResult"])
        statuses.append(_runtime_status(source, readiness, cache, captured, attempted=attempted, error=error))
    mesh, opportunities = _materialize(
        storage,
        provider_results,
        now=captured,
        environ=env,
        route_resolver=route_resolver,
    )
    status = {
        "schemaVersion": "1.0",
        "dataMode": "live",
        "generatedAt": captured.isoformat(),
        "sources": statuses,
        "counts": {
            "events": len(mesh["events"]),
            "eligibleEvents": len(mesh["eligibleEvents"]),
            "opportunities": len(opportunities["opportunities"]),
            "providerErrors": len(mesh["providerErrors"]),
        },
    }
    storage._atomic_write_json(_status_path(storage), status)
    return copy.deepcopy(status)


def load_source_status(*, store: JsonStore | None = None, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    storage = store or JsonStore()
    cached = _read(_status_path(storage), None)
    if isinstance(cached, dict):
        return copy.deepcopy(cached)
    now = datetime.now().astimezone()
    registry = load_source_registry(environ=environ)
    return {
        "schemaVersion": "1.0",
        "dataMode": "live",
        "generatedAt": now.isoformat(),
        "sources": [
            _runtime_status(source, source_state(source, environ), None, now)
            for source in registry["sources"]
        ],
        "counts": {"events": 0, "eligibleEvents": 0, "opportunities": 0, "providerErrors": 0},
    }


def load_event_mesh(*, store: JsonStore | None = None) -> dict[str, Any]:
    storage = store or JsonStore()
    value = _read(_mesh_path(storage), None)
    if not isinstance(value, dict):
        return {
            "schemaVersion": "1.0",
            "dataMode": "live",
            "generatedAt": datetime.now().astimezone().isoformat(),
            "events": [],
            "eligibleEvents": [],
            "excludedEvents": [],
            "series": [],
            "communities": [],
            "providerErrors": [],
            "connectionEvidence": [],
            "routeErrors": [],
            "routeCount": 0,
            "opportunityExclusions": [],
            "counts": {"received": 0, "merged": 0, "eligible": 0, "excluded": 0},
        }
    return copy.deepcopy(value)


def run_calendar_conversation_triggers(
    *,
    store: JsonStore | None = None,
    now: datetime | None = None,
    data_mode: str = "live",
    user_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Evaluate registered users without exposing Calendar event details.

    The local import avoids a module cycle: the conversation trigger uses
    ``sync_before_push`` from this module for its final live revalidation.
    Delivery is intentionally separate; this worker only creates resumable
    Chat episodes that an approved notification channel may announce.
    """

    from osekkai_conversation import start_calendar_sparse_episode_unlocked

    storage = store or JsonStore()
    captured = now or datetime.now().astimezone()
    requested = list(user_ids) if user_ids is not None else storage.list_user_ids()
    created: list[dict[str, str]] = []
    skipped = 0
    for user_id in requested:
        try:
            with storage.user_lock(user_id):
                result = start_calendar_sparse_episode_unlocked(
                    storage, user_id, captured, data_mode
                )
        except (ContractError, ProviderError, StorageError, LockTimeout, OSError, TimeoutError):
            skipped += 1
            continue
        if result is None:
            skipped += 1
            continue
        created.append(
            {
                "userId": user_id,
                "episodeId": result["episode"]["id"],
                "state": result["episode"]["state"],
            }
        )
    return {
        "schemaVersion": "1.0",
        "evaluatedAt": captured.isoformat(),
        "created": created,
        "skipped": skipped,
    }


def sync_before_push(
    event_ids: Iterable[str],
    *,
    store: JsonStore | None = None,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, bool]:
    """Refresh only providers owning shortlisted events, fail closed per event."""

    storage = store or JsonStore()
    mesh = load_event_mesh(store=storage)
    wanted = set(event_ids)
    providers = {event["provider"] for event in mesh["events"] if event.get("id") in wanted}
    current = now or datetime.now().astimezone()
    status = None
    if providers:
        status = run_sync(store=storage, now=current, force=True, source_ids=providers, environ=environ, attempts=1)
    refreshed = {event["id"]: event for event in load_event_mesh(store=storage)["events"]}
    provider_health = {
        item["id"]: item.get("health") == "healthy" and item.get("lastSuccessAt") == current.isoformat()
        for item in (status or {}).get("sources", [])
    }
    return {
        event_id: bool(
            (event := refreshed.get(event_id))
            and provider_health.get(str(event.get("provider")), False)
            and event.get("status") == "scheduled"
            and event.get("registrationStatus") in {"open", "not_required"}
            and datetime.fromisoformat(str(event["endsAt"]).replace("Z", "+00:00")) > current
        )
        for event_id in wanted
    }
