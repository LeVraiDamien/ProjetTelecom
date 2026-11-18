#!/bin/bash
# baseline-test.sh
# Mesures de performance (Step 3, Scénario A) - réutilisable pour baseline ET dégradations.
# Usage : ./baseline-test.sh "Description de la condition testée"
# Prérequis : la topologie doit déjà être en place (./setup-topology.sh)

CONDITION="${1:-Baseline / aucun impairment}"

echo "===================================================="
echo "CONDITION : $CONDITION"
echo "Date : $(date)"
echo "===================================================="

echo ""
echo "=== 1. ICMP RTT (3 répétitions, 10 paquets chacune) ==="
for i in 1 2 3; do
  echo "-- Run $i --"
  sudo ip netns exec ue ping -c 10 10.0.5.2
  echo ""
done

echo ""
echo "=== 2. Débit TCP (iperf3, 3 répétitions, 5s chacune) ==="
for i in 1 2 3; do
  echo "-- Run $i --"
  sudo ip netns exec app-server iperf3 -s -1 &
  sleep 1
  sudo ip netns exec ue iperf3 -c 10.0.5.2 -t 5
  wait
  echo ""
done

echo ""
echo "=== 3. Débit UDP (iperf3, 3 répétitions, 5 Mbps, 5s chacune) ==="
for i in 1 2 3; do
  echo "-- Run $i --"
  sudo ip netns exec app-server iperf3 -s -1 &
  sleep 1
  sudo ip netns exec ue iperf3 -c 10.0.5.2 -u -b 5M -t 5
  wait
  echo ""
done

echo ""
echo "=== 4. Temps de réponse HTTP (10 requêtes successives) ==="
for i in $(seq 1 10); do
  sudo ip netns exec ue curl -s -o /dev/null -w "Requête $i: status=%{http_code} temps=%{time_total}s\n" http://10.0.5.2
done

echo ""
echo "===================================================="
echo "Test terminé - Condition : $CONDITION"
echo "===================================================="
