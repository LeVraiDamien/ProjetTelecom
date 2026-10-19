#!/usr/bin/env bash
# docker compose sur le cœur 5G + les ajouts du Projet 2.
# Se place dans le dossier openverso (le nom de projet et les chemins ./config en dépendent).
# Exemples : ./p2-compose.sh build      ./p2-compose.sh up -d upf ues1 scenario-b-nginx
set -euo pipefail

P2_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="${CORE_DIR:-$HOME/openverso-images/docs/open5gs-and-ueransim}"
export P2_DIR

cd "$CORE_DIR"
exec docker compose -p open5gs-and-ueransim \
  -f ngc.yaml -f gnb1.yaml \
  -f "$P2_DIR/compose/p2-core.yaml" \
  -f "$P2_DIR/compose/p2-scenario-a.yaml" \
  "$@"
