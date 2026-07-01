# =============================================================================
# Description: Frontend module for Snap & Cook. Provisions an S3 bucket
#              configured for static website hosting, uploads the frontend
#              bundle (index.html, app.js, styles.css), and generates config.js
#              at deploy time with the live API endpoint injected so the browser
#              app never contains a hardcoded URL.
#              Note: CORS on API Gateway is already configured with allow_origins
#              = ["*"] in the api module — no additional change is needed here.
# Last Modified By: bvela
# Created: 2026-07-01
# Last Modified:
#     2026-07-01 - File created: S3 static site + frontend file uploads.
# =============================================================================

# ---------------------------------------------------------------------------
# S3 bucket — static website hosting
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend-${var.account_id}"
}

# The frontend bucket must allow public reads so browsers can load the site.
# This is intentionally different from the private images bucket.
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }

  # Route all paths to index.html so ?id= deep-links work correctly.
  error_document {
    key = "index.html"
  }
}

# Public read policy — must be applied after the public access block is lifted.
resource "aws_s3_bucket_policy" "frontend" {
  depends_on = [aws_s3_bucket_public_access_block.frontend]
  bucket     = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.frontend.arn}/*"
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Frontend file uploads
# ---------------------------------------------------------------------------

resource "aws_s3_object" "index_html" {
  depends_on   = [aws_s3_bucket_policy.frontend]
  bucket       = aws_s3_bucket.frontend.id
  key          = "index.html"
  source       = "${path.root}/../frontend/index.html"
  content_type = "text/html"
  # Rebuilt whenever the source file changes.
  etag = filemd5("${path.root}/../frontend/index.html")
}

resource "aws_s3_object" "app_js" {
  depends_on   = [aws_s3_bucket_policy.frontend]
  bucket       = aws_s3_bucket.frontend.id
  key          = "app.js"
  source       = "${path.root}/../frontend/app.js"
  content_type = "application/javascript"
  etag         = filemd5("${path.root}/../frontend/app.js")
}

resource "aws_s3_object" "styles_css" {
  depends_on   = [aws_s3_bucket_policy.frontend]
  bucket       = aws_s3_bucket.frontend.id
  key          = "styles.css"
  source       = "${path.root}/../frontend/styles.css"
  content_type = "text/css"
  etag         = filemd5("${path.root}/../frontend/styles.css")
}

# config.js is generated at deploy time with the live API endpoint.
# The placeholder frontend/config.js is NOT uploaded — this resource owns it.
resource "aws_s3_object" "config_js" {
  depends_on   = [aws_s3_bucket_policy.frontend]
  bucket       = aws_s3_bucket.frontend.id
  key          = "config.js"
  content      = "window.API_BASE_URL = \"${var.api_endpoint}\";"
  content_type = "application/javascript"
  etag         = md5("window.API_BASE_URL = \"${var.api_endpoint}\";")
}