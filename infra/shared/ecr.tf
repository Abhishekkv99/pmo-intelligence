# -----------------------------------------------------------------------------
# ECR: one repository per image, shared by every environment. CI pushes
# sha-<commit> plus an environment tag (staging-latest).
# -----------------------------------------------------------------------------

locals {
  ecr_repositories = toset(["backend", "frontend"])

  ecr_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after ${var.ecr_untagged_expiry_days} days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.ecr_untagged_expiry_days
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep only the last ${var.ecr_tagged_images_kept} tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["latest", "sha-", "staging-"]
          countType     = "imageCountMoreThan"
          countNumber   = var.ecr_tagged_images_kept
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

resource "aws_ecr_repository" "app" {
  for_each = local.ecr_repositories

  name = "${var.project_name}-${each.key}"

  # staging-latest is moved on every deploy
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  for_each = local.ecr_repositories

  repository = aws_ecr_repository.app[each.key].name
  policy     = local.ecr_lifecycle_policy
}
