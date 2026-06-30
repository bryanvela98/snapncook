# =============================================================================
# Description: Storage module for Snap & Cook. Provisions the S3 bucket that
#              holds uploaded ingredient images and the DynamoDB table that
#              stores request results. The image bucket is private (no public
#              access) and versioned; the table is on-demand with a TTL
#              attribute so old request records expire automatically (cost
#              control + the Reliability/Cost pillars).
# Last Modified By: bvela
# Created: 2026-06-30
# Last Modified:
#     2026-06-30 - File created: S3 image bucket + DynamoDB results table.
# =============================================================================

# ---------------------------------------------------------------------------
# S3 — uploaded ingredient images
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "images" {
  bucket = "${var.project_name}-images-${var.account_id}"
}

# Versioning guards against accidental overwrite/delete of an upload mid-process.
resource "aws_s3_bucket_versioning" "images" {
  bucket = aws_s3_bucket.images.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "images" {
  bucket = aws_s3_bucket.images.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Images are private — only the Lambdas (via IAM) ever read/write them.
resource "aws_s3_bucket_public_access_block" "images" {
  bucket                  = aws_s3_bucket.images.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Expire raw uploads after the retention window — we only need the image long
# enough to process it; the recipe result lives in DynamoDB.
resource "aws_s3_bucket_lifecycle_configuration" "images" {
  bucket = aws_s3_bucket.images.id

  rule {
    id     = "expire-uploads"
    status = "Enabled"

    filter {
      prefix = "uploads/"
    }

    expiration {
      days = var.image_retention_days
    }
  }
}

# ---------------------------------------------------------------------------
# DynamoDB — request results
# ---------------------------------------------------------------------------

# Single-table keyed by requestId. Only the partition key is declared here;
# non-key attributes (status, ingredients, recipes, created_at) are schemaless
# and written by the Lambdas at runtime.
resource "aws_dynamodb_table" "results" {
  name         = "${var.project_name}-results"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "requestId"

  attribute {
    name = "requestId"
    type = "S"
  }

  # Records self-expire after the TTL timestamp written by the Lambdas.
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }
}
