# Passerelle N6 du Projet 2 (scenario-b-nginx).
# iproute2 sert à la route de retour vers les UE (10.45.0.0/16 via l'UPF).
FROM nginx:latest

RUN apt-get update \
 && apt-get install -y --no-install-recommends iproute2 \
 && rm -rf /var/lib/apt/lists/*

# Exécuté par l'entrypoint officiel de nginx avant le démarrage du serveur
COPY 05-p2-routes.sh /docker-entrypoint.d/05-p2-routes.sh
RUN chmod 0755 /docker-entrypoint.d/05-p2-routes.sh
