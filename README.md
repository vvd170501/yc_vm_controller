```bash
# create a key for the service account (the account should have a `compute.operator` role)
yc iam key create --service-account-name default-sa --output ./config/key.json

docker-compose build
docker-compose up -d
```

**TODO**:
- Improve README
- Resolve instnces by name
- Upload image to a registry
