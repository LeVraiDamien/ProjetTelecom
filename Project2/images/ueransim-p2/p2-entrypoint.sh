#!/bin/bash
# Maintient la route 10.20.6.0/24 -> uesimtun0, puis lance l'entrypoint d'origine.
# uesimtun0 n'existe qu'une fois la session PDU établie (et il est recréé si la
# session tombe), d'où une boucle plutôt qu'une commande unique au démarrage.
P2_ROUTE="${P2_ROUTE:-10.20.6.0/24}"
P2_TUN="${P2_TUN:-uesimtun0}"

(
  while true; do
    if ip link show "$P2_TUN" >/dev/null 2>&1 \
       && ! ip route show "$P2_ROUTE" | grep -q "dev $P2_TUN"; then
      ip route replace "$P2_ROUTE" dev "$P2_TUN" \
        && echo "[p2-route] route $P2_ROUTE dev $P2_TUN installée"
    fi
    sleep 2
  done
) &

exec /entrypoint.sh "$@"
