# Instructions for Setup and Running Localhost

Modified findopendata: A search engine for Open Data

Setups

1. run postgres: use PostGres app to run "fan"
2. run rabbitmq: `docker run -d --hostname my-rabbit --name some-rabbit rabbitmq:3`
3. run:

    ```
    psql -f sql/create_crawler_tables.sql
    psql -f sql/create_metadata_tables.sql
    psql -f sql/create_sketch_tables.sql
    ```

    see results in `psql -c "SELECT * FROM findopendata.ckan_apis"`

4. run celery worker: `celery -A findopendata worker -l info -Ofair`

    to kill all tasks queued up: `celery -A findopendata purge`

5. run `python harvest_datasets.py`

    WAIT for it to finish
    results in findopendata.ckan_packages and findopendata.socrata_resources

6. run `python generate_metadata.py`

    results in `psql -c "SELECT count(*) FROM findopendata.packages"`

7. run `python sketch_dataset_content.py`

    results in findopendata.column_sketches, findopendata.package_files

8. run `python apiserver/main.py`

9. run `go run lshserver/main.go`

    download 5 dependencies like: "go get github.com/gin-contrib/cors"

10. from frontend: `npm start`

    cd into frontend --> `npm install`

To change / add datasets: change "create_crawler_tables.sql" and "create_metadata_tables.sql"
For postgres configs: lshserver/main.go, configs.yaml, lshserver/app.yaml

To run localhost:

1. `./start_celery_worker.sh`
2. `python apiserver/main.py`
3. `go run lshserver/main.go`
4. `cd frontend --> npm start`
