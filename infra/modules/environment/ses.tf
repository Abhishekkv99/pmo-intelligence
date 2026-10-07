# -----------------------------------------------------------------------------
# SES: the environment's hostname as a sending domain (alerts), verified by
# Easy DKIM records in the delegated zone. A new account sends only to
# verified recipients (SES sandbox) until production access is requested.
# -----------------------------------------------------------------------------

resource "aws_sesv2_email_identity" "this" {
  email_identity = var.hostname
}

resource "aws_route53_record" "ses_dkim" {
  count = 3

  zone_id = aws_route53_zone.this.zone_id
  name    = "${aws_sesv2_email_identity.this.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.hostname}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_sesv2_email_identity.this.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}
