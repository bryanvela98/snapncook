"""
Description: Processor Lambda for Snap & Cook. Triggered by SQS event source
             mapping. For each job message, fetches the uploaded image from S3,
             calls Rekognition DetectLabels to identify ingredient candidates,
             then calls Bedrock (Claude 3 Haiku) to generate 2 complete recipe
             suggestions. Writes the final result (or a FAILED status on error)
             to DynamoDB. Designed to be idempotent: re-processing the same
             requestId overwrites the existing record rather than duplicating.
             Secrets must come from environment variables, never hard-coded.
Last Modified By: bvela
Created: 2026-06-30
Last Modified:
    2026-06-30 - File created: SQS trigger, Rekognition detection, Bedrock
                 recipe generation, DynamoDB write.
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

# Rekognition labels with confidence below this threshold are discarded.
_MIN_CONFIDENCE = 70.0

# Parent categories that indicate a label is food-related.
_FOOD_PARENTS = {"Food", "Fruit", "Vegetable", "Dish", "Meal", "Produce", "Seafood", "Meat"}

BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
)


def handler(event: dict[str, Any], context: Any) -> None:
    """Lambda entry point — process one SQS batch and generate recipes.

    SQS event source mapping delivers records in batches (batch size = 1 here).
    Each record body contains { requestId, s3_key }.

    Args:
        event: SQS event with a 'Records' list.
        context: Lambda runtime context (unused).
    """
    for record in event.get("Records", []):
        _process_record(record)


def _process_record(record: dict[str, Any]) -> None:
    """Process a single SQS message end-to-end.

    Args:
        record: A single SQS event record.
    """
    body = json.loads(record["body"])
    request_id = body["requestId"]
    s3_key = body["s3_key"]

    logger.info(json.dumps({"msg": "processing started", "requestId": request_id, "s3_key": s3_key}))

    try:
        ingredients = _detect_ingredients(s3_key, request_id)
        recipes = _generate_recipes(ingredients, request_id)
        _write_complete(request_id, ingredients, recipes)
        logger.info(json.dumps({
            "msg": "processing complete",
            "requestId": request_id,
            "ingredient_count": len(ingredients),
            "recipe_count": len(recipes),
        }))
    except Exception as exc:
        logger.error(json.dumps({"msg": "processing failed", "requestId": request_id, "error": str(exc)}))
        _write_failed(request_id, str(exc))
        # Re-raise so SQS treats this as a failed receive and retries
        # (up to maxReceiveCount=3, then routes to the DLQ).
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

    labels = response.get("Labels", [])
    ingredients = _filter_food_labels(labels)

    logger.info(json.dumps({
        "msg": "rekognition complete",
        "requestId": request_id,
        "total_labels": len(labels),
        "food_labels": len(ingredients),
        "ingredients": ingredients,
    }))

    return ingredients


def _filter_food_labels(labels: list[dict[str, Any]]) -> list[str]:
    """Keep only food-relevant labels by inspecting their parent categories.

    A label is kept if it has at least one parent in _FOOD_PARENTS, or if
    its own name is in _FOOD_PARENTS. This prevents furniture, people, and
    kitchen objects from appearing in the ingredient list.

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

        is_food = name in _FOOD_PARENTS or bool(parents & _FOOD_PARENTS)
        if is_food and name not in seen:
            seen.add(name)
            result.append(name)

    return result


def _generate_recipes(ingredients: list[str], request_id: str) -> list[dict[str, Any]]:
    """Call Bedrock Claude 3 Haiku to generate 2 recipe suggestions.

    Args:
        ingredients: List of detected ingredient names.
        request_id: UUID for structured logging.

    Returns:
        List of recipe dicts, each with keys: name, ingredients,
        instructions, prep_time, cook_time.

    Raises:
        ValueError: If Bedrock returns malformed JSON or fewer than 2 recipes.
        Exception: Propagated from Bedrock on API errors.
    """
    ingredient_list = ", ".join(ingredients) if ingredients else "assorted ingredients"

    prompt = f"""You are a professional chef. Given these detected ingredients: {ingredient_list}

Return a JSON object with EXACTLY this structure and nothing else — no markdown, no explanation:
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

Provide EXACTLY 2 recipe options. Add common pantry staples (salt, pepper, oil, garlic, etc.) as needed. Each recipe must have at least 4 cooking instruction steps."""

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    })

    response = _bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    raw = json.loads(response["body"].read())
    text = raw["content"][0]["text"].strip()

    # Strip markdown code fences if the model added them despite instructions.
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    parsed = json.loads(text)
    recipes = parsed.get("recipes", [])

    if len(recipes) < 2:
        raise ValueError(f"Bedrock returned {len(recipes)} recipe(s); expected 2.")

    logger.info(json.dumps({
        "msg": "bedrock complete",
        "requestId": request_id,
        "recipe_count": len(recipes),
        "recipe_names": [r.get("name") for r in recipes],
    }))

    return recipes


def _write_complete(
    request_id: str,
    ingredients: list[str],
    recipes: list[dict[str, Any]],
) -> None:
    """Update the DynamoDB record to COMPLETE with ingredients and recipes.

    Args:
        request_id: UUID identifying the request.
        ingredients: Detected ingredient names from Rekognition.
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
    """Update the DynamoDB record to FAILED with an error message.

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
