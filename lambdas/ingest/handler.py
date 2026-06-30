"""
Description: Ingest Lambda for Snap & Cook. Entry point for the POST /analyze
             API route. Accepts a base64-encoded image from API Gateway,
             generates a unique requestId, stores the raw image in S3, writes
             an initial PROCESSING record to DynamoDB, and publishes a job
             message to SQS. Returns 202 immediately so the client can begin
             polling; all ML processing happens asynchronously downstream.
             Secrets must come from environment variables, never hard-coded.
Last Modified By: bvela
Created: 2026-06-30
Last Modified:
    2026-06-30 - File created: initial implementation.
"""

import base64
import json
import logging
import os
import time
import uuid
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")
_dynamodb = boto3.resource("dynamodb")
_sqs = boto3.client("sqs")

IMAGE_BUCKET = os.environ["IMAGE_BUCKET"]
RESULTS_TABLE = os.environ["RESULTS_TABLE"]
JOB_QUEUE_URL = os.environ["JOB_QUEUE_URL"]

# Records expire from DynamoDB after this many seconds (7 days).
_TTL_SECONDS = 7 * 24 * 60 * 60


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point — receive an image upload and enqueue a processing job.

    Args:
        event: API Gateway proxy event. Must contain a base64-encoded image body
               and optionally a 'content-type' header and 'filename' query param.
        context: Lambda runtime context (unused).

    Returns:
        API Gateway-compatible response dict with statusCode and JSON body.
    """
    logger.info(json.dumps({"msg": "ingest started", "requestId": None}))

    body = event.get("body")
    if not body:
        return _error(400, "Request body is required.")

    # API Gateway sets isBase64Encoded when binary media types are configured.
    is_b64 = event.get("isBase64Encoded", False)
    try:
        image_bytes = base64.b64decode(body) if is_b64 else body.encode()
    except Exception:
        return _error(400, "Could not decode request body.")

    if not image_bytes:
        return _error(400, "Image body is empty.")

    content_type = _extract_content_type(event)
    filename = _extract_filename(event, content_type)
    request_id = str(uuid.uuid4())
    s3_key = f"uploads/{request_id}/{filename}"

    try:
        _store_image(s3_key, image_bytes, content_type)
        _write_processing_record(request_id, s3_key)
        _publish_job(request_id, s3_key)
    except Exception as exc:
        logger.error(json.dumps({"msg": "ingest failed", "requestId": request_id, "error": str(exc)}))
        return _error(500, "Failed to process request.")

    logger.info(json.dumps({"msg": "ingest complete", "requestId": request_id, "s3_key": s3_key}))
    return {
        "statusCode": 202,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"requestId": request_id}),
    }


def _store_image(s3_key: str, image_bytes: bytes, content_type: str) -> None:
    """Upload the raw image bytes to the S3 image bucket.

    Args:
        s3_key: Destination key in the image bucket.
        image_bytes: Raw binary image data.
        content_type: MIME type of the image.
    """
    _s3.put_object(
        Bucket=IMAGE_BUCKET,
        Key=s3_key,
        Body=image_bytes,
        ContentType=content_type,
    )


def _write_processing_record(request_id: str, s3_key: str) -> None:
    """Create the initial PROCESSING record in DynamoDB.

    Args:
        request_id: UUID identifying this recipe request.
        s3_key: S3 key where the uploaded image is stored.
    """
    table = _dynamodb.Table(RESULTS_TABLE)
    table.put_item(
        Item={
            "requestId": request_id,
            "status": "PROCESSING",
            "s3_key": s3_key,
            "created_at": int(time.time()),
            "ttl": int(time.time()) + _TTL_SECONDS,
        }
    )


def _publish_job(request_id: str, s3_key: str) -> None:
    """Publish a job message to the SQS queue for async processing.

    Args:
        request_id: UUID identifying this recipe request.
        s3_key: S3 key where the uploaded image is stored.
    """
    _sqs.send_message(
        QueueUrl=JOB_QUEUE_URL,
        MessageBody=json.dumps({"requestId": request_id, "s3_key": s3_key}),
        MessageAttributes={
            "requestId": {"StringValue": request_id, "DataType": "String"}
        },
    )


def _extract_content_type(event: dict[str, Any]) -> str:
    """Read the Content-Type header from the API Gateway event.

    Args:
        event: API Gateway proxy event.

    Returns:
        Content-Type string, defaulting to 'image/jpeg'.
    """
    headers = event.get("headers") or {}
    # API Gateway normalises header names to lowercase.
    return headers.get("content-type", headers.get("Content-Type", "image/jpeg"))


def _extract_filename(event: dict[str, Any], content_type: str) -> str:
    """Derive a filename from query parameters or the content type.

    Args:
        event: API Gateway proxy event.
        content_type: MIME type of the uploaded image.

    Returns:
        A safe filename string for use in the S3 key.
    """
    params = event.get("queryStringParameters") or {}
    if params.get("filename"):
        return params["filename"]
    ext = content_type.split("/")[-1].split(";")[0].strip() or "jpg"
    return f"image.{ext}"


def _error(status_code: int, message: str) -> dict[str, Any]:
    """Build an API Gateway error response.

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
