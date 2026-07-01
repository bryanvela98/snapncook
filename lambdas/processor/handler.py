"""
Description: Processor Lambda for Snap & Cook. Triggered by SQS event source
             mapping. Handles two phases keyed by the 'phase' field in the
             message body:

               phase='detect'  (default): Fetches the uploaded image from S3,
                 calls Rekognition DetectLabels, filters food-relevant labels,
                 and writes AWAITING_CONFIRMATION + ingredients to DynamoDB.
                 The frontend then shows an ingredient verification UI.

               phase='generate': Reads confirmed ingredients and user
                 preferences from DynamoDB, calls Bedrock to generate recipes
                 (recipe_count, max_prep_time, dietary constraints applied),
                 and writes COMPLETE to DynamoDB.

             On any error the record is set to FAILED and the exception is
             re-raised so SQS retries up to maxReceiveCount=3 before routing
             to the DLQ. Secrets come from environment variables only.
Last Modified By: bvela
Created: 2026-06-30
Last Modified:
    2026-06-30 - File created: SQS trigger, Rekognition detection, Bedrock
                 recipe generation, DynamoDB write.
    2026-07-01 - Split into detect/generate phases to support ingredient
                 verification step and user recipe preferences.
"""

import json
import logging
import os
import time
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")
_rekognition = boto3.client("rekognition")
_bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
_dynamodb = boto3.resource("dynamodb")

IMAGE_BUCKET = os.environ["IMAGE_BUCKET"]
RESULTS_TABLE = os.environ["RESULTS_TABLE"]
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

_MIN_CONFIDENCE = 70.0
_FOOD_PARENTS = {"Food", "Fruit", "Vegetable", "Dish", "Meal", "Produce", "Seafood", "Meat"}


# =============================================================================
# Entry point
# =============================================================================

def handler(event: dict[str, Any], context: Any) -> None:
    """Lambda entry point — dispatch SQS records to the correct processing phase.

    Args:
        event: SQS event with a 'Records' list.
        context: Lambda runtime context (unused).
    """
    for record in event.get("Records", []):
        _process_record(record)


def _process_record(record: dict[str, Any]) -> None:
    """Route a single SQS message to detect or generate phase.

    Args:
        record: A single SQS event record.
    """
    body = json.loads(record["body"])
    request_id = body["requestId"]
    phase = body.get("phase", "detect")

    logger.info(json.dumps({"msg": "processing started", "requestId": request_id, "phase": phase}))

    if phase == "detect":
        _run_detection(request_id, body["s3_key"])
    elif phase == "generate":
        _run_generation(request_id)
    else:
        logger.warning(json.dumps({"msg": "unknown phase", "requestId": request_id, "phase": phase}))


# =============================================================================
# Phase 1 — Rekognition detection
# =============================================================================

def _run_detection(request_id: str, s3_key: str) -> None:
    """Detect ingredients from the uploaded image and write AWAITING_CONFIRMATION.

    Args:
        request_id: UUID identifying this request.
        s3_key: S3 object key of the uploaded image.
    """
    try:
        ingredients = _detect_ingredients(s3_key, request_id)
        _write_awaiting_confirmation(request_id, ingredients)
        logger.info(json.dumps({
            "msg": "detection complete",
            "requestId": request_id,
            "ingredient_count": len(ingredients),
            "ingredients": ingredients,
        }))
    except Exception as exc:
        logger.error(json.dumps({"msg": "detection failed", "requestId": request_id, "error": str(exc)}))
        _write_failed(request_id, str(exc))
        raise


def _detect_ingredients(s3_key: str, request_id: str) -> list[str]:
    """Call Rekognition DetectLabels and return food-relevant label names.

    Args:
        s3_key: S3 key of the uploaded image in IMAGE_BUCKET.
        request_id: UUID for structured logging.

    Returns:
        List of ingredient name strings (may be empty if no food detected).

    Raises:
        Exception: Propagated from Rekognition on API errors.
    """
    response = _rekognition.detect_labels(
        Image={"S3Object": {"Bucket": IMAGE_BUCKET, "Name": s3_key}},
        MaxLabels=30,
        MinConfidence=_MIN_CONFIDENCE,
    )
    return _filter_food_labels(response.get("Labels", []))


def _filter_food_labels(labels: list[dict[str, Any]]) -> list[str]:
    """Keep only food-relevant labels by inspecting their parent categories.

    Args:
        labels: Raw Labels list from Rekognition DetectLabels response.

    Returns:
        Deduplicated list of food-relevant label name strings.
    """
    seen: set[str] = set()
    result: list[str] = []
    for label in labels:
        name = label.get("Name", "")
        parents = {p.get("Name", "") for p in label.get("Parents", [])}
        if (name in _FOOD_PARENTS or bool(parents & _FOOD_PARENTS)) and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _write_awaiting_confirmation(request_id: str, ingredients: list[str]) -> None:
    """Write detected ingredients and set status to AWAITING_CONFIRMATION.

    Args:
        request_id: UUID identifying the request.
        ingredients: Detected ingredient names from Rekognition.
    """
    table = _dynamodb.Table(RESULTS_TABLE)
    table.update_item(
        Key={"requestId": request_id},
        UpdateExpression="SET #s = :s, ingredients = :i, detected_at = :t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "AWAITING_CONFIRMATION",
            ":i": ingredients,
            ":t": int(time.time()),
        },
    )


# =============================================================================
# Phase 2 — Bedrock recipe generation
# =============================================================================

def _run_generation(request_id: str) -> None:
    """Generate recipes from confirmed ingredients + preferences, write COMPLETE.

    Args:
        request_id: UUID identifying this request.
    """
    try:
        record = _read_record(request_id)
        # The confirm Lambda writes confirmed_ingredients; fall back to the
        # original Rekognition list if somehow missing.
        ingredients = record.get("confirmed_ingredients") or record.get("ingredients", [])
        preferences = record.get("preferences") or {}

        recipes = _generate_recipes(ingredients, preferences, request_id)
        _write_complete(request_id, ingredients, recipes)
        logger.info(json.dumps({
            "msg": "generation complete",
            "requestId": request_id,
            "recipe_count": len(recipes),
        }))
    except Exception as exc:
        logger.error(json.dumps({"msg": "generation failed", "requestId": request_id, "error": str(exc)}))
        _write_failed(request_id, str(exc))
        raise


def _read_record(request_id: str) -> dict[str, Any]:
    """Fetch the DynamoDB record for a request.

    Args:
        request_id: UUID identifying the request.

    Returns:
        DynamoDB item dict.

    Raises:
        ValueError: If the record is not found.
    """
    table = _dynamodb.Table(RESULTS_TABLE)
    result = table.get_item(Key={"requestId": request_id})
    item = result.get("Item")
    if item is None:
        raise ValueError(f"Record not found for requestId={request_id}")
    return item


def _generate_recipes(
    ingredients: list[str],
    preferences: dict[str, Any],
    request_id: str,
) -> list[dict[str, Any]]:
    """Call Bedrock to generate recipes respecting user preferences.

    Args:
        ingredients: Confirmed ingredient names.
        preferences: Dict with optional keys recipe_count (int, 1–5),
                     max_prep_time (str minutes), dietary (list[str]).
        request_id: UUID for structured logging.

    Returns:
        List of recipe dicts (name, ingredients, instructions, prep_time, cook_time).

    Raises:
        ValueError: If Bedrock returns malformed JSON or fewer recipes than requested.
        Exception: Propagated from Bedrock on API errors.
    """
    recipe_count = max(1, min(5, int(preferences.get("recipe_count", 2))))
    max_prep_time = preferences.get("max_prep_time")
    dietary = preferences.get("dietary") or []

    ingredient_list = ", ".join(ingredients) if ingredients else "assorted ingredients"

    constraints: list[str] = []
    if max_prep_time:
        constraints.append(
            f"Total preparation + cooking time must be {max_prep_time} minutes or less"
        )
    if dietary:
        constraints.append(f"Dietary requirements: {', '.join(dietary)}")
    constraints_block = (
        "\n".join(f"- {c}" for c in constraints) if constraints else "- None"
    )

    prompt = f"""You are a professional chef. Given these ingredients: {ingredient_list}

Generate exactly {recipe_count} recipe(s).

Constraints:
{constraints_block}

Return ONLY the following JSON object with no markdown fences, no explanation:
{{
  "recipes": [
    {{
      "name": "string",
      "ingredients": ["string"],
      "instructions": ["string"],
      "prep_time": "string",
      "cook_time": "string"
    }}
  ]
}}

Rules:
- Provide EXACTLY {recipe_count} recipe(s) in the "recipes" array.
- Each recipe must have at least 4 cooking instruction steps.
- Add common pantry staples (salt, pepper, oil, garlic, etc.) as needed.
- Respect all constraints above strictly."""

    body = json.dumps({
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"max_new_tokens": 2048, "temperature": 0.3},
    })

    response = _bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    raw = json.loads(response["body"].read())
    text = raw["output"]["message"]["content"][0]["text"].strip()

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    parsed = json.loads(text)
    recipes = parsed.get("recipes", [])

    if len(recipes) < recipe_count:
        raise ValueError(
            f"Bedrock returned {len(recipes)} recipe(s); expected {recipe_count}."
        )

    logger.info(json.dumps({
        "msg": "bedrock complete",
        "requestId": request_id,
        "recipe_count": len(recipes),
        "recipe_names": [r.get("name") for r in recipes],
    }))

    return recipes


# =============================================================================
# Shared DynamoDB helpers
# =============================================================================

def _write_complete(
    request_id: str,
    ingredients: list[str],
    recipes: list[dict[str, Any]],
) -> None:
    """Update the DynamoDB record to COMPLETE.

    Args:
        request_id: UUID identifying the request.
        ingredients: Confirmed ingredient names.
        recipes: Generated recipe objects from Bedrock.
    """
    table = _dynamodb.Table(RESULTS_TABLE)
    table.update_item(
        Key={"requestId": request_id},
        UpdateExpression=(
            "SET #s = :s, ingredients = :i, recipes = :r, completed_at = :t"
        ),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "COMPLETE",
            ":i": ingredients,
            ":r": recipes,
            ":t": int(time.time()),
        },
    )


def _write_failed(request_id: str, error_message: str) -> None:
    """Update the DynamoDB record to FAILED.

    Args:
        request_id: UUID identifying the request.
        error_message: Human-readable description of the failure.
    """
    table = _dynamodb.Table(RESULTS_TABLE)
    table.update_item(
        Key={"requestId": request_id},
        UpdateExpression="SET #s = :s, error_message = :e, failed_at = :t",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "FAILED",
            ":e": error_message,
            ":t": int(time.time()),
        },
    )