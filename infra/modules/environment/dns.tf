# -----------------------------------------------------------------------------
# DNS and TLS. The hosted zone for the environment's hostname lives in this
# account; whoever manages itcapp.ai delegates the name to its name servers
# (one NS record). Until then the certificate cannot validate, so the first
# apply targets the zone alone (docs/DEPLOYMENT.md).
# -----------------------------------------------------------------------------

resource "aws_route53_zone" "this" {
  name    = var.hostname
  comment = "${local.name}: delegated from itcapp.ai"

  # Recreating the zone changes its name servers and silently breaks the
  # delegation held outside this account
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_acm_certificate" "this" {
  domain_name       = var.hostname
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for o in aws_acm_certificate.this.domain_validation_options : o.domain_name => o
  }

  zone_id         = aws_route53_zone.this.zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

# Waits until the certificate is issued (needs the delegation in place)
resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# The hostname is the zone apex, so an alias A record (a CNAME cannot sit there)
resource "aws_route53_record" "app" {
  zone_id = aws_route53_zone.this.zone_id
  name    = var.hostname
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}
