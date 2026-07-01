"""
Description: Confirm Lambda for Snap & Cook. Entry point for the POST
             /recipes/{requestId}/confirm API route. Called after the user
             reviews and optionally edits the detected ingredients. Receives
             the confirmed ingredient list and recipe preferences (count,
             max prep time, dietary restrictions), validates the request is in
             AWAITING_CONFIRMATION state, persists the confirmed data to
             DynamoDB, and enqueues a phase='generate' SQS message so the
             processor Lambda runs Bedrock with the user's preferences.
             Returns 202 immediately; the frontend continues polling
             GET /recipes/{id} until status=COMPLETE.
             Secrets must come from environment variables, never hard-coded.
Last Modified By: bvela
Created: 2026-07-01
Last Modified:
    2026-07-01 - File created.
"""

import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb")
_sqs = boto3.client("sqs")

RESULTS_TABLE = os.environ["RESULTS_TABLE"]
JOB_QUEUE_URL = os.environ["JOB_QUEUE_URL"]

_MAX_RECIPE_COUNT = 5
_ALLOWED_DIETARY = {"vegetarian", "vegan", "gluten-free", "dairy-free", "low-carb"}
_ALLOWED_PREP_TIMES = {"15", "30", "45", "60", "90"}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point — confirm ingredients and queue recipe generation.

    Args:
        event: API Gateway proxy event. Path parameter 'requestId' identifies
               the job. JSON body must contain 'ingredients' (list) and
               optionally 'preferences' (dict).
        context: Lambda runtime context (unused).

    Returns:
        API Gateway-compatible response dict with statusCode and JSON body.
    """
    path_params = event.get("pathParameters") or {}
    request_id = path_params.get("requestId")
    if not request_id:
        return _error(400, "Missing requestId path parameter.")

    body_raw = event.get("body") or "{}"
    try:
        body = json.loads(body_raw)
    except json.JSONDecodeError:
        return _error(400, "Request body must be valid JSON.")

    ingredients = body.get("ingredients")
    if not isinstance(ingredients, list) or len(ingredients) == 0:
        return _error(400, "'ingredients' must be a non-empty list.")

    # Sanitise: strip whitespace, deduplicate, drop empty strings.
    ingredients = list({i.strip() for i in ingredients if isinstance(i, str) and i.strip()})
    if not ingredients:
        return _error(400, "'ingredients' contains no valid entries.")

    preferences = _validate_preferences(body.get("preferences") or {})

    logger.info(json.dumps({
        "msg": "confirm started",
        "requestId": request_id,
        "ingredient_count": len(ingredients),
        "preferences": preferences,
    }))

    # Guard: only confirm records that are waiting for user input.
    table = _dynamodb.Table(RESULTS_TABLE)
    result = table.get_item(Key={"requestId": request_id})
    item = result.get("Item")

    if item is None:
        return _error(404, "Request not found.")

    if item.get("status") != "AWAITING_CONFIRMATION":
        return _error(409, f"Cannot confirm a request with status '{item.get('status')}'.")

    # Persist confirmed ingredients + preferences, transition to GENERATING.
    table.update_item(
        Key={"requestId": request_id},
        UpdateExpression=(
            "SET #s = :s, confirmed_ingredients = :ci, preferences = :p, confirmed_at = :t"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "GENERATING",
            ":ci": ingredients,
            ":p": preferences,
            ":t": int(time.time()),
        },
    )

    # Enqueue the Bedrock generation phase.
    _sqs.send_message(
        QueueUrl=JOB_QUEUE_URL,
        MessageBody=json.dumps({"requestId": request_id, "phase": "generate"}),
        MessageAttributes={
            "requestId": {"StringValue": request_id, "DataType": "String"}
        },
    )

    logger.info(json.dumps({"msg": "confirm complete — generation queued", "requestId": request_id}))
    return {
        "statusCode": 202,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"requestId": request_id, "status": "GENERATING"}),
    }


def _validate_preferences(raw: dict[str, Any]) -> dict[str, Any]:
    """Sanitise and clamp user-supplied recipe preferences.

    Args:
        raw: Raw preferences dict from the request body.

    Returns:
        Cleaned preferences dict with validated values only.
    """
    prefs: dict[str, Any] = {}

    # recipe_count: integer 1–5, default 2
    try:
        count = int(raw.get("recipe_count", 2))
        prefs["recipe_count"] = max(1, min(_MAX_RECIPE_COUNT, count))
    except (ValueError, TypeError):
        prefs["recipe_count"] = 2

    # max_prep_time: allowed discrete values in minutes, or omit
    prep = str(raw.get("max_prep_time", "")).strip()
    if prep in _ALLOWED_PREP_TIMES:
        prefs["max_prep_time"] = prep

    # dietary: whitelist of known restrictions
    dietary_raw = raw.get("dietary") or []
    if isinstance(dietary_raw, list):
        prefs["dietary"] = [
            d for d in dietary_raw
            if isinstance(d, str) and d.lower() in _ALLOWED_DIETARY
        ]

    return prefs


def _error(status_code: int, message: str) -> dict[str, Any]:
    """Build an API Gateway error response with CORS headers.

    Args:
        status_code: HTTP status code.
        message: Human-readable error description.

    Returns:
        API Gateway-compatible response dict.
    """
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"error": message}),
    }