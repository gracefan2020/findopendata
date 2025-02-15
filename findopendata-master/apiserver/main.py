import os
import heapq
import uuid

from flask import Flask, render_template, jsonify, request, abort, Response
from dateutil.parser import parse
import datefinder
import re
import flask.json as json
from flask_cors import CORS
from psycopg2.extras import RealDictCursor, register_uuid
from psycopg2.pool import ThreadedConnectionPool
import requests
from datasketch import LeanMinHash

import settings


# Flask app.
app = Flask(__name__)


# When deployed to App Engine,
# the `GAE_ENV` environment variable will be set.
if os.environ.get('GAE_SERVICE') == 'apiserver':
    configs = settings.from_datastore("Settings")
    # If deployed, use the local socket interface for accessing Cloud SQL
    db_host = '/cloudsql/{}'.format(configs.get("CLOUD_SQL_CONNECTION_NAME"))
    db_user = configs.get("CLOUD_SQL_USERNAME")
    db_password = configs.get('CLOUD_SQL_PASSWORD')
    db_name = configs.get('CLOUD_SQL_DATABASE_NAME')
    db_config = {
        'user': db_user,
        'password': db_password,
        'dbname': db_name,
        'host': db_host
    }
    lshserver_endpoint = "https://findopendata.com/lsh"
else:
    # If running locally, use the TCP connections instead
    # Set up Cloud SQL Proxy (cloud.google.com/sql/docs/mysql/sql-proxy)
    # so that your application can use 127.0.0.1:3306 to connect to your
    # Cloud SQL instance
    configs = settings.from_yaml(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        os.path.pardir,
        "configs.yaml"))
    db_config = configs.get("postgres")
    lshserver_dev_configs = configs.get("lshserver_local")
    lshserver_endpoint = "http://{}:{}/lsh".format(
        lshserver_dev_configs.get("host"),
        lshserver_dev_configs.get("port"))
    # All all domains for local server.
    CORS(app, resources={r"/api/*": {"origins": "*"}})


# Postgres connection pool.
cnxpool = ThreadedConnectionPool(minconn=1, maxconn=3, **db_config)
# Register UUID adaptor because we want to use UUID type.
register_uuid()


def _execute_get_package_brief(cur, package_id=None, package_key=None):
    sql = r"""SELECT
                key,
                id,
                p.original_host,
                h.display_name as original_host_display_name,
                h.region as original_host_region,
                title
            FROM findopendata.packages as p
            JOIN findopendata.original_hosts as h
            ON p.original_host = h.original_host
        """
    if package_key is not None:
        sql += r" WHERE key = %s "
        args = (package_key,)
    elif package_id is not None:
        sql += r" WHERE id = %s "
        args = (package_id,)
    else:
        raise ValueError("Missing package_id and package_key")
    cur.execute(sql, args)


def _execute_get_package_detailed(cur, package_id=None, package_key=None):
    sql = r"""SELECT
                key,
                id,
                p.original_host,
                h.display_name as original_host_display_name,
                h.region as original_host_region,
                num_files,
                created,
                modified,
                title,
                name,
                description,
                tags,
                license_title,
                license_url,
                organization_name,
                organization_display_name,
                organization_image_url,
                organization_description
            FROM findopendata.packages as p
            JOIN findopendata.original_hosts as h
            ON p.original_host = h.original_host
        """
    if package_key is not None:
        sql += r" WHERE key = %s "
        args = (package_key,)
    elif package_id is not None:
        sql += r" WHERE id = %s "
        args = (package_id,)
    else:
        raise ValueError("Missing package_id and package_key")
    cur.execute(sql, args)


def _execute_keyword_search_title(cur, query, original_hosts=[], limit=10):
    sql = r"""SELECT
                id,
                title,
                organization_display_name,
                num_files
            FROM 
                findopendata.packages,
                plainto_tsquery('english', %s) query
            WHERE 
                to_tsvector('english', title) @@ query
                AND num_files > 0
        """
    if original_hosts:
        sql += r" AND p.original_host in %s "
    sql += r" ORDER BY ts_rank_cd(to_tsvector('english', title), query) DESC LIMIT %s;"
    if original_hosts:
        cur.execute(sql, (query, original_hosts, limit))
    else:
        cur.execute(sql, (query, limit))
        
def _execute_keyword_search_attribute_names(cur, query, original_hosts=[], limit=10):
    sql = r"""SELECT DISTINCT results.title, results.organization_display_name, results.description
            FROM (SELECT
                p.id,
                p.title,
                p.organization_display_name,
                p.description,
                pf.column_names,
                p.crawler_key,
                pf.crawler_key,
                p.num_files
            FROM 
                findopendata.packages as p, 
                findopendata.package_files as pf,
                plainto_tsquery('english', %s) query
            WHERE 
                p.key = pf.package_key
                AND to_tsvector('english', REPLACE(ARRAY_TO_STRING(pf.column_names, ',', '*'), '/', ' ')) @@ query        
                AND num_files > 0
        """
    if original_hosts:
        sql += r" AND p.original_host in %s "
    sql += r"  ORDER BY ts_rank_cd(to_tsvector('english', REPLACE(ARRAY_TO_STRING(pf.column_names, ',', '*'), '/', ' ')), query) DESC LIMIT %s) AS results;"
    if original_hosts:
        cur.execute(sql, (query, original_hosts, limit))
    else:
        cur.execute(sql, (query, limit))



def _execute_keyword_search(cur, query, original_hosts=[], format_filter=[], limit=50):
    _execute_keyword_search_attribute_names(cur, query, original_hosts, limit)
    attResults = cur.fetchall()
    sql = r""" 
            SELECT DISTINCT results.title, results.description, results.id, results.created, results.modified, results.tags, results.organization_name, results.organization_display_name, results.organization_image_url
            FROM ( SELECT
                p.id,
                p.num_files,
                p.created,
                p.modified,
                p.title,
                p.description,
                p.tags,
                p.organization_name,
                p.organization_display_name,
                p.organization_image_url
            FROM 
                findopendata.packages as p, 
                plainto_tsquery('english', %s) query
            """
    if attResults or format_filter:
        print("Number of results when comparing query with attribute names: ", len(attResults))
        sql += r""" , findopendata.package_files as pf"""
                
    sql += r""" WHERE 
                num_files > 0
            """
    if format_filter:
        print("Format Filter is not null: ", format_filter)
        sql += r""" 
                AND p.key = pf.package_key
                AND format !=''
                AND format IN %s"""
        
    if attResults:
        # if there are results from comparing the query with attribute names, then rank the results
        # by similarity between query and title and query and attribute names
        sql += r""" 
                AND p.key = pf.package_key
                AND column_names IS NOT NULL
                AND to_tsvector('english', p.title || REPLACE(ARRAY_TO_STRING(pf.column_names, ',', '*'), '/', ' ')) @@ query
                ORDER BY ts_rank_cd(to_tsvector('english', p.title || REPLACE(ARRAY_TO_STRING(pf.column_names, ',', '*'), '/', ' ')), query) DESC LIMIT %s) as results
                """
    else:
        # else: rank results by similarity between query and title, organization name, and description
        sql += r"""
                AND to_tsvector('english', p.title || p.organization_display_name || p.description) @@ query
                ORDER BY ts_rank_cd(to_tsvector('english', p.title || p.organization_display_name || p.description), query) DESC LIMIT %s) as results"""

    if format_filter:
        cur.execute(sql, (query, format_filter, limit))
    else:
        cur.execute(sql, (query, limit))

def _execute_similar_packages(cur, ids, original_hosts=[], limit=50):
    sql = r"""SELECT
                r.id,
                r.original_host,
                h.display_name as original_host_display_name,
                h.region as original_host_region,
                r.num_files,
                r.created,
                r.modified,
                r.title,
                r.description,
                r.tags,
                r.organization_name,
                r.organization_display_name,
                r.organization_image_url,
                similarity(q.title, r.title) as title_similarity,
                similarity(q.description, r.description) as description_similarity
            FROM findopendata.packages as r,
            (
                SELECT key, title, description
                FROM findopendata.packages
                WHERE id IN %s
            ) as q,
            findopendata.original_hosts as h
            WHERE
            q.title %% r.title
            AND r.original_host = h.original_host
    """
    if original_hosts:
        sql += r" AND r.original_host in %s "
    sql += r" ORDER BY title_similarity DESC, description_similarity DESC LIMIT %s;"
    if original_hosts:
        cur.execute(sql, (ids, original_hosts, limit))
    else:
        cur.execute(sql, (ids, limit))


def _execute_get_column_sketches(cur, ids, original_hosts=[]):
    sql = r"""
            SELECT
                c.id as id,
                c.seed,
                c.minhash,
                c.column_name,
                c.sample,
                c.distinct_count,
                f.id as package_file_id,
                f.created,
                f.modified,
                f.filename,
                f.name,
                f.description,
                f.original_url,
                f.format,
                p.id as package_id,
                p.original_host,
                h.display_name as original_host_display_name,
                h.region as original_host_region,
                p.created as package_created,
                p.modified as package_modified,
                p.title as package_title,
                p.description as package_description,
                p.tags,
                p.organization_name,
                p.organization_display_name,
                p.organization_image_url
            FROM
                findopendata.column_sketches as c,
                findopendata.package_files as f,
                findopendata.packages as p,
                findopendata.original_hosts as h
            WHERE
                c.package_file_key = f.key
                AND f.package_key = p.key
                AND c.id IN %s
                AND p.original_host = h.original_host
    """
    if original_hosts:
        sql += r" AND p.original_host in %s "
        cur.execute(sql, (ids, original_hosts))
    else:
        cur.execute(sql, (ids,))


_original_hosts = []
cnx = cnxpool.getconn()
with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
    cursor.execute(r"""SELECT
                    original_host,
                    display_name as original_host_display_name,
                    region as original_host_region
                FROM findopendata.original_hosts
                WHERE enabled
                ORDER BY display_name""")
    _original_hosts = [row for row in cursor.fetchall()]
cnxpool.putconn(cnx)


@app.route('/api/original-hosts', methods=['GET'])
def original_hosts():
    return jsonify(_original_hosts)

_data_formats = []
cnx = cnxpool.getconn()
with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
    cursor.execute(r"""SELECT DISTINCT format
                   FROM findopendata.package_files
                   WHERE format != ''
                   """)
    format_results = cursor.fetchall()
    pre_filters = ["XLS", "XLSX", "XSL", "ZIP", "PDF", "ODS", "CSV", "TEXT", "JSON", "XML", "API", "HTML", "TXT", "DOCX", "PPTX", "TAR"]
    set_results = set()
    for r in format_results:
        for f in pre_filters:
            if f.upper() in r['format'].upper():
                set_results.add(f.upper())
    _data_formats = [{"format": curr_filetype} for curr_filetype in sorted(set_results)]
    
cnxpool.putconn(cnx)

@app.route('/api/data-formats', methods=['GET'])
def data_formats():
    # allow user to filter datasets by a particular filetype
    return jsonify(_data_formats)


@app.route('/api/keyword-search-title', methods=['GET'])
def keyword_search_title():
    query = request.args.get('query', '')
    if query == '':
        return jsonify([])
    original_host_filter = tuple(request.args.getlist('original_host'))
    cnx = cnxpool.getconn()
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        _execute_keyword_search_title(cursor, query, original_host_filter)
        results = cursor.fetchall()
    cnxpool.putconn(cnx)
    return jsonify(results)

@app.route('/api/keyword-search-attribute', methods=['GET'])
def keyword_search_attribute():
    query = request.args.get('query', '')
    if query == '':
        return jsonify([])
    original_host_filter = tuple(request.args.getlist('original_host'))
    cnx = cnxpool.getconn()
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        _execute_keyword_search_attribute_names(cursor, query, original_host_filter)
        results = cursor.fetchall()
    cnxpool.putconn(cnx)
    return jsonify(results)


@app.route('/api/keyword-search', methods=['GET'])
def keyword_search():
    query = request.args.get('query', '')
    if query == '':
        return jsonify([])
    original_host_filter = tuple(request.args.getlist('original_host'))
    format_filter = tuple(request.args.getlist('format'))
    print(format_filter)
    cnx = cnxpool.getconn()
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        _execute_keyword_search(cursor, query, original_host_filter, format_filter)
        results = cursor.fetchall()
    cnxpool.putconn(cnx)
    # remove duplicate datasets that have different dates (same names, different dates - could indicate an update)
    # can't do DISTINCT in SQL query, since the different dates are embedded in the dataset titles
    titleDate = {}
    final = []
    for index, r in enumerate(results):
        currTitle = r['title']
        try:
            # parse date, for example with format: 30 May 2014
            matches = list(datefinder.find_dates(currTitle))
            if matches and matches[0].year < 2022 and 0 < matches[0].month < 13:
                _, tokens = parse(currTitle, fuzzy_with_tokens=True)
                newTitle = ''.join(tokens)
                if newTitle in titleDate:
                    # find most recent dataset if they have repeated names
                    if matches[0] > titleDate[newTitle][0]:
                        titleDate[newTitle] = (matches[0], index)
                else:
                    titleDate[newTitle] = (matches[0], index)
            
            else:
                # parse year, for example with format 2017
                yearTitle = currTitle
                replaceChar = ['-', '(', ')']
                for char in replaceChar:
                    yearTitle = yearTitle.replace(char, ' ')
                yearMatch = re.findall('\d{4}', yearTitle)
                yearMatch = [i for i in yearMatch if 1900 < int(i) < 2022]
                
                if yearMatch:
                    for m in yearMatch:
                        yearTitle = yearTitle.replace(m, '')
                    yearMatch = list(map(int, yearMatch))
                    
                    if yearTitle in titleDate:
                        if yearMatch[-1] > titleDate[yearTitle][0]:
                            titleDate[yearTitle] = (yearMatch[-1], index)
                    else:
                        titleDate[yearTitle] = (yearMatch[-1], index)
                else:
                    # add every other dataset to the final results
                    final.append(r)
            
        except:
            final.append(r)
            
        
    for td in titleDate:
        final.append(results[titleDate[td][1]])
    return jsonify(final)

@app.route('/api/similar-packages', methods=['GET'])
def similar_packages():
    package_ids = tuple(request.args.getlist('id', type=uuid.UUID))
    if len(package_ids) == 0:
        return jsonify([])
    original_host_filter = tuple(request.args.getlist('original_host', type=str))
    cnx = cnxpool.getconn()
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        _execute_similar_packages(cursor, package_ids, original_host_filter)
        results = cursor.fetchall()
    cnxpool.putconn(cnx)
    return jsonify(results)


@app.route('/api/package/<uuid:package_id>', methods=['GET'])
def package(package_id):
    cnx = cnxpool.getconn()
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        _execute_get_package_detailed(cursor, package_id=package_id)
        package = cursor.fetchone()
    if package is None:
        cnxpool.putconn(cnx)
        abort(404)
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(r"""SELECT
                    id,
                    created,
                    modified,
                    filename,
                    name,
                    description,
                    original_url,
                    format,
                    sample,
                    column_names,
                    column_sketch_ids,
                    sample IS NOT NULL as available
                FROM findopendata.package_files
                WHERE package_key = %s""", (package["key"],))
        package_files = cursor.fetchall()
    cnxpool.putconn(cnx)
    for package_file in package_files:
        if package_file["column_names"] and package_file["column_sketch_ids"]:
            # Merge column ids and names
            package_file["columns"] = [{"column_name": name, "id": sketch_id}
                    for name, sketch_id in
                    zip(package_file["column_names"],
                    package_file["column_sketch_ids"])]
        else:
            package_file["columns"] = None
        package_file.pop("column_names")
        package_file.pop("column_sketch_ids")
    # Remove key from output
    package.pop("key")
    return jsonify(package=package, package_files=package_files)


@app.route('/api/package-file/<uuid:file_id>', methods=['GET'])
def package_file(file_id):
    cnx = cnxpool.getconn()
    # Obtain the package file.
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(r"""SELECT
                    package_key,
                    created,
                    modified,
                    filename,
                    name,
                    description,
                    original_url,
                    format,
                    column_names,
                    column_sketch_ids,
                    sample
                FROM findopendata.package_files
                WHERE id = %s""", (file_id,))
        package_file = cursor.fetchone()
    if package_file is None:
        cnxpool.putconn(cnx)
        abort(404)
    if package_file["column_names"] and package_file["column_sketch_ids"]:
        # Merge column ids and names
        package_file["columns"] = [{"column_name": name, "id": sketch_id}
                for name, sketch_id in
                zip(package_file["column_names"],
                package_file["column_sketch_ids"])]
    else:
        package_file["columns"] = None
    package_file.pop("column_names")
    package_file.pop("column_sketch_ids")
    # Obtain the package info.
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        _execute_get_package_brief(cursor,
                package_key=package_file["package_key"])
        package = cursor.fetchone()
    cnxpool.putconn(cnx)
    if package is None:
        abort(404)
    # Remove key from output
    package_file.pop("package_key")
    package.pop("key")
    return jsonify(package_file=package_file, package=package)


def _containment(jaccard, x, q):
    if jaccard == 1.0:
        return 1.0
    if jaccard == 0.0 or x == 0 or q == 0:
        return 0.0
    return max(jaccard, min(min(x, q)/float(q),
            jaccard * (1.0 + x) / (1.0 - jaccard)))


@app.route('/api/joinable-column-search', methods=['GET'])
def joinable_column_search():
    query_id = request.args.get('id', None, type=uuid.UUID)
    if query_id == None:
        return jsonify([])
    limit = request.args.get('limit', default=50, type=int)
    original_host_filter = tuple(request.args.getlist('original_host'))
    cnx = cnxpool.getconn()
    # Obtain the MinHash of the query.
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        _execute_get_column_sketches(cursor, (query_id,))
        query = cursor.fetchone()
    if query is None:
        # The query does not exist.
        cnxpool.putconn(cnx)
        abort(404)
    # Query the LSH Server.
    try:
        resp = requests.post(lshserver_endpoint+"/query",
                json={"seed": query["seed"], "minhash": query["minhash"]})
        resp.raise_for_status()
    except requests.exceptions.HTTPError as err:
        app.logger.error("Error in querying the LSH server: {}".format(err))
        cnxpool.putconn(cnx)
        abort(500)
    column_ids = [column_id for column_id in resp.json()
            if column_id != str(query_id)]
    if len(column_ids) == 0:
        # Return empty result.
        cnxpool.putconn(cnx)
        return jsonify([])
    # Create the final query results.
    results = []
    query_minhash = LeanMinHash(seed=query["seed"], hashvalues=query["minhash"])
    # Obtain the column sketches of the results.
    with cnx.cursor(cursor_factory=RealDictCursor) as cursor:
        _execute_get_column_sketches(cursor, tuple(column_ids),
                original_hosts=original_host_filter)
        for column in cursor:
            # Skip columns from query table.
            if column["package_file_id"] == query["package_file_id"]:
                continue
            # Compute the similarities for each column in the result.
            jaccard = query_minhash.jaccard(LeanMinHash(
                    seed=column["seed"], hashvalues=column["minhash"]))
            containment = _containment(jaccard, column["distinct_count"],
                    query["distinct_count"])
            column.pop("seed")
            column.pop("minhash")
            column["jaccard"] = jaccard
            column["containment"] = containment
            if len(results) < limit:
                heapq.heappush(results,
                        (containment, column["id"], dict(column)))
            else:
                heapq.heappushpop(results,
                        (containment, column["id"], dict(column)))
    # Done with SQL.
    cnxpool.putconn(cnx)
    results = [column for _, _, column in heapq.nlargest(limit, results)]
    return jsonify(results)


if __name__ == '__main__':
    dev_configs = configs.get("apiserver_local")
    host = dev_configs.get("host")
    port = dev_configs.get("port")
    app.run(host=host, port=port, debug=True)
