# NEXUS AI AUTOMATION

Première version d'un tableau de bord Python pour surveiller des sites HTTPS et exécuter des contrôles planifiés.

## Fonctionnalités
- Tableau de bord protégé par mot de passe.
- Ajout et suppression de surveillances de sites.
- Contrôle manuel et planification périodique.
- Historique du dernier statut et de la dernière vérification.
- API de santé sur `/health`.
- Blocage des URL non HTTPS et des adresses IP privées/locales.

## Déploiement Render
Le fichier `render.yaml` configure un service Python à Francfort.
1. Créez le service depuis ce dépôt dans Render (Blueprint ou Web Service).
2. Définissez une valeur longue et unique pour `APP_PASSWORD` dans les variables d'environnement Render.
3. Déployez puis ouvrez l'URL fournie par Render.

## Développement local
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export APP_PASSWORD='un-mot-de-passe-long'
uvicorn app:app --reload
``

## Limites importantes
Cette version initiale ne lance pas de commandes système, ne réalise pas d'achats et n'envoie pas de messages. Les intégrations IA, notifications, connecteurs tiers et stockage persistant doivent être ajoutés et configurés explicitement. Le disque local des offres Render gratuites peut être éphémère : prévoir un stockage persistant avant de dépendre de l'historique à long terme. Ne placez jamais de clé API dans le dépôt Git.
