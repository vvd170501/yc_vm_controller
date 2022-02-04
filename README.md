```bash
# Create a service account
ACC_NAME=vm-controller
yc iam service-account create --name $ACC_NAME

# Add permissions
CURRENT_FOLDER=$(yc config list | grep folder-id | cut -d " " -f 2)
ACC_ID=$(yc iam service-account get $ACC_NAME | grep "^id:" | cut -d " " -f 2)
yc resource-manager folder add-access-binding $CURRENT_FOLDER --role compute.operator --subject serviceAccount:$ACC_ID

# Create a key for the service account
yc iam key create --service-account-name $ACC_NAME --output ./config/key.json

# Start the bot
docker-compose pull
docker-compose up -d
```

**TODO**:
- Improve README
- Resolve instnces by name
