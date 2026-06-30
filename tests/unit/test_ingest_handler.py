"""
Description: Unit tests for the ingest_handler Lambda. Uses moto to mock
             AWS services (S3, DynamoDB, SQS) so no real AWS calls are made.
             Tests cover the happy path, missing body, and the 202 contract.
Last Modified By: bvela
Created: 2026-06-30
Last Modified:
    2026-06-30 - File created: initial test suite.
"""

import base64
import json
import os
import time

import boto3
import pytest
from moto import mock_aws

# Environment variables must be set before the handler module is imported so
# the module-level boto3 clients pick up the mocked endpoints.
os.environ["IMAGE_BUCKET"] = "test-image-bucket"
os.environ["RESULTS_TABLE"] = "test-results-table"
os.environ["JOB_QUEUE_URL"] = "https://sqs.us-east-1.amazonaws.com/123456789012/test-queue"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"

from lambdas.ingest.handler import handler  # noqa: E402


@pytest.fixture()
def aws_resources():
    """Spin up mocked S3 bucket, DynamoDB table, and SQS queue."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-image-bucket")

        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="test-results-table",
            KeySchema=[{"AttributeName": "requestId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "requestId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        sqs = boto3.client("sqs", region_name="us-east-1")
        response = sqs.create_queue(QueueName="test-queue")
        os.environ["JOB_QUEUE_URL"] = response["QueueUrl"]

        yield {"s3": s3, "ddb": ddb, "sqs": sqs}


def _b64_event(image_bytes: bytes = b"fake-image-data", filename: str | None = None) -> dict:
    """Build a minimal API Gateway proxy event with a base64-encoded body."""
    params = {"filename": filename} if filename else {}
    return {
        "body": base64.b64encode(image_bytes).decode(),
        "isBase64Encoded": True,
        "headers": {"content-type": "image/jpeg"},
        "queryStringParameters": params,
    }


class TestIngestHandler:
    def test_happy_path_returns_202_with_request_id(self, aws_resources):
        """202 response with a UUID requestId on valid input."""
        response = handler(_b64_event(), context=None)

        assert response["statusCode"] == 202
        body = json.loads(response["body"])
        assert "requestId" in body
        assert len(body["requestId"]) == 36  # UUID format

    def test_image_stored_in_s3(self, aws_resources):
        """Uploaded image bytes land in S3 under uploads/<requestId>/."""
        response = handler(_b64_event(b"real-image-bytes"), context=None)
        request_id = json.loads(response["body"])["requestId"]

        s3 = aws_resources["s3"]
        objects = s3.list_objects_v2(Bucket="test-image-bucket", Prefix=f"uploads/{request_id}/")
        assert objects["KeyCount"] == 1

    def test_dynamodb_record_written_with_processing_status(self, aws_resources):
        """DynamoDB record created with status PROCESSING and correct fields."""
        response = handler(_b64_event(), context=None)
        request_id = json.loads(response["body"])["requestId"]

        table = aws_resources["ddb"].Table("test-results-table")
        item = table.get_item(Key={"requestId": request_id})["Item"]

        assert item["status"] == "PROCESSING"
        assert item["requestId"] == request_id
        assert "s3_key" in item
        assert "created_at" in item
        assert item["ttl"] > int(time.time())

    def test_sqs_message_published(self, aws_resources):
        """A job message with requestId and s3_key is published to SQS."""
        response = handler(_b64_event(), context=None)
        request_id = json.loads(response["body"])["requestId"]

        sqs = aws_resources["sqs"]
        messages = sqs.receive_message(
            QueueUrl=os.environ["JOB_QUEUE_URL"], MaxNumberOfMessages=1
        ).get("Messages", [])

        assert len(messages) == 1
        msg = json.loads(messages[0]["Body"])
        assert msg["requestId"] == request_id
        assert msg["s3_key"].startswith(f"uploads/{request_id}/")

    def test_missing_body_returns_400(self, aws_resources):
        """Empty body returns 400 with an error message."""
        response = handler({"body": None, "isBase64Encoded": False, "headers": {}}, context=None)
        assert response["statusCode"] == 400
        assert "error" in json.loads(response["body"])

    def test_empty_body_returns_400(self, aws_resources):
        """Body present but zero bytes returns 400."""
        event = {
            "body": base64.b64encode(b"").decode(),
            "isBase64Encoded": True,
            "headers": {"content-type": "image/jpeg"},
            "queryStringParameters": {},
        }
        response = handler(event, context=None)
        assert response["statusCode"] == 400

    def test_custom_filename_used_in_s3_key(self, aws_resources):
        """Filename query param is reflected in the S3 key."""
        response = handler(_b64_event(filename="fridge.png"), context=None)
        request_id = json.loads(response["body"])["requestId"]

        s3 = aws_resources["s3"]
        objects = s3.list_objects_v2(Bucket="test-image-bucket", Prefix=f"uploads/{request_id}/")
        key = objects["Contents"][0]["Key"]
        assert key.endswith("fridge.png")

    def test_cors_header_present(self, aws_resources):
        """CORS header is set so the browser frontend can call the API."""
        response = handler(_b64_event(), context=None)
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"
