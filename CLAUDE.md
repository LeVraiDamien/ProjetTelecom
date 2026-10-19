# CLAUDE.md — Projets Télécom (Esisar / RTU, 2026-2027)

Ce fichier donne le contexte à Claude Code. Lis-le en entier avant toute action.

## Qui / quoi

- Étudiant : Damien Guffon (Esisar, 4e année, échange à RTU Riga). Réponds **en français**.
- Cours de télécom : 3 projets à présenter en fin de semestre. **Projet 1 terminé** (poussé sur GitHub). **Projet 2 en cours** (ce fichier).
- Damien veut **comprendre** ce qui est fait : explique chaque étape simplement (pourquoi, pas seulement comment), surtout pour la présentation orale.
- Sujets dans `docs/` :
  - `docs/Project 2_Telecommunication Security DevSecOps and Traffic Intelligence.pdf` — le guidebook (à relire en cas de doute)
  - `docs/notes-rendu-projet2.txt` — consignes supplémentaires du prof (ISCX 2012, LLM, Security Gate)

## Environnement

- Windows + **WSL2 Ubuntu**, 7,6 Go de RAM dans WSL (2 Go de swap). Docker Engine tourne **dans WSL** (pas Docker Desktop). Utilisateur dans le groupe `docker` → pas besoin de sudo pour docker.
- **sudo demande un mot de passe** : ne lance pas de commande sudo toi-même, donne-la à Damien.
- RAM serrée : cœur 5G + monitoring + Jenkins + Selenium + ZAP ≈ 6-7 Go au pic. Si besoin, arrêter le monitoring (`monitoring.yaml`) pendant les runs du pipeline, ou augmenter la RAM via `C:\Users\<user>\.wslconfig`.
- Fichiers en **LF** uniquement (scripts bash et fichiers montés dans Docker).
- Repo GitHub : `git@github.com:LeVraiDamien/Projet1Telecom.git`, racine = `~/ProjetTelecom`. `Project1/` = Projet 1 terminé (`ScenarioA/`, `ScenarioB/`) : **ne pas le modifier**. **`Project2/` = dossier de travail du Projet 2 (sécurité)** : tout le nouveau travail va dedans.
- Secrets jamais commités : `.env`, `secrets/tls/`, clé privée de la CA (reste sur l'hôte, jamais montée dans un conteneur).

## Le réseau 5G existant (fondation du Projet 2)

- Basé sur **Gradiant/openverso-images**, dossier `~/openverso-images/docs/open5gs-and-ueransim`.
  **Toujours lancer `docker compose` depuis ce dossier** (le nom de projet Compose en dépend : `open5gs-and-ueransim`).
- Fichiers compose :
  - `ngc.yaml` : cœur Open5GS (AMF, AUSF, BSF, MongoDB, NRF, NSSF, PCF, SCP, SMF, UDM, UDR, UPF, WebUI)
  - `gnb1.yaml` : gNB + UE simulés (UERANSIM)
  - `app.yaml` : Nginx + iperf3 (réseau de données N6) du Projet 1
  - `monitoring.yaml` : Prometheus 9090, Pushgateway 9091, cAdvisor, Grafana 3000 (admin/admin), config dans `monitoring/`
- PLMN : MCC 999, MNC 70, TAC 1, SST 1, SD 0xffffff. Abonnés dans MongoDB (`register_subscriber.sh`).
- Pool IP des UE : 10.45.0.0/16, passerelle `ogstun` 10.45.0.1 sur l'UPF (défini dans `smf.yaml`).
- **Différence majeure avec le guidebook** : tout est sur **un seul réseau Docker** `open5gs-and-ueransim_default` (172.18.0.0/16) avec des **IP dynamiques** (changent au redémarrage). Le guidebook suppose ran-net / n2-net / n3-net / n4-net / sbi-net / dn-net (10.20.6.0/24) / app-net (10.20.8.0/24) / obs-net / security-net (10.20.10.0/24) avec IP fixes.
  → Plan retenu (proposition, à valider avec Damien) : **ne pas reconstruire le cœur**, ajouter `dn-net`, `app-net`, `security-net` avec IP fixes, brancher l'UPF et Nginx sur `dn-net`, ajouter la route `10.20.6.0/24 dev uesimtun0` dans l'UE. Documenter l'écart dans le rapport.
- L'UPF fait du **NAT** sur N6 (les serveurs voient l'IP de l'UPF, pas celle de l'UE) — vérifier `iptables -t nat -S` dans l'UPF avant de concevoir le routage vers dn-net.

## Pièges connus (déjà rencontrés au Projet 1)

1. **UERANSIM ne change pas la route par défaut de l'UE.** Seul le trafic lié à `uesimtun0` passe dans le tunnel 5G. Un `curl` sans `--interface uesimtun0` (ou sans route explicite) **ne traverse pas la 5G**. Toujours prouver le chemin (capture GTP-U sur N3, port UDP 2152).
2. **Horloge WSL2** : l'horloge de la VM dérive (~3,4 % lente) et est recalée par sauts de ~+1,1 s toutes les ~33 s. Chaque saut provoque un `Radio link failure` dans UERANSIM, dont il ne se remet pas (gNB garde l'ancien contexte, `Discarding RRC Setup Request, UE context already exists`) : `uesimtun0` reste UP avec son IP mais le plan utilisateur est mort. Remède : couper `systemd-timesyncd` pendant les mesures (sudo → Damien), et redémarrer l'UE si le plan utilisateur est mort. Important aussi pour la **corrélation par fenêtre de temps** du Projet 2.
3. `restart: on-failure` a été ajouté à mongo, gnb1 et ues1 (sinon ils restent arrêtés après une pause WSL, et udr/pcf échouent en boucle).
4. IP des NF non fixes → filtrer les captures par **port**, pas par IP.
5. MTU du tunnel 1400 (MSS 1360 côté UE).
6. L'interface web Open5GS (localhost:9999) ne s'ouvre pas depuis Windows — non bloquant.

## Projet 2 — résumé des exigences

Workflow : Reuse → Secure → Model → Test → Detect → Automate → Analyze → Defend.

### Scénario A (BASIC) — service sécurisé sur le plan utilisateur 5G
Chemin : UE → gNB → N3/GTP-U → UPF → N6 → Nginx 10.20.6.20 → (HTTPS terminé) → app-net → Django 10.20.8.20:8000.
- **1A** : route `10.20.6.0/24 dev uesimtun0` persistante (image `telecom-lab-ueransim:3.3.0-p2` basée sur `gradiant/ueransim:3.3.0`) ; `ip route get 10.20.6.20` → `dev uesimtun0` ; UE joint 10.20.6.20.
- **1B** : Django 6.0.8 + Gunicorn, image `telecom-lab-django:0.1` (python:3.12-slim), conteneur `scenario-b-django`, **uniquement sur app-net**, SQLite `/app/data/db.sqlite3` sur volume `django-data`, config par variables d'env, healthcheck, `/health/` → `{"service":"project2-django","status":"ok","project":"Telecommunication Security"}`.
- **1C** : Nginx `telecom-lab-nginx:p2` (nginx:latest + iproute2), `scenario-b-nginx`, dn-net 10.20.6.20 + app-net 10.20.8.10 ; TLS 1.2/1.3, 80→301→443, `X-Forwarded-Proto: https`. PKI : Telecom Lab Root CA → cert serveur avec SAN `IP:10.20.6.20` (+ `DNS:telecom-lab.local`, `DNS:localhost`). CA montée en lecture seule dans l'UE à `/etc/telecom-lab/ca.crt`. Test final avec `curl --cacert`, **jamais `-k`**. Preuves : subject, issuer, validité, SAN, handshake 1.2 et 1.3.
- **1D** : endpoints `/`, `/health/`, `/api/status/`, `/search/` (publics), `/profile/`, `/feedback/` (protégés), `/accounts/login/`, `/accounts/logout/`, `/admin/`. Compte `securityadmin`. Non authentifié → 302 vers login ; authentifié → 200 ; POST feedback avec CSRF → 200, sans → **403 (ne jamais désactiver CSRF)**. `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, session cookie Secure+HttpOnly+SameSite=Lax, HSTS `max-age=3600` (pas includeSubdomains/preload), `SECURE_PROXY_SSL_HEADER`, en-têtes X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy same-origin.
- **1E** : test d'acceptation complet depuis l'UE (liste au bas de la section Scénario A du guidebook) → idéalement un script `acceptance.sh` réutilisé par le pipeline.

### Scénario B (ADVANCED) — Security CI/CD
**Aucun environnement pré-intégré n'a été fourni : on construit tout nous-mêmes** (écart à documenter).
- `security-net` 10.20.10.0/24 : Juice Shop `bkimminich/juice-shop:v20.2.0` @ 10.20.10.20:3000, Selenium @ 10.20.10.30:4444 (image officielle `selenium/standalone-chrome` à version figée au lieu de `telecom-lab-selenium:1.0` — écart).
- Jenkins `telecom-lab-jenkins:2.580.1-jdk21` (plugins Git, Docker Workflow, Credentials Binding, Timestamper, HTML Publisher, Workflow Aggregator ; Docker CLI + `/var/run/docker.sock`).
- Jobs éphémères : ZAP `ghcr.io/zaproxy/zaproxy:stable` (baseline + ciblé `plan.yaml`, requestor POST `/rest/user/login`, règle 40018 strength high / threshold low → 1 finding attendu), capture `telecom-lab-capture:1.0` → `juice-shop-ci-sqli.pcapng`, Suricata `jasonish/suricata:8.0` hors ligne avec `security/ids/rules/scenario-b-local.rules` (SID 1000001, `GET /rest/products/search?q=%27%28`) → eve.json, fast.log, stats.log, suricata.log ; Trivy `aquasec/trivy:0.75.0` ; Syft `anchore/syft:v1.52.0` (CycloneDX) ; corrélation `telecom-lab-correlation:1.0` → `security-event-correlation.json/.md`. Hôte : jq, tshark.
- **Release Manifest** : toutes les versions figées (images, plugins Jenkins, tshark, jq…).
- **Ordre du pipeline imposé** (ne pas réordonner) : 1E acceptance → 2A Preflight → ZAP baseline → Selenium → start capture → SQLi contrôlée → ZAP ciblé → stop capture + validation PCAP → Suricata → (Traffic Intelligence optionnel) → Trivy → Syft → corrélation → archive → Security Gate → résultat.
- **RUN_ID** unique par exécution, évidences dans un répertoire par run (pas de mélange avec d'anciens artefacts).
- Security Gate : `REPORT_ONLY` vs `ENFORCE`. Toujours distinguer : exécution de l'outil → constat de sécurité → décision du gate. ZAP 40018 détecté = PASS du contrôle positif ; Suricata SID 1000001 détecté = PASS. Dire clairement ce qui est informatif, ce qui est requis pour passer, ce qui peut bloquer.

### Exigences supplémentaires du prof (`docs/notes-rendu-projet2.txt`)
- **ISCX IDS 2012** : sous-ensemble avec trafic normal + au moins 2 scénarios d'intrusion ; documenter jours/fichiers, volume, labels, méthode. Matrice de confusion, précision, rappel, F1, taux de faux positifs, **par type d'attaque**. Pas seulement l'accuracy. Discuter déséquilibre des classes, limites du dataset et de la méthode, benchmark vs réalité télécom.
  Piste : Suricata + règles ET Open sur les PCAP, association alertes ↔ flux étiquetés du XML (5-tuple + fenêtre de temps). Éviter le jour DDoS botnet (énorme). Les PCAP sont lourds : stockés hors du repo (ex. `~/ProjetTelecom/iscx/`, dans `.gitignore`).
- **LLM** : ≥ 2 contre-vérifications assistées (dont 1 SBOM ↔ Trivy, 1 autre relation de preuves/corrélation). Pour chacune : modèle/fournisseur/version, date, prompt, preuves en entrée, conclusion du LLM, conclusion vérifiée indépendamment, désaccords explicites. Le LLM n'est jamais la base unique d'une détection ou d'une décision du gate.
- Rapport technique concis en Markdown dans le repo + README (secured → tested → detected → analyzed → automated → defended, déploiement, vérification, preuves, reproductibilité, limites connues).

## Organisation proposée de `Project2/`

```
Project2/
  README.md  REPORT.md  RELEASE-MANIFEST.md
  compose/            # fichiers compose ajoutés (dn-net, app-net, nginx, django, security-net…)
  images/             # Dockerfiles : nginx, django, ueransim-p2, jenkins, capture, correlation
  app/                # code Django
  nginx/              # conf nginx
  pki/                # scripts de génération (les clés vont dans secrets/tls/, ignoré par git)
  security/zap/plan.yaml   security/ids/rules/scenario-b-local.rules
  ci/Jenkinsfile   ci/scripts/
  iscx/               # scripts d'évaluation (pas les PCAP)
  evidence/<RUN_ID>/  # preuves par exécution
```

## Méthode de travail

- Avancer par petites étapes vérifiables, avec une preuve observable à chaque étape (sortie de commande, capture, code HTTP) — le prof veut des preuves, pas des affirmations de configuration.
- Garder les résultats bruts dans des fichiers (la doc se rédige à la fin à partir d'eux).
- Avant de modifier le cœur 5G existant, montrer l'état actuel (`docker ps`, `docker network ls`, routes, NAT de l'UPF).
- Estimation globale : ~50-75 h. Ordre : 1A → Django → Nginx/TLS → sécurité Django → acceptance → Juice Shop/Selenium/Jenkins → pipeline étape par étape ; ISCX en parallèle ; corrélation, LLM, gate, rapport à la fin.
