#!/bin/bash
# setup-topology.sh
# Recrée la topologie complète du Scénario A : ue - access - core - app - host
# A relancer à chaque fois que WSL redémarre (les namespaces ne survivent pas à un reboot).

set -e

echo "=== Nettoyage (au cas où des restes traineraient) ==="
for ns in ue access core app; do
  sudo ip netns del "$ns" 2>/dev/null || true
done
sudo ip link del veth-host 2>/dev/null || true

echo "=== Création des namespaces ==="
sudo ip netns add ue
sudo ip netns add access
sudo ip netns add core
sudo ip netns add app

echo "=== Création des paires veth ==="
sudo ip link add veth-ue type veth peer name veth-acc-in
sudo ip link add veth-acc-out type veth peer name veth-core-in
sudo ip link add veth-core-out type veth peer name veth-app
sudo ip link add veth-app2 type veth peer name veth-host

echo "=== Attribution des interfaces aux namespaces ==="
sudo ip link set veth-ue netns ue
sudo ip link set veth-acc-in netns access
sudo ip link set veth-acc-out netns access
sudo ip link set veth-core-in netns core
sudo ip link set veth-core-out netns core
sudo ip link set veth-app netns app
sudo ip link set veth-app2 netns app
# veth-host reste dans le namespace racine (l'hôte), c'est notre pont vers Docker

echo "=== Activation des interfaces (loopback + veth) ==="
sudo ip netns exec ue ip link set lo up
sudo ip netns exec ue ip link set veth-ue up

sudo ip netns exec access ip link set lo up
sudo ip netns exec access ip link set veth-acc-in up
sudo ip netns exec access ip link set veth-acc-out up

sudo ip netns exec core ip link set lo up
sudo ip netns exec core ip link set veth-core-in up
sudo ip netns exec core ip link set veth-core-out up

sudo ip netns exec app ip link set lo up
sudo ip netns exec app ip link set veth-app up
sudo ip netns exec app ip link set veth-app2 up

sudo ip link set veth-host up

echo "=== Adressage IP ==="
sudo ip netns exec ue ip addr add 10.0.1.1/30 dev veth-ue

sudo ip netns exec access ip addr add 10.0.1.2/30 dev veth-acc-in
sudo ip netns exec access ip addr add 10.0.2.1/30 dev veth-acc-out

sudo ip netns exec core ip addr add 10.0.2.2/30 dev veth-core-in
sudo ip netns exec core ip addr add 10.0.3.1/30 dev veth-core-out

sudo ip netns exec app ip addr add 10.0.3.2/30 dev veth-app
sudo ip netns exec app ip addr add 10.0.4.2/30 dev veth-app2

sudo ip addr add 10.0.4.1/30 dev veth-host

echo "=== Activation du forwarding IP (access, core, app, hôte) ==="
sudo ip netns exec access sysctl -qw net.ipv4.ip_forward=1
sudo ip netns exec core sysctl -qw net.ipv4.ip_forward=1
sudo ip netns exec app sysctl -qw net.ipv4.ip_forward=1
sudo sysctl -qw net.ipv4.ip_forward=1

echo "=== Routage ==="
sudo ip netns exec ue ip route add default via 10.0.1.2

sudo ip netns exec access ip route add default via 10.0.2.2

sudo ip netns exec core ip route add 10.0.1.0/30 via 10.0.2.1
sudo ip netns exec core ip route add default via 10.0.3.2

sudo ip netns exec app ip route add 10.0.1.0/30 via 10.0.3.1
sudo ip netns exec app ip route add 10.0.2.0/30 via 10.0.3.1
sudo ip netns exec app ip route add default via 10.0.4.1

sudo ip route add 10.0.0.0/16 via 10.0.4.2 dev veth-host

echo ""
echo "=== Reconnexion du container Nginx (veth manuel, pas de bridge Docker) ==="

# S'assurer que le service Docker tourne
sudo service docker status > /dev/null 2>&1 || sudo service docker start
sleep 1

# Nettoyer d'éventuels restes du lien précédent
sudo ip link del veth-host2 2>/dev/null || true
sudo rm -f /var/run/netns/app-server 2>/dev/null || true

# Redémarrer le container s'il existe déjà, sinon le créer sans réseau Docker
if docker inspect app-server > /dev/null 2>&1; then
  docker start app-server > /dev/null
else
  docker run -d --name app-server --network none nginx > /dev/null
fi

# Exposer le netns du container pour pouvoir le manipuler avec ip netns
PID=$(docker inspect -f '{{.State.Pid}}' app-server)
sudo mkdir -p /var/run/netns
sudo ln -sfT /proc/$PID/ns/net /var/run/netns/app-server

# Créer le veth manuel hôte <-> container
sudo ip link add veth-host2 type veth peer name veth-container
sudo ip link set veth-container netns app-server

sudo ip netns exec app-server ip link set lo up
sudo ip netns exec app-server ip link set veth-container up
sudo ip netns exec app-server ip addr add 10.0.5.2/24 dev veth-container
sudo ip netns exec app-server ip route add default via 10.0.5.1

sudo ip link set veth-host2 up
sudo ip addr add 10.0.5.1/24 dev veth-host2

# Docker réinitialise la politique FORWARD à DROP sur le namespace racine à chaque démarrage
# du démon. Comme veth-host/veth-host2 vivent dans ce namespace, on autorise explicitement
# le trafic vers/depuis notre chaîne de namespaces, sans rouvrir tout FORWARD en grand.
sudo iptables -C FORWARD -s 10.0.0.0/16 -d 10.0.5.0/24 -j ACCEPT 2>/dev/null || \
  sudo iptables -I FORWARD -s 10.0.0.0/16 -d 10.0.5.0/24 -j ACCEPT
sudo iptables -C FORWARD -s 10.0.5.0/24 -d 10.0.0.0/16 -j ACCEPT 2>/dev/null || \
  sudo iptables -I FORWARD -s 10.0.5.0/24 -d 10.0.0.0/16 -j ACCEPT

echo ""
echo "=== Topologie recréée avec succès ==="
echo "Test de bout en bout (ue -> hôte) :"
sudo ip netns exec ue ping -c 2 10.0.4.1
echo "Test de bout en bout (ue -> container Nginx) :"
sudo ip netns exec ue ping -c 2 10.0.5.2
