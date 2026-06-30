"""
Description: Unit tests for the Bedrock recipe generation half of
             processor_handler. Uses botocore stubbers to mock Bedrock and
             moto to mock DynamoDB. Tests cover JSON parsing, markdown fence
             stripping, fewer-than-2-recipe rejection, and DynamoDB writes.
Last Modified By: bvela
Created: 2026-06-30
Last Modified:
    2026-06-30 - File created: initial test suite for Bedrock + DynamoDB path.
"""

import io
import json
import os
import time

import boto3
import pytest
from botocore.stub import Stubber
from moto import mock_aws

os.environ.setdefault("IMAGE_BUCKET", "test-bucket")
os.environ.setdefault("RESULTS_TABLE", "test-table")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

from lambdas.processor.handler import (  # noqa: E402
    BEDROCK_MODEL_ID,
    _generate_recipes,
    _write_complete,
    _write_failed,
)

_TWO_RECIPES = {
    "recipes": [
        {
            "name": "Tomato Omelette",
            "ingredients": ["2 eggs", "1 tomato", "salt"],
            "instructions": ["Beat eggs.", "Dice tomato.", "Cook in pan.", "Serve hot."],
            "prep_time": "5 minutes",
            "cook_time": "10 minutes",
        },
        {
            "name": "Tomato Scramble",
            "ingredients": ["3 eggs", "1 tomato", "pepper"],
            "instructions": ["Beat eggs.", "Add tomato.", "Scramble.", "Season."],
            "prep_time": "5 minutes",
            "cook_time": "8 minutes",
        },
    ]
}


def _bedrock_response(payload: dict) -> dict:
    """Build a stubbed Bedrock InvokeModel response."""
    body_text = json.dumps({"content": [{"text": json.dumps(payload)}]})
    return {
        "body": io.BytesIO(body_text.encode()),
        "contentType": "application/json",
    }


def _bedrock_params(ingredients: list[str]) -> dict:
    """Expected params dict for the Bedrock stubber."""
    return {
        "modelId": BEDROCK_MODEL_ID,
        "contentType": "application/json",
        "accept": "application/json",
    }


@pytest.fixture()
def ddb_table():
    """Mocked DynamoDB table with the results schema."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName="test-table",
            KeySchema=[{"AttributeName": "requestId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "requestId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # Seed a PROCESSING record so update_item has a target item.
        table.put_item(Item={"requestId": "req-001", "status": "PROCESSING"})
        table.put_item(Item={"requestId": "req-fail", "status": "PROCESSING"})
        yield table


class TestGenerateRecipes:
    def _stub_bedrock(self, payload: dict):
        import lambdas.processor.handler as proc_module
        stubber = Stubber(proc_module._bedrock)
        response = _bedrock_response(payload)
        stubber.add_response("invoke_model", response)
        return stubber

    def test_returns_two_recipes(self):
        with self._stub_bedrock(_TWO_RECIPES):
            result = _generate_recipes(["Tomato", "Egg"], "req-001")
        assert len(result) == 2
        assert result[0]["name"] == "Tomato Omelette"

    def test_strips_markdown_code_fence(self):
        """Handles model output wrapped in ```json ... ``` fences."""
        fenced = f"```json\n{json.dumps(_TWO_RECIPES)}\n```"
        body_text = json.dumps({"content": [{"text": fenced}]})

        import lambdas.processor.handler as proc_module
        stubber = Stubber(proc_module._bedrock)
        stubber.add_response(
            "invoke_model",
            {"body": io.BytesIO(body_text.encode()), "contentType": "application/json"},
        )
        with stubber:
            result = _generate_recipes(["Cheese"], "req-002")
        assert len(result) == 2

    def test_raises_on_fewer_than_two_recipes(self):
        one_recipe = {"recipes": [_TWO_RECIPES["recipes"][0]]}
        with self._stub_bedrock(one_recipe):
            with pytest.raises(ValueError, match="expected 2"):
                _generate_recipes(["Tomato"], "req-003")

    def test_uses_fallback_ingredients_text_when_empty(self):
        """Empty ingredient list still produces a valid Bedrock call."""
        with self._stub_bedrock(_TWO_RECIPES):
            result = _generate_recipes([], "req-004")
        assert len(result) == 2


class TestDynamoDBWrites:
    def test_write_complete_sets_status_and_recipes(self, ddb_table):
        import lambdas.processor.handler as proc_module
        import unittest.mock as mock
        with mock.patch.object(proc_module._dynamodb, "Table", return_value=ddb_table):
            _write_complete("req-001", ["Tomato", "Egg"], _TWO_RECIPES["recipes"])

        item = ddb_table.get_item(Key={"requestId": "req-001"})["Item"]
        assert item["status"] == "COMPLETE"
        assert item["ingredients"] == ["Tomato", "Egg"]
        assert len(item["recipes"]) == 2
        assert "completed_at" in item

    def test_write_failed_sets_status_and_error(self, ddb_table):
        import lambdas.processor.handler as proc_module
        import unittest.mock as mock
        with mock.patch.object(proc_module._dynamodb, "Table", return_value=ddb_table):
            _write_failed("req-fail", "Rekognition API error")

        item = ddb_table.get_item(Key={"requestId": "req-fail"})["Item"]
        assert item["status"] == "FAILED"
        assert "Rekognition" in item["error_message"]
        assert "failed_at" in item
