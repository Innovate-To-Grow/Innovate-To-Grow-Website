# Deployment Guide

## Guides

- [Local development](local.md)
- [Production architecture](production.md)
- [CI and delivery pipeline](ci-cd.md)

## Principles

- Backend and frontend deploy independently but share environment assumptions.
- CI must validate linting, builds, tests, migrations, and structure rules before deployment.
- Production configuration stays environment-driven and should not require code edits per environment.
