# MarketPilot AWS infrastructure — entry point.
#
# This file is intentionally thin: every concern lives in its own file
# (networking.tf, security.tf, ecr.tf, ecs.tf, alb.tf, rds.tf,
# redis.tf, secrets.tf, cloudwatch.tf, iam.tf, route53.tf, acm.tf),
# matching the layout documented in docs/infrastructure.md. State is
# local by default and gitignored — see the "State" section of that
# document before sharing this stack across operators or CI.
