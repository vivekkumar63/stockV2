#!/usr/bin/env bash
# Tail backend logs
set -euo pipefail
exec journalctl -u stockv2-backend -f --no-pager
