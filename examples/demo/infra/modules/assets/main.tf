variable "origin_id" {
  type = string
}

resource "aws_s3_bucket" "this" {
  bucket = "demo-frontend-assets"

  tags = {
    OriginId = var.origin_id
  }
}

output "domain" {
  value = aws_s3_bucket.this.bucket_regional_domain_name
}
