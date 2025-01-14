CREATE SCHEMA IF NOT EXISTS findopendata;

/* The registry of all Socrata Discovery API endpoints.
 */
CREATE TABLE IF NOT EXISTS findopendata.socrata_discovery_apis (
    key serial PRIMARY KEY,
    url text NOT NULL,
    enabled boolean default false
);
CREATE UNIQUE INDEX IF NOT EXISTS socrata_discovery_apis_idx ON findopendata.socrata_discovery_apis (url);
INSERT INTO findopendata.socrata_discovery_apis (url, enabled) VALUES
('https://api.eu.socrata.com/api/catalog/v1', true),
('https://api.us.socrata.com/api/catalog/v1', true)
ON CONFLICT DO NOTHING;

/* The collection of Socrata App Tokens.
 */
CREATE TABLE IF NOT EXISTS findopendata.socrata_app_tokens (
    token text PRIMARY KEY,
    added timestamp default current_timestamp
);
CREATE UNIQUE INDEX IF NOT EXISTS socrata_app_tokens_idx ON findopendata.socrata_app_tokens (token);

/* The registry of all Socrata resources.
 */
CREATE TABLE IF NOT EXISTS findopendata.socrata_resources (
    key serial PRIMARY KEY,
    -- The domain name of the publisher.
    domain text NOT NULL,
    -- The unique ID of this resource.
    id varchar(16) NOT NULL,
    -- The storage blob name of the original metadata JSON.
    metadata_blob text NOT NULL,
    -- The storage blob name of the dataset in JSON-line format.
    resource_blob text NOT NULL,
    -- The original resource URL where the dataset is downloaded.
    original_url text NOT NULL,
    -- The size of the dataset in bytes.
    dataset_size bigint NOT NULL,
    -- The time this resource is added.
    added timestamp default current_timestamp,
    -- The time this resource record is last updated.
    updated timestamp default current_timestamp
);
CREATE UNIQUE INDEX IF NOT EXISTS socrata_resources_idx ON findopendata.socrata_resources (domain, id);

/* The registry of all CKAN API endpoints.
 */
CREATE TABLE IF NOT EXISTS findopendata.ckan_apis (
    key serial PRIMARY KEY,
    scheme text NOT NULL default 'https',
    endpoint text NOT NULL,
    name text NOT NULL,
    region text NOT NULL,
    enabled boolean NOT NULL default false
);
CREATE UNIQUE INDEX IF NOT EXISTS ckan_apis_idx ON findopendata.ckan_apis (scheme, endpoint);
INSERT INTO findopendata.ckan_apis (endpoint, name, region, enabled) VALUES
('data.gov.uk', 'UK Open Data', 'United Kingdoms', true)
ON CONFLICT DO NOTHING;

/* The central registry of all discovered CKAN data packages.
 */
CREATE TABLE IF NOT EXISTS findopendata.ckan_packages (
    key serial PRIMARY KEY,
    -- The CKAN API endpoint URL without HTTP scheme.
    endpoint text NOT NULL,
    -- The CKAN package ID.
    package_id text NOT NULL,
    -- The storage blob name of the original package JSON.
    package_blob text NOT NULL,
    -- The time this package is added 
    added timestamp default current_timestamp,
    -- The time this package record is last updated
    updated timestamp default current_timestamp
);
CREATE UNIQUE INDEX IF NOT EXISTS ckan_packages_idx ON findopendata.ckan_packages (endpoint, package_id);

/* The central registry of all retrieved CKAN resources associated with 
 * packages.
 */
CREATE TABLE IF NOT EXISTS findopendata.ckan_resources (
    key serial PRIMARY KEY,
    -- The package key associated with this file.
    package_key serial NOT NULL REFERENCES findopendata.ckan_packages(key),
    -- The resource ID of this file.
    resource_id text NOT NULL,
    -- The filename relative to this resource.
    filename text,
    -- The storage blob name of this file.
    resource_blob text,
    -- The original URL from which the file is retrieved.
    original_url text NOT NULL,
    -- The size of the file in bytes.
    file_size bigint,
    -- The portion of the raw CKAN metadata associated with this resource.
    raw_metadata jsonb NOT NULL,
    -- The time this file record is added.
    added timestamp default current_timestamp,
    -- The time this file record is last updated
    updated timestamp default current_timestamp
);
CREATE UNIQUE INDEX IF NOT EXISTS ckan_resources_idx ON findopendata.ckan_resources (package_key, resource_id);

