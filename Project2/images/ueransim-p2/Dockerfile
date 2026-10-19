# UE UERANSIM du Projet 2 : même image que le Projet 1 + route persistante vers le N6.
# Écart guidebook : base 3.2.6 (version du gNB en service) au lieu de 3.3.0,
# pour garder gNB et UE sur la même version du protocole radio simulé (RLS).
FROM gradiant/ueransim:3.2.6

COPY p2-entrypoint.sh /p2-entrypoint.sh
RUN chmod 0755 /p2-entrypoint.sh

ENTRYPOINT ["/p2-entrypoint.sh"]
CMD ["ue"]
