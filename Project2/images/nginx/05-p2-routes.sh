#!/bin/sh
# Route de retour vers les UE : sans NAT sur l'UPF, Nginx voit l'IP réelle de l'UE
# (10.45.0.x) et doit renvoyer la réponse à l'UPF, pas à la passerelle Docker.
set -e
UE_SUBNET="${UE_SUBNET:-10.45.0.0/16}"
UPF_N6_IP="${UPF_N6_IP:-10.20.6.10}"

ip route replace "$UE_SUBNET" via "$UPF_N6_IP"
echo "[p2-route] route $UE_SUBNET via $UPF_N6_IP installée"
