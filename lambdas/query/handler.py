"""
Description: Query Lambda for Snap & Cook. Entry point for the GET
             /recipes/{requestId} API route. Fetches the result record from
             DynamoDB and returns the current status. Statuses:
               PROCESSING            — image uploaded, Rekognition not yet done
               AWAITING_CONFIRMATION — ingredients detected, awaiting user review
               GENERATING            — user confirmed; Bedrock running
               COMPLETE              — recipes ready
               FAILED                — unrecoverable error
             Returns 200 + ingredients when AWAITING_CONFIRMATION so the
             frontend can render the verification UI without a second request.
             Returns 404 when the requestId is not found.
             Secrets must come from environment variables, never hard-coded.
Last Modified By: bvela
Created: 2026-07-01
Last Modified:
    2026-07-01 - File created: initial implementation.
    2026-07-01 - Expose ingredients on AWAITING_CONFIRMATION for the
                 ingredient verification UI.
    2026-07-01 - Removed unused TypeDeserializer import.
"""

import json
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb")

RESULTS_TABLE = os.environ["RESULTS_TABLE"]


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point — fetch a recipe result by requestId.

    Args:
        event: API Gateway proxy event. The requestId path parameter is
               expected at event['pathParameters']['requestId'].
        context: Lambda runtime context (unused).

    Returns:
        API Gateway-compatible response dict with statusCode and JSON body.
    """
    path_params = event.get("pathParameters") or {}
    request_id = path_params.get("requestId")

    if not request_id:
        return _response(400, {"error": "Missing requestId path parameter."})

    logger.info(json.dumps({"msg": "query started", "requestId": request_id}))

    table = _dynamodb.Table(RESULTS_TABLE)
    result = table.get_item(Key={"requestId": request_id})
    item = result.get("Item")

    if item is None:
        return _response(404, {"error": "Request not found.", "requestId": request_id})

    status = item.get("status", "UNKNOWN")

    if status == "COMPLETE":
        body = {
            "requestId": request_id,
            "status": "COMPLETE",
            "ingredients": item.get("ingredients", []),
            "recipes": item.get("recipes", []),
        }
    elif status == "AWAITING_CONFIRMATION":
        # Return detected ingredients so the frontend can render the
        # verification UI in a single poll rather than a separate request.
        body = {
            "requestId": request_id,
            "status": "AWAITING_CONFIRMATION",
            "ingredients": item.get("ingredients", []),
        }
    elif status == "FAILED":
        body = {
            "requestId": request_id,
            "status": "FAILED",
            "error": item.get("error_message", "Processing failed."),
        }
    else:
        # Covers PROCESSING, GENERATING, and any future intermediate states.
        body = {"requestId": request_id, "status": status}

    logger.info(json.dumps({"msg": "query complete", "requestId": request_id, "status": status}))
    return _response(200, body)


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway proxy response with CORS headers.

    Args:
        status_code: HTTP status code.
        body: Response payload to JSON-serialize.

    Returns:
        API Gateway-compatible response dict.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
