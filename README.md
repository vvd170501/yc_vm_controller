```bash
# create a key for the service account (the account should have a `compute.operator` role)
yc iam key create --service-account-name default-sa --output ./config/key.json

docker build -t vm_controller .
docker run -d --restart=on-failure:10 --name=vm_controller -v $PWD/config:/config vm_controller
```

**TODO**:
- Improve README
- Use docker-compose
