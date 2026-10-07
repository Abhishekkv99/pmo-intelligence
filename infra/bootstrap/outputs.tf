output "state_bucket_name" {
  description = "Bucket for every PMO stack's Terraform state (backend \"s3\" bucket)"
  value       = aws_s3_bucket.tfstate.bucket
}

output "state_bucket_arn" {
  description = "ARN of the state bucket"
  value       = aws_s3_bucket.tfstate.arn
}

output "state_bucket_region" {
  description = "Region of the state bucket (backend \"s3\" region)"
  value       = var.aws_region
}
