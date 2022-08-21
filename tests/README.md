# Running tests
1. To start the test environment container run:
```shell
make up
```
2. Run tests 
```shell
make test
```
3. Bring down the docker compose environment
```shell
make down
```

If you need to shell into the docker container to run extra commands you can do so by running 
```shell
make shell
```
and then your command, e,g., 
```shell
pip install black
```
